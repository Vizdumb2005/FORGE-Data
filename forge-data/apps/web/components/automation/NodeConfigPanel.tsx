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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  lastRunOutput?: Record<string, unknown> | null;
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
  lastRunOutput,
}: NodeConfigPanelProps) {
  const [label, setLabel] = useState("");
  const [retryCount, setRetryCount] = useState(0);
  const [timeoutSeconds, setTimeoutSeconds] = useState(30);
  const [onFailure, setOnFailure] = useState<"stop" | "continue" | "branch">("stop");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [activeTab, setActiveTab] = useState("config");

  useEffect(() => {
    if (!node) return;
    setLabel(node.label ?? "");
    setRetryCount(node.retry_count ?? 0);
    setTimeoutSeconds(node.timeout_seconds ?? 30);
    setOnFailure(node.on_failure ?? "stop");
    setConfig(node.config ?? {});
    setActiveTab("config");
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

  const outputJson = useMemo(() => {
    if (!lastRunOutput) return "{}";
    return JSON.stringify(lastRunOutput, null, 2);
  }, [lastRunOutput]);

  if (!open || !node) return null;

  const hasOutput = lastRunOutput && Object.keys(lastRunOutput).length > 0;

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
      <Tabs value={activeTab} onValueChange={setActiveTab} className="h-[calc(100%-49px)]">
        <TabsList className="mx-3 mt-2 w-[calc(100%-24px)] bg-[#1a1f2b]">
          <TabsTrigger value="config" className="data-[state=active]:bg-[#f97316] data-[state=active]:text-black">
            Config
          </TabsTrigger>
          <TabsTrigger 
            value="output" 
            disabled={!hasOutput}
            className="data-[state=active]:bg-[#f97316] data-[state=active]:text-black disabled:opacity-50"
          >
            Output
          </TabsTrigger>
        </TabsList>
        
        <TabsContent value="config" className="h-[calc(100%-60px)] mt-0">
          <ScrollArea className="h-full">
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
                  placeholder="Notification subject"
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
                aria-label="Wait duration in seconds"
              />
            </div>
          )}

          {/* Quant & Markets Nodes */}
          {node.type === "fetch_market_data" && (
            <>
              <div className="space-y-1.5">
                <Label>Ticker</Label>
                <Input
                  value={String(config.ticker ?? "AAPL")}
                  placeholder="AAPL"
                  onChange={(e) => setConfig((prev) => ({ ...prev, ticker: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Data Source</Label>
                <Select
                  value={String(config.source ?? "yahoo")}
                  onValueChange={(value) => setConfig((prev) => ({ ...prev, source: value }))}
                >
                  <SelectTrigger><SelectValue placeholder="Select data source" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="yahoo">Yahoo Finance</SelectItem>
                    <SelectItem value="alpha_vantage">Alpha Vantage</SelectItem>
                    <SelectItem value="polygon">Polygon</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {node.type === "calc_indicators" && (
            <>
              <div className="space-y-1.5">
                <Label>Indicator Type</Label>
                <Select
                  value={String(config.indicator ?? "sma")}
                  onValueChange={(value) => setConfig((prev) => ({ ...prev, indicator: value }))}
                >
                  <SelectTrigger><SelectValue placeholder="Select indicator" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="sma">SMA (Simple Moving Average)</SelectItem>
                    <SelectItem value="ema">EMA (Exponential Moving Average)</SelectItem>
                    <SelectItem value="rsi">RSI (Relative Strength Index)</SelectItem>
                    <SelectItem value="macd">MACD</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>Period</Label>
                <Input
                  type="number"
                  placeholder="14"
                  value={Number(config.period ?? 14)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, period: Number(e.target.value) }))}
                />
              </div>
            </>
          )}

          {node.type === "backtest" && (
            <>
              <div className="space-y-1.5">
                <Label>Strategy</Label>
                <Input
                  value={String(config.strategy ?? "sma_crossover")}
                  placeholder="sma_crossover"
                  onChange={(e) => setConfig((prev) => ({ ...prev, strategy: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label>Start Date</Label>
                  <Input
                    type="date"
                    placeholder="2023-01-01"
                    value={String(config.start_date ?? "2023-01-01")}
                    onChange={(e) => setConfig((prev) => ({ ...prev, start_date: e.target.value }))}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>End Date</Label>
                  <Input
                    type="date"
                    placeholder="2024-01-01"
                    value={String(config.end_date ?? "2024-01-01")}
                    onChange={(e) => setConfig((prev) => ({ ...prev, end_date: e.target.value }))}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Initial Capital</Label>
                <Input
                  type="number"
                  placeholder="100000"
                  value={Number(config.initial_capital ?? 100000)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, initial_capital: Number(e.target.value) }))}
                />
              </div>
            </>
          )}

          {node.type === "broker_order" && (
            <>
              <div className="space-y-1.5">
                <Label>Ticker</Label>
                <Input
                  value={String(config.ticker ?? "AAPL")}
                  placeholder="AAPL"
                  onChange={(e) => setConfig((prev) => ({ ...prev, ticker: e.target.value }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label>Action</Label>
                  <Select
                    value={String(config.action ?? "buy")}
                    onValueChange={(value) => setConfig((prev) => ({ ...prev, action: value }))}
                  >
                    <SelectTrigger><SelectValue placeholder="Select action" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="buy">Buy</SelectItem>
                      <SelectItem value="sell">Sell</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Order Type</Label>
                  <Select
                    value={String(config.order_type ?? "market")}
                    onValueChange={(value) => setConfig((prev) => ({ ...prev, order_type: value }))}
                  >
                    <SelectTrigger><SelectValue placeholder="Select order type" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="market">Market</SelectItem>
                      <SelectItem value="limit">Limit</SelectItem>
                      <SelectItem value="stop">Stop</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Quantity</Label>
                <Input
                  type="number"
                  placeholder="100"
                  value={Number(config.quantity ?? 100)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, quantity: Number(e.target.value) }))}
                />
              </div>
            </>
          )}

          {node.type === "portfolio_rebalance" && (
            <>
              <div className="space-y-1.5">
                <Label>Target Weights (JSON)</Label>
                <div className="monaco-wrapper">
                  <MonacoEditor
                    height="120px"
                    language="json"
                    theme="vs-dark"
                    value={String(JSON.stringify(config.target_weights ?? { "AAPL": 0.3, "GOOGL": 0.3, "MSFT": 0.4 }, null, 2))}
                    onChange={(value) => {
                      try {
                        const parsed = JSON.parse(value ?? "{}");
                        setConfig((prev) => ({ ...prev, target_weights: parsed }));
                      } catch {}
                    }}
                    options={{ minimap: { enabled: false }, fontSize: 12 }}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Tolerance</Label>
                <Input
                  type="number"
                  step={0.01}
                  placeholder="0.05"
                  value={Number(config.tolerance ?? 0.05)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, tolerance: Number(e.target.value) }))}
                />
              </div>
            </>
          )}

          {/* State & Looping Nodes */}
          {node.type === "get_state" && (
            <div className="space-y-1.5">
              <Label>State Key</Label>
              <Input
                value={String(config.key ?? "")}
                placeholder="portfolio_value"
                onChange={(e) => setConfig((prev) => ({ ...prev, key: e.target.value }))}
              />
            </div>
          )}

          {node.type === "set_state" && (
            <>
              <div className="space-y-1.5">
                <Label>State Key</Label>
                <Input
                  value={String(config.key ?? "")}
                  placeholder="portfolio_value"
                  onChange={(e) => setConfig((prev) => ({ ...prev, key: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Value (JSON)</Label>
                <div className="monaco-wrapper">
                  <MonacoEditor
                    height="120px"
                    language="json"
                    theme="vs-dark"
                    value={String(typeof config.value === "object" ? JSON.stringify(config.value, null, 2) : config.value ?? "{}")}
                    onChange={(value) => {
                      try {
                        const parsed = JSON.parse(value ?? "{}");
                        setConfig((prev) => ({ ...prev, value: parsed }));
                      } catch {}
                    }}
                    options={{ minimap: { enabled: false }, fontSize: 12 }}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>TTL (seconds)</Label>
                <Input
                  type="number"
                  placeholder="3600"
                  value={Number(config.ttl ?? 3600)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, ttl: Number(e.target.value) }))}
                />
              </div>
            </>
          )}

          {node.type === "loop_start" && (
            <>
              <div className="space-y-1.5">
                <Label>Array (JSON or Jinja2)</Label>
                <Textarea
                  rows={4}
                  value={String(config.array ?? "[]")}
                  placeholder='{{ outputs["node_id"]["prices"] }}'
                  onChange={(e) => setConfig((prev) => ({ ...prev, array: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Current Index</Label>
                <Input
                  type="number"
                  placeholder="0"
                  value={Number(config.current_index ?? 0)}
                  onChange={(e) => setConfig((prev) => ({ ...prev, current_index: Number(e.target.value) }))}
                />
              </div>
            </>
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
                aria-label="Retry count"
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
        </TabsContent>

        <TabsContent value="output" className="h-[calc(100%-60px)] mt-0">
          <ScrollArea className="h-full">
            <div className="space-y-4 p-3">
              <div className="space-y-1.5">
                <Label>Last Run Output (JSON)</Label>
                <p className="text-xs text-forge-muted">
                  Use this output in other nodes with: <code className="text-[#f97316]">{`{{ outputs["${node.id}"]["key"] }}`}</code>
                </p>
                <div className="monaco-wrapper rounded-md border border-forge-border">
                  <MonacoEditor
                    height="400px"
                    language="json"
                    theme="vs-dark"
                    value={outputJson}
                    options={{ 
                      minimap: { enabled: false }, 
                      fontSize: 12,
                      readOnly: true,
                      domReadOnly: true,
                    }}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-forge-muted">Available Keys</Label>
                <div className="flex flex-wrap gap-1">
                  {lastRunOutput && Object.keys(lastRunOutput).map((key) => (
                    <code 
                      key={key} 
                      className="rounded bg-[#1a1f2b] px-2 py-1 text-xs text-forge-muted cursor-pointer hover:text-[#f97316]"
                      onClick={() => {
                        navigator.clipboard.writeText(`{{ outputs["${node.id}"]["${key}"] }}`);
                      }}
                      title="Click to copy Jinja2 expression"
                    >
                      {key}
                    </code>
                  ))}
                </div>
              </div>
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </motion.aside>
  );
}
