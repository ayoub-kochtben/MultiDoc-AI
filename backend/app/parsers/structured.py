"""JSON and XML parsers: structure-aware extraction (JSON paths / XPath), record arrays exposed as tables."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lxml import etree

from app.parsers.base import ParsedDocument, ParserError, Segment, TableData, format_value, json_safe
from app.parsers.text import decode_bytes

MAX_SEGMENT_FIELDS = 60


# --------------------------------------------------------------------------------------- JSON
def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, (str, int, float, bool))


def _fmt_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return format_value(v)


class JsonParser:
    name = "json"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        raw = decode_bytes(path.read_bytes())
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # JSON Lines support
            try:
                data = [json.loads(line) for line in raw.splitlines() if line.strip()]
            except json.JSONDecodeError as exc:
                raise ParserError(f"JSON invalide : {exc}") from exc
        segments: list[Segment] = []
        tables: list[TableData] = []
        self._walk(data, "$", [], segments, tables)
        if not segments:
            raise ParserError("Le document JSON ne contient aucune donnée exploitable.")
        return ParsedDocument(segments=segments, tables=tables, parser="json")

    def _walk(self, node: Any, path: str, context: list[str], segments: list[Segment], tables: list[TableData]) -> None:
        if isinstance(node, dict):
            scalars = [(k, v) for k, v in node.items() if _is_scalar(v)]
            nested = [(k, v) for k, v in node.items() if not _is_scalar(v)]
            if scalars:
                lines = [f"{k}: {_fmt_scalar(v)}" for k, v in scalars[:MAX_SEGMENT_FIELDS]]
                header = f"Objet {path}" + (f" (contexte : {'; '.join(context)})" if context else "")
                segments.append(Segment(text=header + "\n" + "\n".join(lines), kind="record",
                                        meta={"json_path": path}, group=path))
            # identifying scalars (name/id/title) give context to children
            ident = [f"{k}={_fmt_scalar(v)}" for k, v in scalars if k.lower() in {"id", "name", "nom", "title", "titre", "company", "code"}]
            for k, v in nested:
                self._walk(v, f"{path}.{k}", context + ident, segments, tables)
        elif isinstance(node, list):
            dict_items = [x for x in node if isinstance(x, dict)]
            if dict_items and len(dict_items) == len(node):
                cols: list[str] = []
                for item in dict_items:
                    for k, v in item.items():
                        if _is_scalar(v) and k not in cols:
                            cols.append(k)
                if cols:
                    tables.append(TableData(
                        name=path.lstrip("$.") or "root",
                        columns=cols,
                        rows=[[json_safe(item.get(c)) for c in cols] for item in dict_items],
                        meta={"json_path": path},
                    ))
            if node and all(_is_scalar(x) for x in node):
                segments.append(Segment(
                    text=f"Liste {path}" + (f" (contexte : {'; '.join(context)})" if context else "") + "\n"
                    + "\n".join(f"- {_fmt_scalar(x)}" for x in node[:500]),
                    kind="record", meta={"json_path": path}, group=path,
                ))
                return
            for i, item in enumerate(node):
                self._walk(item, f"{path}[{i}]", context, segments, tables)
        elif node is not None and path == "$":
            segments.append(Segment(text=_fmt_scalar(node), meta={"json_path": "$"}))


# ---------------------------------------------------------------------------------------- XML
def _local(tag: Any) -> str:
    if not isinstance(tag, str):
        return ""
    return etree.QName(tag).localname


class XmlParser:
    name = "xml"

    def parse(self, path: Path, filename: str) -> ParsedDocument:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=False,
                                 remove_comments=True, remove_pis=True, load_dtd=False)
        try:
            tree = etree.parse(str(path), parser)
        except etree.XMLSyntaxError as exc:
            raise ParserError(f"XML invalide : {exc}") from exc
        root = tree.getroot()
        segments: list[Segment] = []
        tables: list[TableData] = []
        self._walk(root, tree, segments, tables)
        if not segments:
            raise ParserError("Le document XML ne contient aucun texte.")
        return ParsedDocument(segments=segments, tables=tables, parser="xml/lxml", metadata={"root": _local(root.tag)})

    @staticmethod
    def _is_record(el: etree._Element) -> bool:
        children = [c for c in el if isinstance(c.tag, str)]
        return bool(children) and all(len([g for g in c if isinstance(g.tag, str)]) == 0 for c in children)

    @staticmethod
    def _record_fields(el: etree._Element) -> list[tuple[str, str]]:
        fields = [(f"@{_local(k)}", v) for k, v in el.attrib.items()]
        for c in el:
            if isinstance(c.tag, str):
                fields.extend((f"{_local(c.tag)}@{_local(k)}", v) for k, v in c.attrib.items())
                fields.append((_local(c.tag), " ".join((c.text or "").split())))
        return fields

    def _walk(self, el: etree._Element, tree: etree._ElementTree, segments: list[Segment], tables: list[TableData]) -> None:
        children = [c for c in el if isinstance(c.tag, str)]
        xpath = tree.getpath(el)
        if self._is_record(el):
            fields = self._record_fields(el)
            text = f"<{_local(el.tag)}> " + " | ".join(f"{k}: {v}" for k, v in fields if v != "")
            segments.append(Segment(text=text, kind="record", meta={"xpath": xpath}, group=tree.getpath(el.getparent()) if el.getparent() is not None else xpath))
            return
        own_text = " ".join((el.text or "").split())
        if own_text or (el.attrib and not children):
            attrs = " ".join(f'{_local(k)}="{v}"' for k, v in el.attrib.items())
            segments.append(Segment(text=f"<{_local(el.tag)}{' ' + attrs if attrs else ''}> {own_text}".strip(),
                                    meta={"xpath": xpath}, group=xpath))
        # Repeated record-like siblings become a table (e.g. /orders/order)
        by_tag: dict[str, list[etree._Element]] = {}
        for c in children:
            if self._is_record(c):
                by_tag.setdefault(_local(c.tag), []).append(c)
        for tag, items in by_tag.items():
            if len(items) >= 2:
                cols: list[str] = []
                recs = [dict(self._record_fields(i)) for i in items]
                for r in recs:
                    cols.extend(k for k in r if k not in cols)
                tables.append(TableData(
                    name=f"{_local(el.tag)}_{tag}",
                    columns=[c.lstrip("@") for c in cols],
                    rows=[[_auto_number(r.get(c)) for c in cols] for r in recs],
                    meta={"xpath": f"{xpath}/{tag}"},
                ))
        for c in children:
            self._walk(c, tree, segments, tables)
            tail = " ".join((c.tail or "").split())
            if tail:
                segments.append(Segment(text=tail, meta={"xpath": xpath}, group=xpath))


def _auto_number(v: str | None) -> Any:
    """Convert numeric XML text to int/float so that SQL aggregations work."""
    if v is None or v == "":
        return None
    s = v.strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s.replace(",", ".")) if s.count(",") <= 1 else s
    except ValueError:
        return v
