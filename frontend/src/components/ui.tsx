"use client";

import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "primary",
  size = "md",
  loading,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}) {
  const v = {
    primary: "bg-accent-600 text-white hover:bg-accent-700 disabled:bg-accent-500/50",
    secondary:
      "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
    ghost: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  }[variant];
  const s = size === "sm" ? "h-8 px-2.5 text-xs gap-1.5" : "h-9 px-3.5 text-sm gap-2";
  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${v} ${s} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 ${className}`}>{children}</div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-6 py-4 dark:border-slate-800 dark:bg-slate-900">
      <div>
        <h1 className="text-lg font-semibold">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function ErrorBanner({ message, onClose }: { message: string; onClose?: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
      <span>{message}</span>
      {onClose && (
        <button onClick={onClose} className="text-rose-500 hover:text-rose-700" aria-label="Fermer">
          ×
        </button>
      )}
    </div>
  );
}

const TYPE_COLORS: Record<string, string> = {
  pdf: "bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  docx: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  xlsx: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  csv: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  pptx: "bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300",
  html: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
  json: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  xml: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  eml: "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-300",
  image: "bg-pink-100 text-pink-700 dark:bg-pink-500/15 dark:text-pink-300",
  table: "bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300",
};

export function TypeBadge({ type }: { type: string }) {
  return (
    <span
      className={`inline-flex h-5 min-w-10 items-center justify-center rounded px-1.5 font-mono text-[10px] font-semibold uppercase ${
        TYPE_COLORS[type] || "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
      }`}
    >
      {type === "image" ? "img" : type === "table" ? "calc" : type}
    </span>
  );
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin text-slate-400" />;
}
