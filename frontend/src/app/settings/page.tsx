"use client";

import { useEffect, useState } from "react";
import { RotateCcw, Save } from "lucide-react";
import { api, type RagSettings } from "@/lib/api";
import { Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";

type NumKey = { [K in keyof RagSettings]: RagSettings[K] extends number ? K : never }[keyof RagSettings];

const NUMBER_FIELDS: { key: NumKey; label: string; help: string; min: number; max: number; step: number; group: string }[] = [
  { key: "temperature", label: "Température", help: "0 = réponses factuelles et stables", min: 0, max: 2, step: 0.05, group: "llm" },
  { key: "num_ctx", label: "Fenêtre de contexte (tokens)", help: "Plus grand = plus de VRAM", min: 2048, max: 131072, step: 1024, group: "llm" },
  { key: "max_tokens", label: "Longueur max. de réponse", help: "Tokens générés au maximum", min: 64, max: 8192, step: 64, group: "llm" },
  { key: "history_turns", label: "Tours d'historique", help: "Échanges précédents fournis au modèle", min: 0, max: 20, step: 1, group: "llm" },
  { key: "vector_top_k", label: "Top-k vectoriel", help: "Candidats issus de pgvector (cosinus)", min: 1, max: 200, step: 1, group: "retrieval" },
  { key: "keyword_top_k", label: "Top-k mots-clés", help: "Candidats issus de la recherche plein texte", min: 0, max: 200, step: 1, group: "retrieval" },
  { key: "rerank_candidates", label: "Candidats rerankés", help: "Passages évalués par BGE Reranker", min: 1, max: 100, step: 1, group: "retrieval" },
  { key: "final_top_n", label: "Passages envoyés au LLM", help: "Nombre maximal de sources", min: 1, max: 30, step: 1, group: "retrieval" },
  { key: "min_rerank_score", label: "Score de rerank minimal", help: "Les 3 meilleurs passages sont toujours conservés", min: 0, max: 1, step: 0.01, group: "retrieval" },
  { key: "chunk_size", label: "Taille des chunks (caractères)", help: "S'applique aux prochaines indexations", min: 200, max: 6000, step: 50, group: "chunking" },
  { key: "chunk_overlap", label: "Chevauchement (caractères)", help: "S'applique aux prochaines indexations", min: 0, max: 1000, step: 10, group: "chunking" },
];

export default function SettingsPage() {
  const [s, setS] = useState<RagSettings | null>(null);
  const [models, setModels] = useState<{ name: string; parameters: string }[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.settings().then(setS).catch((e) => setError(e.message));
    api.models().then(setModels).catch(() => {});
  }, []);

  const save = async () => {
    if (!s) return;
    setSaving(true);
    setError(null);
    try {
      setS(await api.saveSettings(s));
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const group = (g: string) =>
    NUMBER_FIELDS.filter((f) => f.group === g).map((f) => (
      <label key={f.key} className="block">
        <span className="text-sm font-medium">{f.label}</span>
        <input
          type="number"
          min={f.min}
          max={f.max}
          step={f.step}
          value={s ? s[f.key] : ""}
          onChange={(e) => s && setS({ ...s, [f.key]: Number(e.target.value) })}
          className="mt-1 h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm tabular-nums outline-none focus:border-accent-500 dark:border-slate-700 dark:bg-slate-800"
        />
        <span className="mt-1 block text-xs text-slate-500">{f.help}</span>
      </label>
    ));

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Paramètres"
        subtitle="Modèles et moteur RAG"
        actions={
          <>
            <Button variant="secondary" onClick={async () => setS(await api.resetSettings())}>
              <RotateCcw size={14} /> Valeurs par défaut
            </Button>
            <Button onClick={save} loading={saving} disabled={!s}>
              <Save size={14} /> {saved ? "Enregistré ✓" : "Enregistrer"}
            </Button>
          </>
        }
      />
      <div className="scrollbar-thin flex-1 overflow-y-auto p-6">
        <div className="mx-auto max-w-4xl space-y-4">
          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
          {!s ? (
            <Spinner size={22} />
          ) : (
            <>
              <Card className="p-5">
                <h2 className="mb-4 text-sm font-semibold">Modèle de langage (Ollama)</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block sm:col-span-2">
                    <span className="text-sm font-medium">Modèle</span>
                    <select
                      value={s.llm_model}
                      onChange={(e) => setS({ ...s, llm_model: e.target.value })}
                      className="mt-1 h-9 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-accent-500 dark:border-slate-700 dark:bg-slate-800"
                    >
                      {!models.some((m) => m.name === s.llm_model) && <option value={s.llm_model}>{s.llm_model}</option>}
                      {models.map((m) => (
                        <option key={m.name} value={m.name}>
                          {m.name} {m.parameters ? `(${m.parameters})` : ""}
                        </option>
                      ))}
                    </select>
                    <span className="mt-1 block text-xs text-slate-500">
                      Modèles installés localement. Pour en ajouter : <code className="font-mono">ollama pull qwen3:8b</code>
                    </span>
                  </label>
                  {group("llm")}
                </div>
              </Card>
              <Card className="p-5">
                <h2 className="mb-4 text-sm font-semibold">Recherche hybride et reranking</h2>
                <div className="grid gap-4 sm:grid-cols-2">{group("retrieval")}</div>
              </Card>
              <Card className="p-5">
                <h2 className="mb-4 text-sm font-semibold">Découpage (chunking)</h2>
                <div className="grid gap-4 sm:grid-cols-2">{group("chunking")}</div>
              </Card>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
