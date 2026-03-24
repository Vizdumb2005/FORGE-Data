"use client";

import { useEffect, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import DataGrid from "@/components/data/DataGrid";
import ProfileChart from "@/components/data/ProfileChart";
import {
  getDataset,
  listVersions,
  diffVersions,
  rollbackVersion,
  createVersion,
  runQualityCheck,
  getQualityReports,
  saveRuleset,
  executeQuery,
  maskDatasetPII,
  acknowledgeDatasetPII,
} from "@/lib/api/datasets";
import { formatDate } from "@/lib/utils";
import type {
  Dataset,
  DatasetVersion,
  VersionDiff,
  QualityReport,
  QualityRule,
  ColumnProfile,
} from "@/types";
import {
  RefreshCw,
  Upload,
  GitBranch,
  ArrowDownToLine,
  Plus,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  ShieldAlert,
} from "lucide-react";
import { useToast } from "@/components/ui/use-toast";

interface DatasetDetailPanelProps {
  workspaceId: string;
  datasetId: string;
  open: boolean;
  onClose: () => void;
  onDeleted?: () => void;
  onOpenLineage?: () => void;
}

export default function DatasetDetailPanel({
  workspaceId,
  datasetId,
  open,
  onClose,
  onOpenLineage,
}: DatasetDetailPanelProps) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!open || !datasetId) return;
    setLoading(true);
    getDataset(workspaceId, datasetId)
      .then(setDataset)
      .finally(() => setLoading(false));
  }, [open, workspaceId, datasetId]);

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="flex flex-col overflow-hidden">
        <SheetHeader>
          {loading ? (
            <>
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-32" />
            </>
          ) : dataset ? (
            <>
              <SheetTitle>{dataset.name}</SheetTitle>
              <SheetDescription>
                {dataset.source_type} · v{dataset.version} ·{" "}
                {dataset.row_count?.toLocaleString() ?? "—"} rows
              </SheetDescription>
            </>
          ) : (
            <SheetTitle>Dataset not found</SheetTitle>
          )}
        </SheetHeader>

        {dataset && (
          <Tabs defaultValue="overview" className="flex flex-1 flex-col overflow-hidden px-6 pb-4">
            <TabsList className="mb-3 w-full justify-start bg-forge-bg">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="schema">Schema</TabsTrigger>
              <TabsTrigger value="quality">Quality</TabsTrigger>
              <TabsTrigger value="versions">Versions</TabsTrigger>
              <TabsTrigger value="preview">Preview</TabsTrigger>
              {onOpenLineage ? <TabsTrigger value="lineage" onClick={onOpenLineage}>Lineage</TabsTrigger> : null}
            </TabsList>

            <div className="flex-1 overflow-auto">
              <TabsContent value="overview">
                <OverviewTab dataset={dataset} />
              </TabsContent>
              <TabsContent value="schema">
                <SchemaTab dataset={dataset} />
              </TabsContent>
              <TabsContent value="quality">
                <QualityTab workspaceId={workspaceId} dataset={dataset} />
              </TabsContent>
              <TabsContent value="versions">
                <VersionsTab workspaceId={workspaceId} dataset={dataset} />
              </TabsContent>
              <TabsContent value="preview">
                <PreviewTab workspaceId={workspaceId} dataset={dataset} />
              </TabsContent>
            </div>
          </Tabs>
        )}
      </SheetContent>
    </Sheet>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab: Overview
// ═══════════════════════════════════════════════════════════════════════════════

