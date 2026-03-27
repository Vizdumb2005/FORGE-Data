"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AutomationNode, Dataset } from "@/types";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type NodeConfigUpdate = {
  label?: string;
  retry_count?: number;
  timeout_seconds?: number;
  on_failure?: "stop" | "continue" | "branch";
  config?: Record<string, unknown>;
};

interface NodeConfigPanelProps {
  open: boolean;
  node: AutomationNode | null;
  datasets: Dataset[];
  onClose: () => void;
  onUpdate: (nodeId: string, patch: NodeConfigUpdate) => Promise<void>;
  onDelete: (nodeId: string) => Promise<void>;
}

function KeyValueTable({
  rows,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
}: {
  rows: Array<{ key: string; value: string }>;
  onChange: (next: Array<{ key: string; value: string }>) => void;
  keyPlaceholder: string;
  valuePlaceholder: string;
}) {
  return (
    <div className="space-y-2">
      {rows.map((row, idx) => (
        <div key={`${row.key}-${idx}`} className="grid grid-cols-2 gap-2">
          <Input
            value={row.key}
            placeholder={keyPlaceholder}
            onChange={(e) => {
              const next = [...rows];
              next[idx] = { ...next[idx], key: e.target.value };
              onChange(next);
            }}
          />
          <Input
            value={row.value}
            placeholder={valuePlaceholder}
            onChange={(e) => {
              const next = [...rows];
              next[idx] = { ...next[idx], value: e.target.value };
              onChange(next);
            }}
          />
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...rows, { key: "", value: "" }])}
      >
        Add Row
      </Button>
    </div>
  );
}

