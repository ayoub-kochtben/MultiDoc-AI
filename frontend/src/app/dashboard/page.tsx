"use client";

import { useEffect, useState } from "react";
import { Database, FileStack, MessageSquare } from "lucide-react";
import { api, formatBytes, type Stats } from "@/lib/api";
import { Card, ErrorBanner, PageHeader, Spinner, TypeBadge } from "@/components/ui";

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Database; label: string; value: string | number; hint?: string }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <Icon size={14} /> {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-400">{hint}</div>}
    </Card>
  );
}

function Bars({ data, unit = "" }: { data: { label: React.ReactNode; key: string; value: number }[]; unit?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  if (!data.length) return <p className="text-sm text-slate-400">Pas encore de données.</p>;
  return (
    <ul className="space-y-2">
      {data.map((d) => (
        <li key={d.key} className="grid grid-cols-[minmax(0,10rem)_1fr_3rem] items-center gap-3 text-sm">
          <span className="truncate">{d.label}</span>
          <span className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <span className="block h-full rounded-full bg-accent-500" style={{ width: `${(d.value / max) * 100}%` }} />
          </span>
          <span className="text-right tabular-nums text-slate-500">
            {d.value}
            {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.stats().then(setStats).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Tableau de bord" subtitle="Statistiques de la base documentaire" />
      <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto p-6">
        {error && <ErrorBanner message={error} />}
        {!stats ? (
          !error && <Spinner size={22} />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <Stat icon={FileStack} label="Documents" value={stats.documents.total} hint={`${stats.documents.indexed} indexés · ${stats.documents.failed} en échec`} />
              <Stat icon={Database} label="Chunks indexés" value={stats.chunks.total} hint={formatBytes(stats.documents.total_bytes)} />
              <Stat icon={MessageSquare} label="Conversations" value={stats.conversations} hint={`${stats.answers.total} réponses générées`} />
            </div>
            <Card className="p-5">
              <h2 className="mb-4 text-sm font-semibold">Documents par format</h2>
              <Bars
                data={Object.entries(stats.documents.by_type)
                  .sort((a, b) => b[1] - a[1])
                  .map(([k, v]) => ({ key: k, label: <TypeBadge type={k} />, value: v }))}
              />
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