function OverviewTab({ dataset }: { dataset: Dataset }) {
  const profile = dataset.profile_data;
  const columns: ColumnProfile[] = profile?.columns ?? [];

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Rows" value={dataset.row_count?.toLocaleString() ?? "—"} />
        <StatCard label="Columns" value={String(dataset.column_count ?? "—")} />
        <StatCard
          label="Size"
          value={
            dataset.size_bytes
              ? dataset.size_bytes > 1048576
                ? `${(dataset.size_bytes / 1048576).toFixed(1)} MB`
                : `${(dataset.size_bytes / 1024).toFixed(1)} KB`
              : "—"
          }
        />
      </div>

      {/* Null summary bar */}
      {columns.length > 0 && profile && (
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
            Null % per column
          </p>
          <div className="space-y-1">
            {columns.map((col) => {
              const pct =
                profile.row_count > 0
                  ? (col.null_count / profile.row_count) * 100
                  : 0;
              return (
                <div key={col.name} className="flex items-center gap-2">
                  <span className="w-24 truncate font-mono text-[10px] text-forge-muted">
                    {col.name}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-forge-border">
                    <div
                      className={`h-full rounded-full ${
                        pct > 50
                          ? "bg-red-500"
                          : pct > 10
                            ? "bg-yellow-500"
                            : "bg-forge-accent"
                      }`}
                      style={{ width: `${Math.max(pct, 0.5)}%` }}
                    />
                  </div>
                  <span className="w-12 text-right font-mono text-[10px] text-forge-muted">
                    {pct.toFixed(1)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Profile charts */}
      {columns.length > 0 && profile && (
        <div>
          <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
            Column profiles
          </p>
          <div className="space-y-3">
            {columns.map((col) => (
              <ProfileChart
                key={col.name}
                column={col}
                totalRows={profile.row_count}
              />
            ))}
          </div>
        </div>
      )}

      {columns.length === 0 && (
        <div className="rounded-lg border border-dashed border-forge-border py-8 text-center text-sm text-forge-muted">
          No profile data available. Upload a file to generate profiles.
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
      <p className="font-mono text-[10px] uppercase tracking-wider text-forge-muted">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-foreground">{value}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab: Schema
// ═══════════════════════════════════════════════════════════════════════════════

function SchemaTab({ dataset }: { dataset: Dataset }) {
  const schema = dataset.schema_snapshot ?? [];
  const { toast } = useToast();
  const [localDataset, setLocalDataset] = useState(dataset);
  const piiColumns = localDataset.metadata_info?.pii_columns ?? {};
  const piiDetected = Boolean(localDataset.metadata_info?.pii_detected);
  const piiAcknowledged = Boolean(localDataset.metadata_info?.pii_acknowledged);

  useEffect(() => {
    setLocalDataset(dataset);
  }, [dataset]);

  if (schema.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-forge-border py-8 text-center text-sm text-forge-muted">
        No schema information available
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {piiDetected && !piiAcknowledged ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-2 text-sm font-medium text-amber-200">
                <ShieldAlert className="h-4 w-4" />
                ⚠️ PII Detected: This dataset contains potential personally identifiable information
              </p>
              <p className="mt-1 text-xs text-amber-100/80">
                {Object.entries(piiColumns).map(([col, types]) => `${col} (${types.join(", ")})`).join(" · ")}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="rounded border border-amber-300/50 px-2 py-1 text-xs text-amber-100 hover:bg-amber-400/20"
                onClick={async () => {
                  try {
                    const masked = await maskDatasetPII(localDataset.workspace_id, localDataset.id);
                    setLocalDataset(masked);
                    toast({ title: "PII masked successfully" });
                  } catch {
                    toast({ title: "Failed to mask PII", variant: "destructive" });
                  }
                }}
              >
                Mask PII
              </button>
              <button
                className="rounded border border-amber-300/50 px-2 py-1 text-xs text-amber-100 hover:bg-amber-400/20"
                onClick={async () => {
                  try {
                    const updated = await acknowledgeDatasetPII(localDataset.workspace_id, localDataset.id);
                    setLocalDataset(updated);
                    toast({ title: "PII warning acknowledged" });
                  } catch {
                    toast({ title: "Failed to acknowledge PII warning", variant: "destructive" });
                  }
                }}
              >
                Acknowledge
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="overflow-auto rounded-lg border border-forge-border">
        <table className="w-full text-sm">
        <thead>
          <tr className="bg-forge-bg">
            <th className="px-3 py-2 text-left font-mono text-xs text-forge-muted">
              Column
            </th>
            <th className="px-3 py-2 text-left font-mono text-xs text-forge-muted">
              Type
            </th>
            <th className="px-3 py-2 text-left font-mono text-xs text-forge-muted">
              Nullable
            </th>
              <th className="px-3 py-2 text-left font-mono text-xs text-forge-muted">
                Samples
              </th>
              <th className="px-3 py-2 text-left font-mono text-xs text-forge-muted">
                PII
              </th>
            </tr>
          </thead>
          <tbody>
          {schema.map((col, i) => (
            <tr key={i} className="border-t border-forge-border/50">
              <td className="px-3 py-1.5 font-mono text-xs font-medium text-foreground">
                {col.name}
              </td>
              <td className="px-3 py-1.5">
                <Badge variant="secondary" className="font-mono text-[10px]">
                  {col.dtype}
                </Badge>
              </td>
              <td className="px-3 py-1.5 text-xs text-forge-muted">
                {col.nullable ? "Yes" : "No"}
              </td>
              <td className="max-w-[180px] truncate px-3 py-1.5 text-xs text-forge-muted">
                {col.sample_values?.slice(0, 3).join(", ") ?? "—"}
              </td>
              <td className="px-3 py-1.5 text-xs">
                {col.pii_types && col.pii_types.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {col.pii_types.map((pii) => (
                      <Badge key={`${col.name}-${pii}`} variant="warning" className="font-mono text-[10px]">
                        {pii}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <span className="text-forge-muted">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab: Quality
// ═══════════════════════════════════════════════════════════════════════════════

const QUICK_RULES: { label: string; rule: (col: string) => QualityRule }[] = [
  { label: "Not Null", rule: (col) => ({ type: "not_null", column: col }) },
  { label: "Unique", rule: (col) => ({ type: "unique", column: col }) },
];

function QualityTab({
  workspaceId,
  dataset,
}: {
  workspaceId: string;
  dataset: Dataset;
}) {
  const [reports, setReports] = useState<QualityReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedRules, setSelectedRules] = useState<QualityRule[]>([]);
  const columns = dataset.schema_snapshot ?? [];

  useEffect(() => {
    getQualityReports(workspaceId, dataset.id)
      .then(setReports)
      .finally(() => setLoading(false));
  }, [workspaceId, dataset.id]);

  const addRule = (rule: QualityRule) => {
    setSelectedRules((prev) => [...prev, rule]);
  };

  const removeRule = (idx: number) => {
    setSelectedRules((prev) => prev.filter((_, i) => i !== idx));
  };

  const runChecks = async () => {
    if (selectedRules.length === 0) return;
    setRunning(true);
    try {
      const report = await runQualityCheck(
        workspaceId,
        dataset.id,
        selectedRules,
      );
      setReports((prev) => [report, ...prev]);
    } catch {
      /* error handled in UI */
    } finally {
      setRunning(false);
    }
  };

  const handleSaveRuleset = async () => {
    if (selectedRules.length === 0) return;
    setSaving(true);
    try {
      await saveRuleset(workspaceId, dataset.id, "default", selectedRules);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Rule builder */}
      <div>
        <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
          Add quality rules
        </p>
        <div className="flex flex-wrap gap-1">
          {columns.map((col) =>
            QUICK_RULES.map((qr) => (
              <button
                key={`${col.name}-${qr.label}`}
                onClick={() => addRule(qr.rule(col.name))}
                className="rounded border border-forge-border px-2 py-0.5 text-[10px] text-forge-muted hover:border-forge-accent hover:text-forge-accent"
              >
                {col.name}: {qr.label}
              </button>
            )),
          )}
        </div>
      </div>

      {/* Selected rules */}
      {selectedRules.length > 0 && (
        <div className="space-y-2">
          <p className="font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
            Rules to run ({selectedRules.length})
          </p>
          <div className="space-y-1">
            {selectedRules.map((rule, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded border border-forge-border bg-forge-bg px-3 py-1 text-xs"
              >
                <span className="text-foreground">
                  {rule.column}: <span className="text-forge-accent">{rule.type}</span>
                </span>
                <button
                  onClick={() => removeRule(i)}
                  className="text-forge-muted hover:text-red-400"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={runChecks}
              disabled={running}
              className="flex items-center gap-1.5 rounded-md bg-forge-accent px-3 py-1.5 text-xs font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
            >
              {running && <Loader2 className="h-3 w-3 animate-spin" />}
              Run checks
            </button>
            <button
              onClick={handleSaveRuleset}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-md border border-forge-border px-3 py-1.5 text-xs text-forge-muted hover:bg-forge-border/50 hover:text-foreground disabled:opacity-50"
            >
              {saving && <Loader2 className="h-3 w-3 animate-spin" />}
              Save ruleset
            </button>
          </div>
        </div>
      )}

      {/* Past reports */}
      <div>
        <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
          Report history
        </p>
        {loading ? (
          <div className="space-y-2">
            {[1, 2].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : reports.length === 0 ? (
          <p className="text-sm text-forge-muted">No quality reports yet</p>
        ) : (
          <div className="space-y-2">
            {reports.map((report) => (
              <div
                key={report.id}
                className="rounded-lg border border-forge-border bg-forge-bg p-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {report.failed === 0 ? (
                      <CheckCircle2 className="h-4 w-4 text-green-400" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 text-yellow-400" />
                    )}
                    <span className="text-sm text-foreground">
                      {report.passed} passed, {report.failed} failed
                    </span>
                  </div>
                  <span className="text-xs text-forge-muted">
                    {formatDate(report.created_at)}
                  </span>
                </div>
                {report.results
                  .filter((r) => r.status === "failed")
                  .slice(0, 3)
                  .map((r, i) => (
                    <p key={i} className="mt-1 text-xs text-red-400">
                      ✗ {r.message}
                    </p>
                  ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab: Versions
// ═══════════════════════════════════════════════════════════════════════════════

function VersionsTab({
  workspaceId,
  dataset,
}: {
  workspaceId: string;
  dataset: Dataset;
}) {
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [rollbackLoading, setRollbackLoading] = useState<number | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    listVersions(workspaceId, dataset.id)
      .then(setVersions)
      .finally(() => setLoading(false));
  }, [workspaceId, dataset.id]);

  const loadDiff = async (v1: number, v2: number) => {
    setDiffLoading(true);
    try {
      const d = await diffVersions(workspaceId, dataset.id, v1, v2);
      setDiff(d);
    } finally {
      setDiffLoading(false);
    }
  };

  const handleRollback = async (vn: number) => {
    setRollbackLoading(vn);
    try {
      const newVer = await rollbackVersion(workspaceId, dataset.id, vn);
      setVersions((prev) => [newVer, ...prev]);
    } finally {
      setRollbackLoading(null);
    }
  };

  const handleUploadVersion = async (file: File) => {
    setUploading(true);
    try {
      const ver = await createVersion(workspaceId, dataset.id, file);
      setVersions((prev) => [ver, ...prev]);
      setUploadOpen(false);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
          Version history
        </p>
        <button
          onClick={() => setUploadOpen(!uploadOpen)}
          className="flex items-center gap-1.5 rounded-md border border-forge-border px-2.5 py-1 text-xs text-forge-muted hover:bg-forge-border/50 hover:text-foreground"
        >
          <Upload className="h-3 w-3" />
          New version
        </button>
      </div>

      {/* Upload new version */}
      {uploadOpen && (
        <div className="rounded-lg border border-forge-accent/30 bg-forge-accent/5 p-3">
          <input
            type="file"
            accept=".csv,.xlsx,.xls,.parquet,.json"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleUploadVersion(f);
            }}
            className="text-sm text-foreground file:mr-2 file:rounded file:border-0 file:bg-forge-accent file:px-2 file:py-1 file:text-xs file:font-semibold file:text-forge-bg"
          />
          {uploading && (
            <div className="mt-2 flex items-center gap-2 text-xs text-forge-muted">
              <Loader2 className="h-3 w-3 animate-spin" />
              Uploading…
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : versions.length === 0 ? (
        <p className="text-sm text-forge-muted">
          No versions yet. Upload a new version to start tracking changes.
        </p>
      ) : (
        <div className="relative space-y-0">
          {/* Timeline line */}
          <div className="absolute left-3 top-2 bottom-2 w-px bg-forge-border" />

          {versions.map((ver, i) => (
            <div key={ver.id} className="relative flex gap-3 pb-4 pl-7">
              {/* Dot */}
              <div
                className={`absolute left-1.5 top-1.5 h-3 w-3 rounded-full border-2 ${
                  i === 0
                    ? "border-forge-accent bg-forge-accent"
                    : "border-forge-border bg-forge-surface"
                }`}
              />
              <div className="flex-1 rounded-lg border border-forge-border bg-forge-bg p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <GitBranch className="h-3 w-3 text-forge-muted" />
                    <span className="font-mono text-sm font-medium text-foreground">
                      v{ver.version_number}
                    </span>
                    {ver.message && (
                      <span className="text-xs text-forge-muted">
                        — {ver.message}
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-forge-muted">
                    {formatDate(ver.created_at)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-forge-muted">
                  {ver.row_count?.toLocaleString() ?? "?"} rows
                  {ver.size_bytes
                    ? ` · ${(ver.size_bytes / 1024).toFixed(1)} KB`
                    : ""}
                </p>
                <div className="mt-2 flex gap-2">
                  {i < versions.length - 1 && (
                    <button
                      onClick={() =>
                        loadDiff(
                          versions[i + 1].version_number,
                          ver.version_number,
                        )
                      }
                      disabled={diffLoading}
                      className="flex items-center gap-1 text-[10px] text-forge-accent hover:underline"
                    >
                      <RefreshCw className="h-3 w-3" />
                      Diff with v{versions[i + 1].version_number}
                    </button>
                  )}
                  {i > 0 && (
                    <button
                      onClick={() => handleRollback(ver.version_number)}
                      disabled={rollbackLoading === ver.version_number}
                      className="flex items-center gap-1 text-[10px] text-forge-muted hover:text-yellow-400"
                    >
                      {rollbackLoading === ver.version_number ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <RotateCcw className="h-3 w-3" />
                      )}
                      Rollback to this
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Diff viewer */}
      {diff && (
        <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
          <p className="mb-2 font-mono text-xs font-semibold text-foreground">
            Diff: v{diff.v1} → v{diff.v2}
          </p>
          <div className="space-y-1 text-xs">
            <p className="text-forge-muted">
              Rows: {diff.row_count_v1.toLocaleString()} →{" "}
              {diff.row_count_v2.toLocaleString()}{" "}
              <span
                className={
                  diff.row_delta > 0
                    ? "text-green-400"
                    : diff.row_delta < 0
                      ? "text-red-400"
                      : "text-forge-muted"
                }
              >
                ({diff.row_delta > 0 ? "+" : ""}
                {diff.row_delta})
              </span>
            </p>
            {diff.added_columns.length > 0 && (
              <p className="text-green-400">
                + Columns: {diff.added_columns.join(", ")}
              </p>
            )}
            {diff.removed_columns.length > 0 && (
              <p className="text-red-400">
                − Columns: {diff.removed_columns.join(", ")}
              </p>
            )}
            {diff.type_changes.map((tc, i) => (
              <p key={i} className="text-yellow-400">
                ~ {tc.column}: {tc.from} → {tc.to}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tab: Preview
// ═══════════════════════════════════════════════════════════════════════════════

function PreviewTab({
  workspaceId,
  dataset,
}: {
  workspaceId: string;
  dataset: Dataset;
}) {
  const [previewData, setPreviewData] = useState<{
    columns: string[];
    rows: unknown[][];
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPreview = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await executeQuery(
        workspaceId,
        `SELECT * FROM "${dataset.name}" LIMIT 100`,
      );
      setPreviewData({ columns: result.columns, rows: result.rows });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load preview",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-8 w-full" />
        {[1, 2, 3, 4, 5].map((i) => (
          <Skeleton key={i} className="h-6 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-dashed border-forge-border py-8 text-center">
        <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-yellow-400" />
        <p className="text-sm text-forge-muted">{error}</p>
        <button
          onClick={loadPreview}
          className="mt-2 text-xs text-forge-accent hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!previewData) return null;

  return (
    <DataGrid
      columns={previewData.columns}
      rows={previewData.rows}
      maxHeight="400px"
      exportFilename={`${dataset.name}_preview.csv`}
    />
  );
}
