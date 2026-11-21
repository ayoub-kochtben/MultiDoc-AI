"""Prompt-injection defenses for untrusted document content.

1. Detection: heuristic patterns (FR/EN) flag chunks that contain instructions aimed at an AI.
2. Neutralization: chat-template control tokens and our own source delimiters are escaped so that
   document text can never close the data block or impersonate a system/assistant turn.
3. The system prompt (app.llm.prompts) states that sources are data, never instructions.
"""
from __future__ import annotations

import re

INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rx, re.I | re.S)) for name, rx in [
        ("ignore_instructions_en", r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your|system)\b.{0,30}\b(instructions?|rules?|prompts?|directives?|guidelines?)"),
        ("ignore_instructions_fr", r"\b(ignore[rz]?|oublie[rz]?|n[ée]glige[rz]?|contourne[rz]?|outrepasse[rz]?)\b.{0,40}\b(tes|vos|les|toutes?|ses|pr[ée]c[ée]dentes?)\b.{0,30}\b(instructions?|r[èe]gles?|consignes?|directives?|prompts?)"),
        ("role_override_en", r"\b(you are now|from now on,? you|act as (an?|the)|pretend (to be|you are)|new instructions?:)"),
        ("role_override_fr", r"\b(tu es (d[ée]sormais|maintenant)|vous [êe]tes (d[ée]sormais|maintenant)|à partir de maintenant,? (tu|vous)|nouvelles? instructions? ?:|joue le r[ôo]le)"),
        ("prompt_exfiltration", r"\b(reveal|print|show|display|r[ée]v[èe]le[rz]?|affiche[rz]?|montre[rz]?)\b.{0,30}\b(system prompt|prompt syst[èe]me|your instructions|tes instructions|vos instructions)"),
        ("chat_template_tokens", r"(<\|im_(start|end)\|>|<\|(system|user|assistant|endoftext|eot_id|start_header_id)\|>|\[/?INST\]|<<SYS>>)"),
        ("fake_role_header", r"(^|\n)\s*(#{2,}\s*)?(system|assistant|syst[èe]me)\s*:\s"),
        ("ai_addressed", r"\b(chatbot|assistant|ia|ai|llm|mod[èe]le)\b.{0,40}\b(dois|doit|must|should|ne (dois|doit) pas)\b.{0,40}\b(r[ée]pondre|answer|dire|say|ignorer|ignore)"),
    ]
]

_TOKEN_RX = re.compile(r"<\|[^|>]{1,40}\|>|\[/?INST\]|<<SYS>>|<</SYS>>")
_DELIM_RX = re.compile(r"</?\s*(source|sources|document|documents|context|contexte)\b[^>]*>", re.I)


def detect_injection(text: str) -> list[str]:
    return [name for name, rx in INJECTION_PATTERNS if rx.search(text)]


def neutralize(text: str) -> str:
    text = _TOKEN_RX.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›").replace("[", "⟦").replace("]", "⟧"), text)
    return _DELIM_RX.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text)
