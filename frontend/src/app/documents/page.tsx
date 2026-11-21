"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Download, Eye, RefreshCw, Trash2, UploadCloud, X, XCircle } from "lucide-react";
import { api, formatBytes, PROCESSING, uploadFiles, type ChunkItem, type DocumentItem, type UploadResult } from "@/lib/api";
import { Button, Card, ErrorBanner, PageHeader, Spinner, TypeBadge } from "@/components/ui";

const STATUS_LABEL: Record<string, string> = {
  queued: "En attente",
  parsing: "Extraction",
  chunking: "Découpage",
  embedding: "Embeddings",
  indexed: "Indexé",
  failed: "Échec",
};

function StatusCell({ d }: { d: DocumentItem }) {
  if (d.status === "indexed")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-600">
        <CheckCircle2 size={14} /> Indexé
      </span>
    );
  if (d.status === "failed")
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-rose-600" title={d.error ?? ""}>
        <XCircle size={14} /> Échec
      </span>
    );
  return (
    <div className="w-36">
      <div className="mb-1 flex justify-between text-[11px] text-slate-500">
        <span className="truncate">{d.stage_detail || STATUS_LABEL[d.status]}</span>
        <span>{Math.round(d.progress * 100)}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        <div className="h-full rounded-full bg-accent-500 transition-all duration-500" style={{ width: `${Math.max(4, d.progress * 100)}%` }} />
      </div>
    </div>
  );
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState<number | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [formats, setFormats] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ doc: DocumentItem; chunks: ChunkItem[] | null } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(
    () =>
      api
        .documents()
        .then(setDocs)
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false)),
    [],
  );

  useEffect(() => {
    load();
    api.formats().then((f) => setFormats(f.extensions)).catch(() => {});
  }, [load]);

  // Poll while something is being indexed
  const processing = docs.some((d) => PROCESSING.includes(d.status));
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(load, 1200);
    return () => clearInterval(t);
  }, [processing, load]);

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setError(null);
    setUploading(0);
    try {
      const res = await uploadFiles(files, setUploading);
      setResults(res);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(null);
    }
  };

  const openPreview = async (doc: DocumentItem) => {
    setPreview({ doc, chunks: null });
    try {
      setPreview({ doc, chunks: await api.chunks(doc.id) });
    } catch (e) {
      setError((e as Error).message);
      setPreview(null);
    }
  };

  const visible = docs.filter((d) => d.filename.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Documents"
        subtitle={`${docs.length} document(s) · ${docs.filter((d) => d.status === "indexed").length} indexé(s)`}
        actions={
          <Button variant="secondary" onClick={load}>
            <RefreshCw size={14} /> Actualiser
          </Button>
        }
      />
      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            upload(Array.from(e.dataTransfer.files));
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
            dragOver
              ? "border-accent-500 bg-accent-50 dark:bg-accent-500/10"
              : "border-slate-300 bg-white hover:border-accent-500 dark:border-slate-700 dark:bg-slate-900"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            multiple
            hidden
            accept={formats.join(",")}
            onChange={(e) => {
              upload(Array.from(e.target.files || []));
              e.target.value = "";
            }}
          />
          {uploading !== null ? (
            <>
              <Spinner size={28} />
              <p className="mt-3 text-sm font-medium">Envoi… {Math.round(uploading * 100)}%</p>
            </>
          ) : (
            <>
              <UploadCloud size={32} className="text-accent-500" />
              <p className="mt-3 text-sm font-medium">Glissez-déposez vos fichiers ici, ou cliquez pour parcourir</p>
              <p className="mt-1 max-w-xl text-xs text-slate-500">
                PDF (OCR si scanné), DOCX, XLSX, CSV, PPTX, HTML, JSON, XML, TXT, MD, EML, images · envoi multiple · doublons détectés par SHA-256
              </p>
            </>
          )}
        </div>

        {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

        {results.length > 0 && (
          <Card className="p-3">
            <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-slate-400">
              Résultat de l&apos;envoi
              <button onClick={() => setResults([])} aria-label="Fermer">
                <X size={14} />
              </button>
            </div>
            <ul className="space-y-1 text-sm">
              {results.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  {r.status === "accepted" ? (
                    <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-500" />
                  ) : r.status === "duplicate" ? (
                    <Copy size={15} className="mt-0.5 shrink-0 text-amber-500" />
                  ) : (
                    <XCircle size={15} className="mt-0.5 shrink-0 text-rose-500" />
                  )}
                  <span>
                    <span className="font-medium">{r.filename}</span>
                    <span className="text-slate-500">
                      {" — "}
                      {r.status === "accepted" ? "accepté, indexation en cours" : r.detail}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-2.5 dark:border-slate-800">
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Rechercher un document…"
              className="h-8 w-64 rounded-md bg-slate-50 px-2.5 text-sm outline-none dark:bg-slate-800"
            />
          </div>
          {loading ? (
            <div className="grid place-items-center p-10">
              <Spinner size={22} />
            </div>
          ) : visible.length === 0 ? (
            <p className="p-10 text-center text-sm text-slate-500">Aucun document.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-800/50">
                  <tr>
                    <th className="px-4 py-2 font-medium">Fichier</th>
                    <th className="px-4 py-2 font-medium">Taille</th>
                    <th className="px-4 py-2 font-medium">Chunks</th>
                    <th className="px-4 py-2 font-medium">Parser</th>
                    <th className="px-4 py-2 font-medium">Statut</th>
                    <th className="px-4 py-2 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((d) => (
                    <tr key={d.id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <TypeBadge type={d.file_type} />
                          <span className="max-w-72 truncate font-medium" title={d.filename}>
                            {d.filename}
                          </span>
                          {Number(d.metadata?.suspicious_chunks || 0) > 0 && (
                            <span title="Contient des instructions suspectes (prompt injection) — traitées comme données">
                              <AlertTriangle size={14} className="text-amber-500" />
                            </span>
                          )}
                        </div>
                        {d.status === "failed" && d.error && <div className="mt-1 max-w-md text-xs text-rose-600">{d.error}</div>}
                      </td>
                      <td className="px-4 py-2.5 whitespace-nowrap text-slate-500 tabular-nums">{formatBytes(d.size_bytes)}</td>
                      <td className="px-4 py-2.5 text-slate-500 tabular-nums">
                        {d.num_chunks || "—"}
                        {d.num_pages ? <span className="text-xs"> · {d.num_pages} p.</span> : null}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-xs text-slate-500">
                        {d.parser ?? "—"}
                        {d.processing_seconds != null && <div>{d.processing_seconds.toFixed(1)} s</div>}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusCell d={d} />
                      </td>
                      <td className="px-4 py-2.5">
                        {confirmDelete === d.id ? (
                          <div className="flex items-center justify-end gap-1.5 text-xs">
                            <span className="text-rose-600">Supprimer définitivement ?</span>
                            <Button
                              size="sm"
                              variant="danger"
                              onClick={async () => {
                                setConfirmDelete(null);
                                await api.deleteDocument(d.id).catch((e) => setError(e.message));
                                load();
                              }}
                            >
                              Oui
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(null)}>
                              Non
                            </Button>
                          </div>
                        ) : (
                          <div className="flex justify-end gap-0.5">
                            <IconBtn label="Aperçu des chunks" onClick={() => openPreview(d)} disabled={d.status !== "indexed"}>
                              <Eye size={15} />
                            </IconBtn>
                            <a href={api.fileUrl(d.id)} target="_blank" rel="noreferrer" title="Télécharger" className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
                              <Download size={15} />
                            </a>
                            <IconBtn
                              label="Réindexer"
                              disabled={PROCESSING.includes(d.status) && d.status !== "queued"}
                              onClick={async () => {
                                await api.reindex(d.id).catch((e) => setError(e.message));
                                load();
                              }}
                            >
                              <RefreshCw size={15} />
                            </IconBtn>
                            <IconBtn label="Supprimer" danger onClick={() => setConfirmDelete(d.id)}>
                              <Trash2 size={15} />
                            </IconBtn>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {preview && (
        <div className="fixed inset-0 z-40 flex justify-end bg-slate-900/30" onClick={() => setPreview(null)}>
          <div className="flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl dark:bg-slate-900" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <TypeBadge type={preview.doc.file_type} />
                  <span className="truncate font-semibold">{preview.doc.filename}</span>
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-slate-400">SHA-256 {preview.doc.sha256.slice(0, 16)}…</div>
              </div>
              <button onClick={() => setPreview(null)} className="rounded p-1 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Fermer">
                <X size={18} />
              </button>
            </div>
            <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto p-5">
              {preview.chunks === null ? (
                <Spinner />
              ) : (
                preview.chunks.map((c) => (
                  <div key={c.id} className="rounded-lg border border-slate-200 dark:border-slate-700">
                    <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-slate-50 px-3 py-1.5 text-xs dark:border-slate-800 dark:bg-slate-800/50">
                      <span className="font-mono text-slate-400">#{c.chunk_index}</span>
                      <span className="truncate text-slate-600 dark:text-slate-300">{c.location}</span>
                      <span className="flex items-center gap-1.5">
                        {c.suspicious && <AlertTriangle size={13} className="text-amber-500" />}
                        <span className="rounded bg-white px-1.5 font-mono text-[10px] text-slate-500 dark:bg-slate-900">{c.kind}</span>
                      </span>
                    </div>
                    <pre className="p-3 font-sans text-sm leading-relaxed whitespace-pre-wrap">{c.content}</pre>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function IconBtn({
  children,
  label,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`rounded-md p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800 ${danger ? "hover:text-rose-600" : ""}`}
    >
      {children}
    </button>
  );
}
