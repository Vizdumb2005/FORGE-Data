"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useWorkspace } from "@/lib/hooks/useWorkspace";
import { listDatasets } from "@/lib/api/datasets";
import { formatDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import ConnectorWizard from "@/components/data/ConnectorWizard";
import DatasetDetailPanel from "@/components/data/DatasetDetailPanel";
import type { Dataset, SourceType } from "@/types";
import {
  Database,
  Plus,
  Search,
  FileSpreadsheet,
  HardDrive,
  Snowflake,
  RefreshCw,
} from "lucide-react";

// ── Source type metadata ─────────────────────────────────────────────────────

const SOURCE_META: Record<string, { icon: React.ReactNode; color: string }> = {
  csv: { icon: <FileSpreadsheet className="h-4 w-4" />, color: "text-green-400" },
  parquet: { icon: <FileSpreadsheet className="h-4 w-4" />, color: "text-blue-400" },
  json: { icon: <FileSpreadsheet className="h-4 w-4" />, color: "text-yellow-400" },
  excel: { icon: <FileSpreadsheet className="h-4 w-4" />, color: "text-emerald-400" },
  postgres: { icon: <Database className="h-4 w-4" />, color: "text-sky-400" },
  mysql: { icon: <Database className="h-4 w-4" />, color: "text-orange-400" },
  snowflake: { icon: <Snowflake className="h-4 w-4" />, color: "text-cyan-400" },
  s3: { icon: <HardDrive className="h-4 w-4" />, color: "text-amber-400" },
  bigquery: { icon: <Database className="h-4 w-4" />, color: "text-indigo-400" },
};

const SOURCE_TYPE_OPTIONS: SourceType[] = [
  "csv", "parquet", "json", "excel", "postgres", "mysql", "snowflake", "s3",
];

export default function DatasetsPage() {
  const { workspaces, loading: wsLoading } = useWorkspace();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [lineageWorkspaceId, setLineageWorkspaceId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("");

  // Auto-select first workspace
  useEffect(() => {
    if (!selectedWorkspaceId && workspaces.length > 0) {
      setSelectedWorkspaceId(workspaces[0].id);
    }
  }, [workspaces, selectedWorkspaceId]);

  // Fetch datasets when workspace changes
  const fetchDatasets = useCallback(async () => {
    if (!selectedWorkspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await listDatasets(selectedWorkspaceId);
      setDatasets(data);
    } catch {
      setError("Failed to load datasets");
    } finally {
      setLoading(false);
    }
  }, [selectedWorkspaceId]);

  useEffect(() => {
    fetchDatasets();
  }, [fetchDatasets]);

  // Filtered datasets
  const filtered = useMemo(() => {
    let result = datasets;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter((d) => d.name.toLowerCase().includes(q));
    }
    if (filterType) {
      result = result.filter((d) => d.source_type === filterType);
    }
    return result;
  }, [datasets, search, filterType]);

  const handleWizardSuccess = () => {
    fetchDatasets();
  };

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
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
        <div className="flex items-center gap-2">
          <button
            onClick={fetchDatasets}
            className="rounded-md border border-forge-border p-2 text-forge-muted hover:bg-forge-border/50 hover:text-foreground"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setWizardOpen(true)}
            disabled={!selectedWorkspaceId}
            className="inline-flex items-center gap-1.5 rounded-md bg-forge-accent px-3 py-1.5 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-40"
          >
            <Plus className="h-4 w-4" />
            Add Dataset
          </button>
        </div>
      </div>

      {/* Workspace selector + Filter bar */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* Workspace picker */}
        <select
          value={selectedWorkspaceId}
          onChange={(e) => setSelectedWorkspaceId(e.target.value)}
          className="rounded-md border border-forge-border bg-forge-bg px-3 py-1.5 text-sm text-foreground focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
        >
          {wsLoading && <option>Loading…</option>}
          {workspaces.map((ws) => (
            <option key={ws.id} value={ws.id}>
              {ws.name}
            </option>
          ))}
        </select>

        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-forge-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search datasets…"
            className="w-full rounded-md border border-forge-border bg-forge-bg py-1.5 pl-9 pr-3 text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
          />
        </div>

        {/* Type filter */}
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="rounded-md border border-forge-border bg-forge-bg px-3 py-1.5 text-sm text-foreground focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
        >
          <option value="">All types</option>
          {SOURCE_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* Content */}
      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-32 rounded-lg" />
          ))}
        </div>
      ) : error ? (
        <div className="rounded-lg border border-dashed border-red-500/30 p-12 text-center">
          <p className="text-sm text-red-400">{error}</p>
          <button
            onClick={fetchDatasets}
            className="mt-2 text-xs text-forge-accent hover:underline"
          >
            Retry
          </button>
        </div>
      ) : !selectedWorkspaceId ? (
        <div className="rounded-lg border border-dashed border-forge-border p-12 text-center">
          <Database className="mx-auto mb-3 h-8 w-8 text-forge-muted" />
          <p className="text-sm text-forge-muted">
            Create a workspace first to start adding datasets
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed border-forge-border p-12 text-center">
          <Database className="mx-auto mb-3 h-8 w-8 text-forge-muted" />
          <p className="text-sm text-forge-muted">
            {datasets.length === 0 ? (
              <>
                No datasets yet.{" "}
                <button
                  onClick={() => setWizardOpen(true)}
                  className="text-forge-accent hover:underline"
                >
                  Connect your first data source
                </button>
              </>
            ) : (
              "No datasets match your filters"
            )}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((ds) => (
            <DatasetCard
              key={ds.id}
              dataset={ds}
              onClick={() => setSelectedDatasetId(ds.id)}
            />
          ))}
        </div>
      )}

      {/* Connector wizard */}
      {wizardOpen && selectedWorkspaceId && (
        <ConnectorWizard
          workspaceId={selectedWorkspaceId}
          onClose={() => setWizardOpen(false)}
          onSuccess={handleWizardSuccess}
        />
      )}

      {/* Dataset detail panel */}
      {selectedDatasetId && selectedWorkspaceId && (
        <DatasetDetailPanel
          workspaceId={selectedWorkspaceId}
          datasetId={selectedDatasetId}
          open={!!selectedDatasetId}
          onClose={() => setSelectedDatasetId(null)}
          onOpenLineage={() => setLineageWorkspaceId(selectedWorkspaceId)}
          onDeleted={() => {
            setSelectedDatasetId(null);
            fetchDatasets();
          }}
        />
      )}
      {lineageWorkspaceId ? (
        <button
          className="fixed bottom-4 right-4 rounded bg-forge-accent px-3 py-2 text-xs font-semibold text-forge-bg"
          onClick={() => {
            window.location.href = `/workspace/${lineageWorkspaceId}`;
          }}
        >
          Open Workspace Lineage
        </button>
      ) : null}
    </div>
  );
}

