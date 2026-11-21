export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type DocStatus = "queued" | "parsing" | "chunking" | "embedding" | "indexed" | "failed";
export const PROCESSING: DocStatus[] = ["queued", "parsing", "chunking", "embedding"];

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  mime_type: string | null;
  sha256: string;
  size_bytes: number;
  status: DocStatus;
  progress: number;
  stage_detail: string | null;
  error: string | null;
  num_chunks: number;
  num_pages: number | null;
  parser: string | null;
  metadata: Record<string, unknown>;
  processing_seconds: number | null;
  created_at: string;
  indexed_at: string | null;
}

export interface UploadResult {
  filename: string;
  status: "accepted" | "duplicate" | "rejected";
  document: DocumentItem | null;
  detail: string | null;
}

export interface ChunkItem {
  id: string;
  chunk_index: number;
  kind: string;
  content: string;
  location: string;
  metadata: Record<string, unknown>;
  suspicious: boolean;
}

export interface Source {
  n: number;
  type: "passage" | "computation";
  chunk_id?: string;
  document_id: string;
  filename: string;
  file_type: string;
  location: string;
  excerpt: string;
  content?: string;
  suspicious: boolean;
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  explanation?: string;
  scores: { rerank?: number | null; vector?: number | null; keyword?: number | null; rrf?: number };
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  document_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface RagSettings {
  llm_model: string;
  temperature: number;
  num_ctx: number;
  max_tokens: number;
  chunk_size: number;
  chunk_overlap: number;
  vector_top_k: number;
  keyword_top_k: number;
  rerank_enabled: boolean;
  rerank_candidates: number;
  final_top_n: number;
  min_rerank_score: number;
  table_qa_enabled: boolean;
  query_rewrite: boolean;
  history_turns: number;
}

export interface Stats {
  documents: {
    total: number;
    by_type: Record<string, number>;
    by_status: Record<string, number>;
    total_bytes: number;
    avg_processing_s: number | null;
    indexed: number;
    failed: number;
  };
  chunks: { total: number; suspicious: number };
  tables: number;
  conversations: number;
  messages: number;
  answers: {
    total: number;
    avg_total_s: number | null;
    avg_first_token_s: number | null;
    avg_retrieval_s: number | null;
    avg_rerank_s: number | null;
    not_found: number;
  };
  top_documents: { filename: string; citations: number }[];
  activity: { day: string; questions: number }[];
}

export interface Health {
  status: string;
  database: string;
  ollama: string;
  reranker: { loaded: boolean; error: string | null; load_seconds: number | null; model: string };
  models?: { llm: string; llm_available: boolean; embedding: string; embedding_available: boolean };
  ocr_languages: string[] | string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Backend injoignable (${API_URL}). Est-il démarré ?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  documents: () => request<DocumentItem[]>("/api/documents"),
  formats: () => request<{ extensions: string[] }>("/api/documents/formats"),
  chunks: (id: string) => request<ChunkItem[]>(`/api/documents/${id}/chunks`),
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  reindex: (id: string) => request<DocumentItem>(`/api/documents/${id}/reindex`, { method: "POST" }),
  fileUrl: (id: string) => `${API_URL}/api/documents/${id}/file`,
  conversations: () => request<Conversation[]>("/api/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  renameConversation: (id: string, title: string) => request<Conversation>(`/api/conversations/${id}`, json("PATCH", { title })),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: "DELETE" }),
  settings: () => request<RagSettings>("/api/settings"),
  saveSettings: (s: RagSettings) => request<RagSettings>("/api/settings", json("PUT", s)),
  resetSettings: () => request<RagSettings>("/api/settings/reset", { method: "POST" }),
  models: () => request<{ name: string; size: number; family: string; parameters: string }[]>("/api/models"),
  stats: () => request<Stats>("/api/stats"),
};

/** Upload with real progress reporting (XMLHttpRequest exposes upload progress, fetch does not). */
export function uploadFiles(files: File[], onProgress: (fraction: number) => void): Promise<UploadResult[]> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/api/documents/upload`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else {
        let detail = xhr.statusText;
        try {
          detail = JSON.parse(xhr.responseText).detail;
        } catch {}
        reject(new ApiError(xhr.status, detail || "Échec de l'envoi"));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, `Backend injoignable (${API_URL}).`));
    xhr.send(form);
  });
}

export type ChatEvent =
  | { event: "conversation"; data: { conversation_id: string } }
  | { event: "status"; data: { stage: string; message: string } }
  | { event: "sources"; data: Source[] }
  | { event: "token"; data: string }
  | { event: "done"; data: { message_id: string; meta: Record<string, unknown> } }
  | { event: "error"; data: { message: string } };

/** POST /api/chat and parse the Server-Sent Events stream. */
export async function streamChat(
  body: { conversation_id: string | null; message: string; document_ids: string[] },
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/chat`, { ...json("POST", body), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, `Backend injoignable (${API_URL}).`);
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (dataLines.length) onEvent({ event, data: JSON.parse(dataLines.join("\n")) } as ChatEvent);
    }
  }
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} o`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} Ko`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} Mo`;
  return `${(n / 1024 ** 3).toFixed(2)} Go`;
}
