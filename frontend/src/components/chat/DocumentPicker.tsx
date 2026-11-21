"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Files } from "lucide-react";
import type { DocumentItem } from "@/lib/api";
import { TypeBadge } from "@/components/ui";

export function DocumentPicker({
  documents,
  selected,
  onChange,
}: {
  documents: DocumentItem[];
  selected: string[];
  onChange: (ids: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const indexed = documents.filter((d) => d.status === "indexed");

  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const label =
    selected.length === 0
      ? `Tous les documents (${indexed.length})`
      : selected.length === 1
        ? indexed.find((d) => d.id === selected[0])?.filename ?? "1 document"
        : `${selected.length} documents sélectionnés`;
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const visible = indexed.filter((d) => d.filename.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex h-8 max-w-72 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
      >
        <Files size={14} className="shrink-0 text-slate-400" />
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className="shrink-0 text-slate-400" />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-20 mb-2 w-80 rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <div className="border-b border-slate-100 p-2 dark:border-slate-800">
            <input
              autoFocus
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filtrer…"
              className="h-8 w-full rounded-md bg-slate-50 px-2 text-sm outline-none dark:bg-slate-800"
            />
          </div>
          <div className="scrollbar-thin max-h-72 overflow-y-auto p-1">
            <button
              onClick={() => onChange([])}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
            >
              <span className={`grid size-4 place-items-center rounded border ${selected.length === 0 ? "border-accent-600 bg-accent-600 text-white" : "border-slate-300"}`}>
                {selected.length === 0 && <Check size={12} />}
              </span>
              Tous les documents
            </button>
            {visible.map((d) => (
              <button
                key={d.id}
                onClick={() => toggle(d.id)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <span className={`grid size-4 shrink-0 place-items-center rounded border ${selected.includes(d.id) ? "border-accent-600 bg-accent-600 text-white" : "border-slate-300"}`}>
                  {selected.includes(d.id) && <Check size={12} />}
                </span>
                <TypeBadge type={d.file_type} />
                <span className="truncate">{d.filename}</span>
              </button>
            ))}
            {indexed.length === 0 && <p className="p-3 text-sm text-slate-500">Aucun document indexé.</p>}
          </div>
        </div>
      )}
    </div>
  );
}
