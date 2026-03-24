"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { MlflowRun } from "@/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface RunDetailPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  run: MlflowRun | null;
  onDeploy: (modelName: string) => Promise<void>;
}

export default function RunDetailPanel({ open, onOpenChange, run, onDeploy }: RunDetailPanelProps) {
  const [modelName, setModelName] = useState("model");
  const [deploying, setDeploying] = useState(false);
  const metricKeys = useMemo(() => Object.keys(run?.metrics ?? {}), [run]);

  const deploy = async () => {
    if (!run) return;
    setDeploying(true);
    try {
      await onDeploy(modelName.trim() || "model");
    } finally {
      setDeploying(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[700px] max-w-[95vw] overflow-auto">
        <SheetHeader>
          <SheetTitle>Run details</SheetTitle>
          <SheetDescription>{run?.run_name || run?.run_id || "No run selected"}</SheetDescription>
        </SheetHeader>
        {run ? (
          <div className="p-4">
            <Tabs defaultValue="overview">
              <TabsList className="bg-forge-bg/60">
                <TabsTrigger value="overview">Overview</TabsTrigger>
                <TabsTrigger value="params">Params</TabsTrigger>
                <TabsTrigger value="metrics">Metrics</TabsTrigger>
                <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
                <TabsTrigger value="model">Model</TabsTrigger>
              </TabsList>

              <TabsContent value="overview" className="space-y-3">
                <div className="rounded border border-forge-border p-3">
                  <div className="text-sm text-forge-muted">Run Name</div>
                  <div className="font-semibold">{run.run_name || run.run_id}</div>
                </div>
                <div className="rounded border border-forge-border p-3">
                  <div className="text-sm text-forge-muted">Status</div>
                  <Badge variant={run.status === "FINISHED" ? "success" : "warning"}>{run.status}</Badge>
                </div>
                <div className="rounded border border-forge-border p-3">
                  <div className="text-sm text-forge-muted">Started</div>
                  <div>{run.start_time ? new Date(run.start_time).toLocaleString() : "N/A"}</div>
                </div>
                <div className="rounded border border-forge-border p-3">
                  <div className="text-sm text-forge-muted">Duration</div>
                  <div>{run.duration ? `${run.duration.toFixed(2)}s` : "N/A"}</div>
                </div>
              </TabsContent>

              <TabsContent value="params">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-forge-muted">
                      <th className="py-2">Key</th>
                      <th className="py-2">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(run.params).map(([k, v]) => (
                      <tr key={k} className="border-t border-forge-border/50">
                        <td className="py-2 font-mono">{k}</td>
                        <td className="py-2">{v}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TabsContent>

              <TabsContent value="metrics" className="space-y-4">
                {metricKeys.length > 0 ? (
                  <>
                    <Plot
                      data={metricKeys.map((k, i) => ({
                        x: [0, 1],
                        y: [run.metrics[k], run.metrics[k]],
                        mode: "lines+markers",
                        name: k,
                        line: { width: 2 + (i % 2) },
                      }))}
                      layout={{
                        title: { text: "Metric values (interactive)" },
                        paper_bgcolor: "transparent",
                        plot_bgcolor: "transparent",
                        font: { color: "#e2e8f0" },
                        autosize: true,
                      }}
                      config={{ responsive: true, scrollZoom: true, displaylogo: false }}
                      style={{ width: "100%", height: 320 }}
                    />
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-forge-muted">
                          <th className="py-2">Metric</th>
                          <th className="py-2">Final Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {metricKeys.map((k) => (
                          <tr key={k} className="border-t border-forge-border/50">
                            <td className="py-2 font-mono">{k}</td>
                            <td className="py-2">{run.metrics[k]}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                ) : (
                  <div className="text-sm text-forge-muted">No metrics logged.</div>
                )}
              </TabsContent>

              <TabsContent value="artifacts">
                <div className="rounded border border-forge-border p-3 text-sm text-forge-muted">
                  Artifact browser placeholder (download links from MLflow artifacts API).
                </div>
              </TabsContent>

              <TabsContent value="model" className="space-y-3">
                <div className="text-sm text-forge-muted">
                  If this run logged a model, deploy it to registry.
                </div>
                <div className="flex items-center gap-2">
                  <Input value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="model name" />
                  <Button onClick={deploy} disabled={deploying}>
                    {deploying ? "Deploying..." : "Deploy"}
                  </Button>
                </div>
              </TabsContent>
            </Tabs>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}

