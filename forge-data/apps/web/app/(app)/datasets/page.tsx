"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Database, Plus } from "lucide-react";
import type { Dataset } from "@/types";
import ConnectorWizard from "@/components/data/ConnectorWizard";

export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);

  useEffect(() => {
    api
      .get<Dataset[]>("/api/v1/datasets")
      .then((r) => setDatasets(r.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
            <Database className="h-6 w-6 text-forge-accent" />
            Datasets
          </h1>
          <p className="mt-1 text-sm text-forge-muted">
            Connect and manage your data sources
          </p>
        </div>
        <button
          onClick={() => setWizardOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-md bg-forge-accent px-3 py-1.5 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim"
        >
          <Plus className="h-4 w-4" />
          Connect data
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 rounded-lg shimmer" />
          ))}
        </div>
      ) : datasets.length === 0 ? (
        <div className="rounded-lg border border-dashed border-forge-border p-12 text-center">
          <Database className="mx-auto mb-3 h-8 w-8 text-forge-muted" />
          <p className="text-sm text-forge-muted">
            No datasets yet.{" "}
            <button
              onClick={() => setWizardOpen(true)}
              className="text-forge-accent hover:underline"
            >
              Connect your first data source
            </button>
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {datasets.map((ds) => (
            <div
              key={ds.id}
              className="rounded-lg border border-forge-border bg-forge-surface px-4 py-3"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-foreground">{ds.name}</p>
                  <p className="text-xs text-forge-muted">
                    {ds.source_type} ·{" "}
                    {ds.row_count != null ? `${ds.row_count.toLocaleString()} rows` : "—"}
                  </p>
                </div>
                <p className="text-xs text-forge-muted">{formatDate(ds.updated_at)}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {wizardOpen && <ConnectorWizard onClose={() => setWizardOpen(false)} />}
    </div>
  );
}