// ── Dataset card ─────────────────────────────────────────────────────────────

function DatasetCard({
  dataset,
  onClick,
}: {
  dataset: Dataset;
  onClick: () => void;
}) {
  const meta = SOURCE_META[dataset.source_type] ?? {
    icon: <Database className="h-4 w-4" />,
    color: "text-forge-muted",
  };

  return (
    <button
      onClick={onClick}
      className="group block w-full rounded-lg border border-forge-border bg-forge-surface p-4 text-left transition-all duration-200 hover:border-forge-accent/30 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-forge-accent/5"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <div className={meta.color}>{meta.icon}</div>
          <h3 className="text-sm font-medium text-foreground group-hover:text-forge-accent">
            {dataset.name}
          </h3>
        </div>
        <Badge variant="outline" className="font-mono text-[10px]">
          v{dataset.version}
        </Badge>
      </div>

      <div className="mt-3 flex items-center gap-3 text-xs text-forge-muted">
        <span>{dataset.source_type}</span>
        <span className="text-forge-border">·</span>
        <span>
          {dataset.row_count != null
            ? `${dataset.row_count.toLocaleString()} rows`
            : "—"}
        </span>
        <span className="text-forge-border">·</span>
        <span>
          {dataset.column_count != null
            ? `${dataset.column_count} cols`
            : "—"}
        </span>
      </div>

      <p className="mt-2 text-[10px] text-forge-muted/70">
        Updated {formatDate(dataset.updated_at)}
      </p>
    </button>
  );
}
