"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { FlaskConical, Plus } from "lucide-react";
import type { Experiment } from "@/types";

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Experiment[]>("/api/v1/experiments/")
      .then((r) => setExperiments(r.data))
      .catch(() => setExperiments([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <FlaskConical className="h-6 w-6 text-forge-accent" />
            Experiments
          </h1>
          <p className="mt-1 text-sm text-forge-muted">
            Track ML runs and metrics via MLflow
          </p>
        </div>
        <button className="inline-flex items-center gap-1.5 rounded-md bg-forge-accent px-3 py-1.5 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim">
          <Plus className="h-4 w-4" />
          New experiment
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg shimmer" />
          ))}
        </div>
      ) : experiments.length === 0 ? (
        <div className="rounded-lg border border-dashed border-forge-border p-12 text-center">
          <FlaskConical className="mx-auto mb-3 h-8 w-8 text-forge-muted" />
          <p className="text-sm text-forge-muted">No experiments yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {experiments.map((exp) => (
            <div
              key={exp.id}
              className="rounded-lg border border-forge-border bg-forge-surface px-4 py-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">{exp.name}</p>
                  <p className="text-xs text-forge-muted">
                    {exp.description ?? "No description"}
                  </p>
                </div>
                <p className="text-xs text-forge-muted">
                  {formatDate(exp.updated_at)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
