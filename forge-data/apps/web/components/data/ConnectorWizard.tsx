"use client";

import { useState } from "react";
import { X, ChevronRight, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import api from "@/lib/api";
import type { SourceType, ConnectorTestResult } from "@/types";

const SOURCE_TYPES: { value: SourceType; label: string }[] = [
  { value: "postgres", label: "PostgreSQL" },
  { value: "mysql", label: "MySQL" },
  { value: "sqlite", label: "SQLite" },
  { value: "csv", label: "CSV / File" },
  { value: "parquet", label: "Parquet" },
  { value: "json", label: "JSON" },
  { value: "excel", label: "Excel" },
  { value: "rest_api", label: "REST API" },
  { value: "s3", label: "Amazon S3" },
  { value: "bigquery", label: "BigQuery" },
];

const SQL_SOURCES: SourceType[] = ["postgres", "mysql", "sqlite"];

interface ConnectorWizardProps {
  onClose: () => void;
}

type Step = "type" | "config" | "test";

export default function ConnectorWizard({ onClose }: ConnectorWizardProps) {
  const [step, setStep] = useState<Step>("type");
  const [sourceType, setSourceType] = useState<SourceType | null>(null);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ConnectorTestResult | null>(null);

  const isSql = sourceType && SQL_SOURCES.includes(sourceType);

  const defaultFields = isSql
    ? ["host", "port", "database", "username", "password"]
    : sourceType === "rest_api"
    ? ["url", "headers_json"]
    : sourceType === "s3"
    ? ["bucket", "prefix", "region", "access_key_id", "secret_access_key"]
    : ["path"];

  const test = async () => {
    if (!sourceType) return;
    setTesting(true);
    setTestResult(null);
    try {
      const resp = await api.post<ConnectorTestResult>("/api/v1/connectors/test", {
        source_type: sourceType,
        connection_config: config,
      });
      setTestResult(resp.data);
    } catch {
      setTestResult({ ok: false, message: "Request failed", latency_ms: 0 });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="relative w-full max-w-lg rounded-xl border border-forge-border bg-forge-surface p-6 shadow-2xl">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-forge-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>

        <h2 className="mb-1 text-lg font-semibold text-foreground">
          Connect a data source
        </h2>
        <p className="mb-5 text-sm text-forge-muted">
          Step {step === "type" ? "1" : step === "config" ? "2" : "3"} of 3
        </p>

        {/* Step 1: choose type */}
        {step === "type" && (
          <div className="grid grid-cols-2 gap-2">
            {SOURCE_TYPES.map(({ value, label }) => (
              <button
                key={value}
                onClick={() => {
                  setSourceType(value);
                  setStep("config");
                }}
                className="flex items-center justify-between rounded-lg border border-forge-border bg-forge-bg px-4 py-3 text-sm text-foreground hover:border-forge-accent hover:text-forge-accent"
              >
                {label}
                <ChevronRight className="h-4 w-4 text-forge-muted" />
              </button>
            ))}
          </div>
        )}

        {/* Step 2: connection config */}
        {step === "config" && (
          <div className="space-y-3">
            {defaultFields.map((field) => (
              <div key={field}>
                <label className="mb-1 block text-xs font-medium capitalize text-forge-muted">
                  {field.replace(/_/g, " ")}
                </label>
                <input
                  type={
                    field === "password" || field === "secret_access_key"
                      ? "password"
                      : "text"
                  }
                  value={config[field] ?? ""}
                  onChange={(e) =>
                    setConfig((c) => ({ ...c, [field]: e.target.value }))
                  }
                  className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
                />
              </div>
            ))}
            <div className="flex justify-between pt-2">
              <button
                onClick={() => setStep("type")}
                className="text-sm text-forge-muted hover:text-foreground"
              >
                ← Back
              </button>
              <button
                onClick={() => setStep("test")}
                className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim"
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* Step 3: test connection */}
        {step === "test" && (
          <div className="space-y-4">
            <p className="text-sm text-foreground">
              Test your connection to{" "}
              <strong>
                {SOURCE_TYPES.find((s) => s.value === sourceType)?.label}
              </strong>
              .
            </p>
            <button
              onClick={test}
              disabled={testing}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-forge-accent py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
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

            {testResult && (
              <div
                className={`flex items-center gap-2 rounded-lg px-4 py-3 text-sm ${
                  testResult.ok
                    ? "bg-green-900/30 text-green-400"
                    : "bg-red-900/30 text-red-400"
                }`}
              >
                {testResult.ok ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                {testResult.message}{" "}
                {testResult.ok && (
                  <span className="text-xs opacity-70">
                    ({testResult.latency_ms}ms)
                  </span>
                )}
              </div>
            )}

            <div className="flex justify-between pt-2">
              <button
                onClick={() => setStep("config")}
                className="text-sm text-forge-muted hover:text-foreground"
              >
                ← Back
              </button>
              {testResult?.ok && (
                <button
                  onClick={onClose}
                  className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim"
                >
                  Save connector
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