export default function NodeConfigPanel({
  open,
  node,
  datasets,
  onClose,
  onUpdate,
  onDelete,
}: NodeConfigPanelProps) {
  const [label, setLabel] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [onFailure, setOnFailure] = useState<"stop" | "continue" | "branch">("stop");
  const [config, setConfig] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!node) return;
    setLabel(node.label ?? "");
    setRetryCount(node.retry_count ?? 0);
    setTimeoutSeconds(node.timeout_seconds ?? 30);
    setOnFailure(node.on_failure ?? "stop");
    setConfig(node.config ?? {});
  }, [node]);

  const methodOptions = ["GET", "POST", "PUT", "PATCH", "DELETE"];

  const parameters = useMemo(() => {
    const value = config.parameters;
    return Array.isArray(value)
      ? (value as Array<{ key: string; value: string }>)
      : [{ key: "", value: "" }];
  }, [config.parameters]);

  const headers = useMemo(() => {
    const value = config.headers;
    return Array.isArray(value)
      ? (value as Array<{ key: string; value: string }>)
      : [{ key: "", value: "" }];
  }, [config.headers]);

  if (!open || !node) return null;

  return (
    <motion.aside
      initial={{ x: 320, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 320, opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="absolute right-0 top-0 z-20 h-full w-[300px] border-l border-forge-border bg-[#0f131b]"
    >
      <div className="flex items-center justify-between border-b border-forge-border px-3 py-2">
        <p className="text-sm font-semibold">Node Config</p>
        <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
      </div>
      <ScrollArea className="h-[calc(100%-49px)]">
        <div className="space-y-4 p-3">
          <div className="space-y-1.5">
            <Label>Label</Label>
            <Input value={label} onChange={(e) => setLabel(e.target.value)} />
          </div>

          {node.type === "code_cell" && (
            <>
              <div className="space-y-1.5">
                <Label>Code Cell</Label>
                <Select
                  value={String(config.cell_id ?? "")}
                  onValueChange={(value) => setConfig((prev) => ({ ...prev, cell_id: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select source cell" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cell_1">cell_1</SelectItem>
                    <SelectItem value="cell_2">cell_2</SelectItem>
                    <SelectItem value="cell_3">cell_3</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Parameters</Label>
                <KeyValueTable
                  rows={parameters}
                  keyPlaceholder="key"
                  valuePlaceholder="value"
                  onChange={(next) => setConfig((prev) => ({ ...prev, parameters: next }))}
                />
              </div>
            </>
          )}

          {node.type === "sql_query" && (
            <>
              <div className="space-y-1.5">
                <Label>SQL</Label>
                <div className="monaco-wrapper">
                  <MonacoEditor
                    height="200px"
                    language="sql"
                    theme="vs-dark"
                    value={String(config.sql ?? "SELECT * FROM table")}
                    onChange={(value) => setConfig((prev) => ({ ...prev, sql: value ?? "" }))}
                    options={{ minimap: { enabled: false }, fontSize: 12 }}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Dataset</Label>
                <Select
                  value={String(config.dataset_id ?? "")}
                  onValueChange={(value) => setConfig((prev) => ({ ...prev, dataset_id: value }))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select dataset" />
                  </SelectTrigger>
                  <SelectContent>
                    {datasets.map((d) => (
                      <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Output Table Name</Label>
                <Input
                  value={String(config.output_table ?? "")}
                  onChange={(e) => setConfig((prev) => ({ ...prev, output_table: e.target.value }))}
                />
              </div>
            </>
          )}

          {node.type === "api_call" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label>Method</Label>
                  <Select
                    value={String(config.method ?? "GET")}
                    onValueChange={(value) => setConfig((prev) => ({ ...prev, method: value }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {methodOptions.map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Auth Type</Label>
                  <Select
                    value={String(config.auth_type ?? "none")}
                    onValueChange={(value) => setConfig((prev) => ({ ...prev, auth_type: value }))}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">none</SelectItem>
                      <SelectItem value="bearer">bearer</SelectItem>
                      <SelectItem value="basic">basic</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>URL</Label>
                <Input
                  value={String(config.url ?? "")}
                  onChange={(e) => setConfig((prev) => ({ ...prev, url: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Auth Value</Label>
                <Input
                  value={String(config.auth_value ?? "")}
                  onChange={(e) => setConfig((prev) => ({ ...prev, auth_value: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Headers</Label>
                <KeyValueTable
                  rows={headers}
                  keyPlaceholder="Header"
                  valuePlaceholder="Value"
                  onChange={(next) => setConfig((prev) => ({ ...prev, headers: next }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Body</Label>
                <div className="monaco-wrapper">
                  <MonacoEditor
                    height="200px"
                    language="json"
                    theme="vs-dark"
                    value={String(config.body ?? "{}")}
                    onChange={(value) => setConfig((prev) => ({ ...prev, body: value ?? "" }))}
                    options={{ minimap: { enabled: false }, fontSize: 12 }}
                  />
                </div>
              </div>
            </>
          )}

          {node.type === "email_notify" && (
            <>
              <div className="space-y-1.5">
                <Label>To</Label>
                <Input
                  value={String(config.to ?? "")}
                  placeholder="team@company.com, alerts@company.com"
                  onChange={(e) => setConfig((prev) => ({ ...prev, to: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Subject</Label>
                <Input
                  value={String(config.subject ?? "")}
                  onChange={(e) => setConfig((prev) => ({ ...prev, subject: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Jinja2 Body</Label>
                <Textarea
                  rows={6}
                  value={String(config.body_template ?? "")}
                  onChange={(e) => setConfig((prev) => ({ ...prev, body_template: e.target.value }))}
                />
              </div>
            </>
          )}

          {node.type === "conditional" && (
            <div className="space-y-1.5">
              <Label>Expression</Label>
              <Textarea
                rows={5}
                value={String(config.expression ?? "")}
                onChange={(e) => setConfig((prev) => ({ ...prev, expression: e.target.value }))}
              />
              <p className="text-xs text-forge-muted">Use Python-style truthy expression, e.g. <code>{`metrics["accuracy"] > 0.92`}</code></p>
            </div>
          )}

          {node.type === "wait" && (
            <div className="space-y-1.5">
              <Label>Wait: {Number(config.seconds ?? 0)}s</Label>
              <input
                className="w-full"
                type="range"
                min={0}
                max={3600}
                value={Number(config.seconds ?? 0)}
                onChange={(e) => setConfig((prev) => ({ ...prev, seconds: Number(e.target.value) }))}
              />
            </div>
          )}

          <div className="space-y-2 rounded-md border border-forge-border p-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-forge-muted">Shared</p>
            <div className="space-y-1.5">
              <Label>Retry Count: {retryCount}</Label>
              <input
                className="w-full"
                type="range"
                min={0}
                max={10}
                value={retryCount}
                onChange={(e) => setRetryCount(Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Timeout (s)</Label>
              <Input
                type="number"
                min={0}
                value={timeoutSeconds}
                onChange={(e) => setTimeoutSeconds(Number(e.target.value) || 0)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>On Failure</Label>
              <Select value={onFailure} onValueChange={(v: "stop" | "continue" | "branch") => setOnFailure(v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="stop">Stop</SelectItem>
                  <SelectItem value="continue">Continue</SelectItem>
                  <SelectItem value="branch">Branch</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              className="flex-1 bg-[#f97316] text-black hover:bg-[#ea580c]"
              onClick={async () => {
                await onUpdate(node.id, {
                  label,
                  retry_count: retryCount,
                  timeout_seconds: timeoutSeconds,
                  on_failure: onFailure,
                  config,
                });
              }}
            >
              Save
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                await onDelete(node.id);
                onClose();
              }}
            >
              Delete
            </Button>
          </div>
        </div>
      </ScrollArea>
    </motion.aside>
  );
}
