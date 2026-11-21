"use client";

import { AlertTriangle, Calculator, Download, X } from "lucide-react";
import { api, type Source } from "@/lib/api";
import { TypeBadge } from "@/components/ui";

function Score({ label, value }: { label: string; value?: number | null }) {
  if (value === null || value === undefined) return null;
  return (
    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500 dark:bg-slate-800">
      {label} {value.toFixed(3)}
    </span>
  );
}

export function SourcePanel({ source, onClose }: { source: Source; onClose: () => void }) {
  return (
    <aside className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl xl:static xl:z-auto xl:w-[400px] xl:shadow-none dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="grid size-6 place-items-center rounded bg-accent-600 font-mono text-xs font-semibold text-white">
              {source.n}
            </span>
            <TypeBadge type={source.file_type} />
          </div>
          <div className="truncate text-sm font-semibold" title={source.filename}>
            {source.filename}
          </div>
          <div className="text-xs text-slate-500">{source.location}</div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Fermer">
          <X size={18} />
        </button>
      </div>
      <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto p-4">
        {source.suspicious && (
          <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            Ce passage contient des instructions adressées à une IA. Il a été traité comme une simple donnée.
          </div>
        )}
        {source.type === "computation" ? (
          <>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
              <Calculator size={14} /> Calcul exact (SQL exécuté sur les données)
            </div>
            {source.explanation && <p className="text-sm text-slate-600 dark:text-slate-300">{source.explanation}</p>}
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-emerald-300">
              {source.sql}
            </pre>
            <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 dark:bg-slate-800">
                  <tr>
                    {source.columns?.map((c) => (
                      <th key={c} className="px-3 py-1.5 text-left font-mono text-xs font-medium text-slate-500">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {source.rows?.map((r, i) => (
                    <tr key={i} className="border-t border-slate-100 dark:border-slate-800">
                      {r.map((v, j) => (
                        <td key={j} className="px-3 py-1.5 tabular-nums">
                          {v === null ? "—" : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <>
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Passage cité</div>
            <div className="rounded-lg border-l-4 border-accent-500 bg-slate-50 p-3 text-sm leading-relaxed whitespace-pre-wrap dark:bg-slate-800/60">
              {source.content || source.excerpt}
            </div>
          </>
        )}
        <div className="flex flex-wrap gap-1.5">
          <Score label="rerank" value={source.scores?.rerank} />
          <Score label="cosinus" value={source.scores?.vector} />
          <Score label="mots-clés" value={source.scores?.keyword} />
        </div>
      </div>
      <div className="border-t border-slate-200 p-3 dark:border-slate-800">
        <a
          href={api.fileUrl(source.document_id)}
          className="inline-flex items-center gap-2 text-sm font-medium text-accent-600 hover:underline"
          target="_blank"
          rel="noreferrer"
        >
          <Download size={14} /> Ouvrir le fichier original
        </a>
      </div>
    </aside>
  );
}
