"use client";

import { MessageSquarePlus, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Conversation } from "@/lib/api";

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  return (
    <div className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex dark:border-slate-800 dark:bg-slate-900">
      <div className="p-3">
        <button
          onClick={onNew}
          className="flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-accent-600 text-sm font-medium text-white hover:bg-accent-700"
        >
          <MessageSquarePlus size={16} /> Nouvelle conversation
        </button>
      </div>
      <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Historique</div>
      <ul className="scrollbar-thin flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {conversations.length === 0 && <li className="px-2 py-3 text-xs text-slate-400">Aucune conversation.</li>}
        {conversations.map((c) => (
          <li key={c.id} className="group relative">
            {editing === c.id ? (
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={() => setEditing(null)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && draft.trim()) {
                    onRename(c.id, draft.trim());
                    setEditing(null);
                  }
                  if (e.key === "Escape") setEditing(null);
                }}
                className="h-8 w-full rounded-md border border-accent-500 bg-white px-2 text-sm outline-none dark:bg-slate-800"
              />
            ) : confirmDelete === c.id ? (
              <div className="flex items-center justify-between gap-1 rounded-md bg-rose-50 px-2 py-1.5 text-xs dark:bg-rose-950/40">
                <span className="text-rose-700 dark:text-rose-300">Supprimer ?</span>
                <span className="flex gap-1">
                  <button onClick={() => (onDelete(c.id), setConfirmDelete(null))} className="rounded bg-rose-600 px-2 py-0.5 text-white">
                    Oui
                  </button>
                  <button onClick={() => setConfirmDelete(null)} className="rounded px-2 py-0.5 text-slate-600 hover:bg-white">
                    Non
                  </button>
                </span>
              </div>
            ) : (
              <button
                onClick={() => onSelect(c.id)}
                className={`w-full truncate rounded-md px-2 py-1.5 pr-14 text-left text-sm ${
                  activeId === c.id
                    ? "bg-accent-50 font-medium text-accent-700 dark:bg-accent-500/15 dark:text-accent-100"
                    : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                }`}
                title={c.title}
              >
                {c.title}
              </button>
            )}
            {editing !== c.id && confirmDelete !== c.id && (
              <span className="absolute top-1 right-1 hidden gap-0.5 group-hover:flex">
                <button
                  onClick={() => (setEditing(c.id), setDraft(c.title))}
                  className="rounded p-1 text-slate-400 hover:bg-white hover:text-slate-700 dark:hover:bg-slate-700"
                  aria-label="Renommer"
                >
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => setConfirmDelete(c.id)}
                  className="rounded p-1 text-slate-400 hover:bg-white hover:text-rose-600 dark:hover:bg-slate-700"
                  aria-label="Supprimer"
                >
                  <Trash2 size={13} />
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
