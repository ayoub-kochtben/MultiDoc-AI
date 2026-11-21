"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renders an answer; "[n]" citations become clickable chips. */
export function AnswerMarkdown({
  content,
  maxSource,
  onCite,
  activeSource,
}: {
  content: string;
  maxSource: number;
  onCite: (n: number) => void;
  activeSource?: number | null;
}) {
  const withLinks = content.replace(/\[(\d{1,2})\](?!\()/g, (m, n) =>
    Number(n) >= 1 && Number(n) <= maxSource ? `[\\[${n}\\]](#cite-${n})` : m,
  );
  return (
    <div className="prose-answer text-[15px]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              return (
                <button
                  type="button"
                  onClick={() => onCite(n)}
                  className={`mx-0.5 inline-flex h-5 min-w-5 -translate-y-px items-center justify-center rounded px-1 align-middle font-mono text-[11px] font-semibold transition-colors ${
                    activeSource === n
                      ? "bg-accent-600 text-white"
                      : "bg-accent-100 text-accent-700 hover:bg-accent-500 hover:text-white dark:bg-accent-500/20 dark:text-accent-100"
                  }`}
                  title={`Voir la source ${n}`}
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-accent-600 underline">
                {children}
              </a>
            );
          },
        }}
      >
        {withLinks}
      </ReactMarkdown>
    </div>
  );
}
