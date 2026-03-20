"use client";

import { useEffect, useMemo, useState } from "react";
import { BookMarked, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Dataset } from "@/types";

interface SemanticLayerManagerProps {
  workspaceId: string;
  datasets: Dataset[];
}

interface MetricRecord {
  id: string;
  name: string;
  definition: string;
  formula_sql: string;
  depends_on: string[];
  created_at: string;
}

export default function SemanticLayerManager({ workspaceId, datasets }: SemanticLayerManagerProps) {
  const [metrics, setMetrics] = useState<MetricRecord[]>([]);
  const [name, setName] = useState("");
  const [definition, setDefinition] = useState("");
  const [formulaSql, setFormulaSql] = useState("");
  const [dependsOn, setDependsOn] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const datasetNames = useMemo(() => datasets.map((d) => d.name), [datasets]);

  const loadMetrics = async () => {
    const { data } = await api.get<MetricRecord[]>(
      `/api/v1/ai/workspaces/${workspaceId}/semantic-layer/metrics`,
    );
    setMetrics(data);
  };

  useEffect(() => {
    void loadMetrics();
  }, [workspaceId]);

  const createMetric = async () => {
    if (!name.trim() || !definition.trim() || !formulaSql.trim()) return;
    setLoading(true);
    try {
      await api.post(`/api/v1/ai/workspaces/${workspaceId}/semantic-layer/metrics`, {
        name: name.trim(),
        definition: definition.trim(),
        formula_sql: formulaSql.trim(),
        depends_on: dependsOn,
      });
      setName("");
      setDefinition("");
      setFormulaSql("");
      setDependsOn([]);
      await loadMetrics();
    } finally {
      setLoading(false);
    }
  };

  const deleteMetric = async (metricId: string) => {
    await api.delete(`/api/v1/ai/workspaces/${workspaceId}/semantic-layer/metrics/${metricId}`);
    await loadMetrics();
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-forge-border bg-forge-surface p-4">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
          <BookMarked className="h-4 w-4 text-forge-accent" />
          Semantic Layer
        </h3>
        <p className="text-xs text-forge-muted">
          Define business metrics once so AI can reuse your KPI logic across analysis sessions.
        </p>
      </div>

      <div className="space-y-2 rounded-lg border border-forge-border bg-forge-surface p-4">
        <h4 className="text-sm font-semibold text-foreground">Define new metric</h4>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Metric name (e.g., churn_rate)" />
        <Textarea
          value={definition}
          onChange={(e) => setDefinition(e.target.value)}
          placeholder="Definition"
          className="min-h-[90px]"
        />
        <Textarea
          value={formulaSql}
          onChange={(e) => setFormulaSql(e.target.value)}
          placeholder="SQL formula"
          className="min-h-[90px] font-mono"
        />

        <div>
          <p className="mb-1 text-xs text-forge-muted">Depends on datasets</p>
          <div className="flex flex-wrap gap-1">
            {datasetNames.map((datasetName) => {
              const active = dependsOn.includes(datasetName);
              return (
                <button
                  key={datasetName}
                  onClick={() =>
                    setDependsOn((prev) =>
                      active ? prev.filter((x) => x !== datasetName) : [...prev, datasetName],
                    )
                  }
                  className={`rounded-full border px-2 py-0.5 text-xs ${
                    active
                      ? "border-forge-accent bg-forge-accent/10 text-forge-accent"
                      : "border-forge-border bg-forge-bg text-forge-muted"
                  }`}
                >
                  {datasetName}
                </button>
              );
            })}
          </div>
        </div>

        <Button onClick={createMetric} disabled={loading}>
          <Plus className="h-4 w-4" />
          {loading ? "Saving..." : "Save metric"}
        </Button>
      </div>

      {metrics.length === 0 ? (
        <div className="rounded-lg border border-dashed border-forge-border bg-forge-surface p-8 text-center text-sm text-forge-muted">
          No metrics defined yet. Add one to teach FORGE your business vocabulary.
        </div>
      ) : (
        <div className="space-y-2">
          {metrics.map((metric) => (
            <div key={metric.id} className="rounded-lg border border-forge-border bg-forge-surface p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-foreground">{metric.name}</p>
                  <p className="mt-1 text-xs text-forge-muted">{metric.definition}</p>
                  <pre className="mt-2 rounded border border-forge-border bg-forge-bg p-2 text-[11px] text-foreground">
                    {metric.formula_sql}
                  </pre>
                  {metric.depends_on?.length > 0 && (
                    <p className="mt-2 text-[11px] text-forge-muted">
                      Depends on: {metric.depends_on.join(", ")}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => void deleteMetric(metric.id)}
                  className="rounded-md p-1 text-forge-muted hover:bg-red-900/20 hover:text-red-400"
                  aria-label="Delete metric"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
