"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import {
  X,
  Upload,
  Database,
  Snowflake,
  HardDrive,
  CheckCircle2,
  XCircle,
  Loader2,
  FileSpreadsheet,
} from "lucide-react";
import api from "@/lib/api";
import { uploadDataset, connectDataset } from "@/lib/api/datasets";
import type { SourceType, Dataset, DatasetProfile, SchemaColumn } from "@/types";

// ── Source type definitions ──────────────────────────────────────────────────

const FILE_SOURCES: { value: SourceType; label: string; icon: React.ReactNode; exts: string }[] = [
  { value: "csv", label: "Upload File", icon: <Upload className="h-5 w-5" />, exts: "CSV, Excel, Parquet, JSON" },
];

const DB_SOURCES: {
  value: SourceType;
  label: string;
  icon: React.ReactNode;
  disabled?: boolean;
  fields: string[];
}[] = [
  { value: "postgres", label: "PostgreSQL", icon: <Database className="h-5 w-5" />, fields: ["host", "port", "database", "username", "password", "schema_name"] },
  { value: "snowflake", label: "Snowflake", icon: <Snowflake className="h-5 w-5" />, fields: ["account", "warehouse", "database", "username", "password", "schema_name", "table"] },
  { value: "s3", label: "Amazon S3", icon: <HardDrive className="h-5 w-5" />, fields: ["bucket", "prefix", "region", "aws_access_key", "aws_secret_key", "endpoint_url"] },
  { value: "mysql", label: "MySQL", icon: <Database className="h-5 w-5" />, fields: ["host", "port", "database", "username", "password"] },
  { value: "bigquery", label: "BigQuery", icon: <Database className="h-5 w-5" />, fields: ["project_id", "dataset_id", "table", "credentials_json"] },
];

type Step = "choose" | "file" | "database" | "name" | "success";

interface ConnectorWizardProps {
  workspaceId: string;
  onClose: () => void;
  onSuccess?: (dataset: Dataset) => void;
}

