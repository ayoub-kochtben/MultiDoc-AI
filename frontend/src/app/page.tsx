"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowUp, Calculator, FileText, Loader2, MessageSquarePlus, Square } from "lucide-react";
import { api, streamChat, type Conversation, type DocumentItem, type Message, type Source } from "@/lib/api";
import { AnswerMarkdown } from "@/components/chat/Markdown";
import { SourcePanel } from "@/components/chat/SourcePanel";
import { DocumentPicker } from "@/components/chat/DocumentPicker";
import { ConversationList } from "@/components/chat/ConversationList";
import { ErrorBanner, TypeBadge } from "@/components/ui";

interface UiMessage extends Omit<Message, "id" | "created_at"> {
  id: string;
  pending?: boolean;
  status?: string;
  error?: string;
}

const SUGGESTIONS = [
  "Résume les points clés de mes documents.",
  "Quel est le total des ventes dans le tableau Excel ?",
  "Y a-t-il des contradictions entre les documents ?",
];

export default function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [activeSource, setActiveSource] = useState<{ msg: string; n: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const loadConversations = useCallback(() => api.conversations().then(setConversations).catch((e) => setError(e.message)), []);

  useEffect(() => {
    loadConversations();
    api.documents().then(setDocuments).catch((e) => setError(e.message));
  }, [loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const openConversation = async (id: string) => {
    if (streaming) return;
    try {
      const c = await api.conversation(id);
      setConversationId(id);
      setMessages(c.messages);
      setSelectedDocs(c.document_ids.filter((d) => documents.some((doc) => doc.id === d)));
      setActiveSource(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const newConversation = () => {
    if (streaming) return;
    setConversationId(null);
    setMessages([]);
    setActiveSource(null);
    textareaRef.current?.focus();
  };

  const updateLast = (fn: (m: UiMessage) => UiMessage) =>
    setMessages((ms) => (ms.length ? [...ms.slice(0, -1), fn(ms[ms.length - 1])] : ms));

  const send = async (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || streaming) return;
    setInput("");
    setError(null);
    setStreaming(true);
    const now = Date.now();
    setMessages((ms) => [
      ...ms,
      { id: `u-${now}`, role: "user", content: question, sources: [], metadata: {} },
      { id: `a-${now}`, role: "assistant", content: "", sources: [], metadata: {}, pending: true, status: "Préparation…" },
    ]);
    const controller = new AbortController();
    abortRef.current = controller;
    let convId = conversationId;
    try {
      await streamChat(
        { conversation_id: conversationId, message: question, document_ids: selectedDocs },
        (ev) => {
          switch (ev.event) {
            case "conversation":
              convId = ev.data.conversation_id;
              setConversationId(convId);
              break;
            case "status":
              updateLast((m) => ({ ...m, status: ev.data.message }));
              break;
            case "sources":
              updateLast((m) => ({ ...m, sources: ev.data }));
              break;
            case "token":
              updateLast((m) => ({ ...m, content: m.content + ev.data, status: undefined }));
              break;
            case "done":
              updateLast((m) => ({ ...m, id: ev.data.message_id, metadata: ev.data.meta, pending: false }));
              break;
            case "error":
              updateLast((m) => ({ ...m, pending: false, error: ev.data.message }));
              break;
          }
        },
        controller.signal,
      );
    } catch (e) {
      const aborted = (e as Error).name === "AbortError";
      updateLast((m) => ({ ...m, pending: false, error: aborted ? undefined : (e as Error).message, status: undefined,
        content: aborted && !m.content ? "_Génération interrompue._" : m.content }));
    } finally {
      updateLast((m) => ({ ...m, pending: false, status: undefined }));
      setStreaming(false);
      abortRef.current = null;
      loadConversations();
    }
  };

  const selected: Source | null = activeSource
    ? (messages.find((m) => m.id === activeSource.msg)?.sources.find((s) => s.n === activeSource.n) ?? null)
    : null;
  const indexedCount = documents.filter((d) => d.status === "indexed").length;

  return (
    <div className="flex h-full">
      <ConversationList
        conversations={conversations}
        activeId={conversationId}
        onSelect={openConversation}
        onNew={newConversation}
        onDelete={async (id) => {
          await api.deleteConversation(id).catch((e) => setError(e.message));
          if (id === conversationId) newConversation();
          loadConversations();
        }}
        onRename={async (id, title) => {
          await api.renameConversation(id, title).catch((e) => setError(e.message));
          loadConversations();
        }}
      />

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 dark:border-slate-800 dark:bg-slate-900">
          <h1 className="truncate text-sm font-semibold">
            {conversations.find((c) => c.id === conversationId)?.title ?? "Nouvelle conversation"}
          </h1>
          <button onClick={newConversation} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden" aria-label="Nouvelle conversation">
            <MessageSquarePlus size={18} />
          </button>
        </header>

        <div className="scrollbar-thin flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
            {messages.length === 0 && (
              <div className="pt-16 text-center">
                <h2 className="text-2xl font-semibold">Interrogez vos documents</h2>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
                  Les réponses s&apos;appuient uniquement sur le contenu de vos fichiers, avec des citations vérifiables.
                </p>
                {indexedCount === 0 ? (
                  <Link href="/documents" className="mt-6 inline-flex items-center gap-2 rounded-lg bg-accent-600 px-4 py-2 text-sm font-medium text-white hover:bg-accent-700">
                    <FileText size={16} /> Importer des documents
                  </Link>
                ) : (
                  <div className="mt-8 flex flex-wrap justify-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => send(s)}
                        className="rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-sm text-slate-600 hover:border-accent-500 hover:text-accent-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-600 px-4 py-2.5 text-[15px] whitespace-pre-wrap text-white">
                    {m.content}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="space-y-2">
                  {m.status && (
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                      <Loader2 size={14} className="animate-spin" /> {m.status}
                    </div>
                  )}
                  {m.content && (
                    <div className={m.pending ? "caret" : ""}>
                      <AnswerMarkdown
                        content={m.content}
                        maxSource={m.sources.length}
                        onCite={(n) => setActiveSource({ msg: m.id, n })}
                        activeSource={activeSource?.msg === m.id ? activeSource.n : null}
                      />
                    </div>
                  )}
                  {m.error && <ErrorBanner message={m.error} />}
                  {m.sources.length > 0 && !m.pending && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {m.sources.map((s) => {
                        const cited = ((m.metadata.cited as number[]) || []).includes(s.n);
                        return (
                          <button
                            key={s.n}
                            onClick={() => setActiveSource({ msg: m.id, n: s.n })}
                            className={`flex max-w-64 items-center gap-1.5 rounded-lg border px-2 py-1 text-left text-xs transition-colors ${
                              activeSource?.msg === m.id && activeSource.n === s.n
                                ? "border-accent-500 bg-accent-50 dark:bg-accent-500/15"
                                : cited
                                  ? "border-slate-300 bg-white hover:border-accent-500 dark:border-slate-600 dark:bg-slate-900"
                                  : "border-slate-200 bg-white opacity-60 hover:opacity-100 dark:border-slate-800 dark:bg-slate-900"
                            }`}
                            title={`${s.filename} — ${s.location}${cited ? "" : " (non cité)"}`}
                          >
                            <span className="font-mono font-semibold text-accent-600">{s.n}</span>
                            {s.type === "computation" ? <Calculator size={12} className="text-teal-600" /> : <TypeBadge type={s.file_type} />}
                            <span className="truncate">{s.filename}</span>
                            {s.suspicious && <AlertTriangle size={12} className="shrink-0 text-amber-500" />}
                          </button>
                        );
                      })}
                    </div>
                  )}
                  {!m.pending && typeof m.metadata.total_s === "number" && (
                    <div className="text-[11px] text-slate-400">
                      {(m.metadata.total_s as number).toFixed(1)} s
                      {typeof m.metadata.first_token_s === "number" && ` · 1er token ${(m.metadata.first_token_s as number).toFixed(1)} s`}
                      {typeof m.metadata.model === "string" && ` · ${m.metadata.model}`}
                      {typeof m.metadata.rewritten_question === "string" && ` · recherche : « ${m.metadata.rewritten_question} »`}
                    </div>
                  )}
                </div>
              ),
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
          <div className="mx-auto max-w-3xl space-y-2">
            {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
            <div className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-accent-500 dark:border-slate-700 dark:bg-slate-800">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={Math.min(6, Math.max(1, input.split("\n").length))}
                placeholder="Posez une question sur vos documents…"
                title="Entrée pour envoyer, Maj+Entrée pour un saut de ligne"
                className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] outline-none placeholder:text-slate-400"
              />
              {streaming ? (
                <button onClick={() => abortRef.current?.abort()} className="grid size-9 place-items-center rounded-xl bg-slate-700 text-white hover:bg-slate-800" aria-label="Arrêter">
                  <Square size={14} fill="currentColor" />
                </button>
              ) : (
                <button
                  onClick={() => send()}
                  disabled={!input.trim()}
                  className="grid size-9 place-items-center rounded-xl bg-accent-600 text-white hover:bg-accent-700 disabled:opacity-40"
                  aria-label="Envoyer"
                >
                  <ArrowUp size={18} />
                </button>
              )}
            </div>
            <div className="flex items-center justify-between gap-2">
              <DocumentPicker documents={documents} selected={selectedDocs} onChange={setSelectedDocs} />
              <span className="hidden text-[11px] text-slate-400 sm:block">Réponses générées localement à partir de vos documents uniquement.</span>
            </div>
          </div>
        </div>
      </section>

      {selected && <SourcePanel source={selected} onClose={() => setActiveSource(null)} />}
    </div>
  );
}