export default function ConnectorWizard({
  workspaceId,
  onClose,
  onSuccess,
}: ConnectorWizardProps) {
  const [step, setStep] = useState<Step>("choose");
  const [sourceType, setSourceType] = useState<SourceType>("csv");
  const [file, setFile] = useState<File | null>(null);
  const [filePreview, setFilePreview] = useState<string[][] | null>(null);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [datasetName, setDatasetName] = useState("");
  const [description, setDescription] = useState("");
  const [testing, setTesting] = useState(false);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [testMessage, setTestMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [resultDataset, setResultDataset] = useState<Dataset | null>(null);
  const [resultProfile, setResultProfile] = useState<DatasetProfile | null>(null);
  const [resultSchema, setResultSchema] = useState<SchemaColumn[] | null>(null);

  const isFileSource = sourceType === "csv" || sourceType === "excel" || sourceType === "parquet" || sourceType === "json";

  // ── File drop handler ──────────────────────────────────────────────────

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length === 0) return;
    const f = accepted[0];
    setFile(f);
    setDatasetName(f.name.replace(/\.[^.]+$/, ""));
    setError(null);

    // Preview first 5 rows for CSV
    if (f.name.endsWith(".csv")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const lines = text.split("\n").filter(Boolean).slice(0, 6);
        setFilePreview(lines.map((l) => l.split(",")));
      };
      reader.readAsText(f.slice(0, 8192));
    } else {
      setFilePreview(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "application/json": [".json"],
      "application/octet-stream": [".parquet"],
    },
    maxFiles: 1,
    multiple: false,
  });

  // ── Test connection ────────────────────────────────────────────────────

  const testConnection = async () => {
    setTesting(true);
    setTestOk(null);
    try {
      const resp = await api.post("/api/v1/connectors/test", {
        type: sourceType,
        ...config,
      });
      setTestOk(resp.data.success);
      setTestMessage(resp.data.message);
    } catch {
      setTestOk(false);
      setTestMessage("Connection test failed");
    } finally {
      setTesting(false);
    }
  };

  // ── Submit ─────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    setUploading(true);
    setError(null);
    setUploadProgress(10);

    try {
      if (isFileSource && file) {
        setUploadProgress(30);
        const result = await uploadDataset(workspaceId, file);
        setUploadProgress(90);
        setResultDataset(result.dataset);
        setResultProfile(result.profile);
        setResultSchema(result.dataset.schema_snapshot);
      } else {
        setUploadProgress(30);
        const result = await connectDataset(
          workspaceId,
          datasetName || sourceType,
          sourceType,
          config,
        );
        setUploadProgress(90);
        setResultDataset(result.dataset);
        setResultSchema(result.dataset.schema_snapshot);
      }
      setUploadProgress(100);
      setStep("success");
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Upload failed. Please try again.";
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────

  const stepNumber =
    step === "choose" ? 1 : step === "file" || step === "database" ? 2 : step === "name" ? 3 : 4;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="relative w-full max-w-xl rounded-xl border border-forge-border bg-forge-surface p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-forge-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="mb-1 text-lg font-semibold text-foreground">
          {step === "success" ? "Dataset created" : "Connect a data source"}
        </h2>
        {step !== "success" && (
          <p className="mb-5 text-sm text-forge-muted">Step {stepNumber} of 4</p>
        )}

        {/* ── Step 1: Choose source type ─────────────────────────────── */}
        {step === "choose" && (
          <div className="space-y-3">
            <p className="font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
              File upload
            </p>
            <div className="grid grid-cols-1 gap-2">
              {FILE_SOURCES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => {
                    setSourceType("csv");
                    setStep("file");
                  }}
                  className="flex items-center gap-3 rounded-lg border border-forge-border bg-forge-bg px-4 py-3 text-sm text-foreground transition-colors hover:border-forge-accent hover:text-forge-accent"
                >
                  {s.icon}
                  <div className="text-left">
                    <p className="font-medium">{s.label}</p>
                    <p className="text-xs text-forge-muted">{s.exts}</p>
                  </div>
                </button>
              ))}
            </div>

            <p className="mt-4 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
              Databases & warehouses
            </p>
            <div className="grid grid-cols-2 gap-2">
              {DB_SOURCES.map((s) => (
                <button
                  key={s.value}
                  disabled={s.disabled}
                  onClick={() => {
                    setSourceType(s.value);
                    setStep("database");
                  }}
                  className="flex items-center gap-3 rounded-lg border border-forge-border bg-forge-bg px-4 py-3 text-sm text-foreground transition-colors hover:border-forge-accent hover:text-forge-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {s.icon}
                  <div className="text-left">
                    <p className="font-medium">{s.label}</p>
                    {s.disabled && (
                      <p className="text-[10px] text-forge-muted">Coming soon</p>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Step 2a: File upload ────────────────────────────────────── */}
        {step === "file" && (
          <div className="space-y-4">
            <div
              {...getRootProps()}
              className={`cursor-pointer rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
                isDragActive
                  ? "border-forge-accent bg-forge-accent/5"
                  : "border-forge-border hover:border-forge-accent/50"
              }`}
            >
              <input {...getInputProps()} />
              {file ? (
                <div className="space-y-1">
                  <FileSpreadsheet className="mx-auto h-8 w-8 text-forge-accent" />
                  <p className="text-sm font-medium text-foreground">{file.name}</p>
                  <p className="text-xs text-forge-muted">
                    {(file.size / 1024).toFixed(1)} KB — Click or drop to replace
                  </p>
                </div>
              ) : (
                <div className="space-y-1">
                  <Upload className="mx-auto h-8 w-8 text-forge-muted" />
                  <p className="text-sm text-foreground">
                    Drag & drop a file, or{" "}
                    <span className="text-forge-accent">browse</span>
                  </p>
                  <p className="text-xs text-forge-muted">CSV, Excel, Parquet, JSON</p>
                </div>
              )}
            </div>

            {/* CSV preview */}
            {filePreview && filePreview.length > 1 && (
              <div className="overflow-auto rounded-lg border border-forge-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-forge-bg">
                      {filePreview[0].map((h, i) => (
                        <th
                          key={i}
                          className="whitespace-nowrap px-2 py-1 text-left font-mono text-forge-muted"
                        >
                          {h.trim()}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filePreview.slice(1, 6).map((row, ri) => (
                      <tr key={ri} className="border-t border-forge-border/50">
                        {row.map((cell, ci) => (
                          <td
                            key={ci}
                            className="max-w-[120px] truncate whitespace-nowrap px-2 py-1 text-foreground"
                          >
                            {cell.trim()}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-between pt-2">
              <button
                onClick={() => {
                  setStep("choose");
                  setFile(null);
                  setFilePreview(null);
                }}
                className="text-sm text-forge-muted hover:text-foreground"
              >
                ← Back
              </button>
              <button
                disabled={!file}
                onClick={() => setStep("name")}
                className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* ── Step 2b: Database config ────────────────────────────────── */}
        {step === "database" && (
          <div className="space-y-3">
            <p className="text-sm text-foreground">
              Configure{" "}
              <strong>
                {DB_SOURCES.find((s) => s.value === sourceType)?.label}
              </strong>{" "}
              connection
            </p>

            {(DB_SOURCES.find((s) => s.value === sourceType)?.fields || []).map(
              (field) => (
                <div key={field}>
                  <label className="mb-1 block text-xs font-medium capitalize text-forge-muted">
                    {field.replace(/_/g, " ")}
                  </label>
                  <input
                    type={
                      field.includes("password") || field.includes("secret")
                        ? "password"
                        : "text"
                    }
                    placeholder={
                      field === "port"
                        ? sourceType === "postgres"
                          ? "5432"
                          : "3306"
                        : field === "schema_name"
                          ? "public"
                          : ""
                    }
                    value={config[field] ?? ""}
                    onChange={(e) =>
                      setConfig((c) => ({ ...c, [field]: e.target.value }))
                    }
                    className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
                  />
                </div>
              ),
            )}

            {/* Test connection */}
            <button
              onClick={testConnection}
              disabled={testing}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-forge-border py-2 text-sm text-foreground hover:bg-forge-border/50 disabled:opacity-50"
            >
              {testing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Testing…
                </>
              ) : (
                "Test connection"
              )}
            </button>

            {testOk !== null && (
              <div
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm ${
                  testOk
                    ? "bg-green-900/30 text-green-400"
                    : "bg-red-900/30 text-red-400"
                }`}
              >
                {testOk ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                {testMessage}
              </div>
            )}

            <div className="flex justify-between pt-2">
              <button
                onClick={() => {
                  setStep("choose");
                  setTestOk(null);
                }}
                className="text-sm text-forge-muted hover:text-foreground"
              >
                ← Back
              </button>
              <button
                onClick={() => setStep("name")}
                className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim"
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3: Name & submit ───────────────────────────────────── */}
        {step === "name" && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-forge-muted">
                Dataset name
              </label>
              <input
                value={datasetName}
                onChange={(e) => setDatasetName(e.target.value)}
                placeholder="My dataset"
                className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-forge-muted">
                Description (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-red-900/30 px-4 py-2 text-sm text-red-400">
                {error}
              </div>
            )}

            {uploading && (
              <div className="space-y-1">
                <div className="h-2 overflow-hidden rounded-full bg-forge-border">
                  <div
                    className="h-full rounded-full bg-forge-accent transition-all duration-500"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="text-center text-xs text-forge-muted">
                  {uploadProgress < 30
                    ? "Preparing…"
                    : uploadProgress < 90
                      ? "Uploading & profiling…"
                      : "Finalizing…"}
                </p>
              </div>
            )}

            <div className="flex justify-between pt-2">
              <button
                onClick={() => setStep(isFileSource ? "file" : "database")}
                className="text-sm text-forge-muted hover:text-foreground"
              >
                ← Back
              </button>
              <button
                onClick={handleSubmit}
                disabled={uploading || (!file && isFileSource)}
                className="flex items-center gap-2 rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-40"
              >
                {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
                {isFileSource ? "Upload & profile" : "Connect"}
              </button>
            </div>
          </div>
        )}

        {/* ── Step 4: Success ─────────────────────────────────────────── */}
        {step === "success" && resultDataset && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 rounded-lg bg-green-900/30 px-4 py-3 text-sm text-green-400">
              <CheckCircle2 className="h-5 w-5" />
              Dataset &quot;{resultDataset.name}&quot; created successfully
            </div>

            {/* Schema preview */}
            {resultSchema && resultSchema.length > 0 && (
              <div>
                <p className="mb-2 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
                  Schema
                </p>
                <div className="max-h-48 overflow-auto rounded-lg border border-forge-border">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-forge-bg">
                        <th className="px-3 py-1.5 text-left font-mono text-forge-muted">
                          Column
                        </th>
                        <th className="px-3 py-1.5 text-left font-mono text-forge-muted">
                          Type
                        </th>
                        <th className="px-3 py-1.5 text-left font-mono text-forge-muted">
                          Nullable
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {resultSchema.map((col, i) => (
                        <tr key={i} className="border-t border-forge-border/50">
                          <td className="px-3 py-1 font-mono text-foreground">
                            {col.name}
                          </td>
                          <td className="px-3 py-1 text-forge-muted">
                            {col.dtype}
                          </td>
                          <td className="px-3 py-1 text-forge-muted">
                            {col.nullable ? "Yes" : "No"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {resultProfile && (
              <p className="text-xs text-forge-muted">
                {resultProfile.row_count.toLocaleString()} rows ·{" "}
                {resultProfile.column_count} columns
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => {
                  onSuccess?.(resultDataset);
                  onClose();
                }}
                className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim"
              >
                View dataset
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
