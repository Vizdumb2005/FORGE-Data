"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  cancelWorkflowRun,
  listWorkflowRunNodes,
  listWorkflowRuns,
} from "@/lib/api/automation";
import { formatDate } from "@/lib/utils";
import type { AutomationNodeExecution, AutomationRunSummary } from "@/types";

interface RunLogPanelProps {
  workflowId: string;
  open: boolean;
  onToggle: () => void;
}

const STATUS_DOT: Record<string, string> = {
  success: "bg-green-400",
  failed: "bg-red-400",
  running: "bg-yellow-400",
  queued: "bg-yellow-400",
  cancelled: "bg-forge-muted",
};

export default function RunLogPanel({ workflowId, open, onToggle }: RunLogPanelProps) {
  const [runs, setRuns] = useState<AutomationRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [nodes, setNodes] = useState<AutomationNodeExecution[]>([]);

  useEffect(() => {
    if (!workflowId) return;
    let disposed = false;

    const load = async () => {
      const data = await listWorkflowRuns(workflowId);
      if (disposed) return;
      setRuns(data);
      if (!selectedRunId && data.length > 0) {
        setSelectedRunId(data[0].run_id);
      }
    };

    void load();
    const timer = setInterval(() => {
      void load();
    }, 3000);

    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [workflowId, selectedRunId]);

  useEffect(() => {
    if (!workflowId || !selectedRunId) return;
    let disposed = false;

    const loadNodes = async () => {
      const data = await listWorkflowRunNodes(workflowId, selectedRunId);
      if (!disposed) setNodes(data);
    };

    void loadNodes();
    const timer = setInterval(() => {
      void loadNodes();
    }, 3000);

    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [selectedRunId, workflowId]);

  const maxDuration = useMemo(
    () => Math.max(...nodes.map((n) => n.duration_ms ?? 0), 1),
    [nodes],
  );

  return (
    <motion.div
      initial={false}
      animate={{ height: open ? 200 : 34 }}
      className="border-t border-forge-border bg-[#0e1118]"
    >
      <div className="flex h-[34px] items-center justify-between border-b border-forge-border px-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-forge-muted">Run Log</p>
        <Button size="sm" variant="ghost" onClick={onToggle}>{open ? "Hide" : "Show"}</Button>
      </div>

      {open && (
        <div className="grid h-[166px] grid-cols-2">
          <ScrollArea className="border-r border-forge-border">
            <div className="p-2">
              {runs.map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => setSelectedRunId(run.run_id)}
                  className={`mb-1 w-full rounded-md border p-2 text-left text-xs ${
                    selectedRunId === run.run_id
                      ? "border-[#f97316]/70 bg-[#1a1f2b]"
                      : "border-forge-border bg-forge-surface"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px]">{run.run_id.slice(0, 8)}</span>
                    <Badge variant={run.status === "success" ? "success" : run.status === "failed" ? "destructive" : "warning"}>
                      {run.status}
                    </Badge>
                  </div>
                  <div className="mt-1 text-[11px] text-forge-muted">
                    {run.triggered_by ?? "system"} • {run.started_at ? formatDate(run.started_at) : "-"}
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>

          <ScrollArea>
            <div className="space-y-2 p-2">
              {nodes.map((node) => (
                <details key={node.node_id} className="rounded-md border border-forge-border bg-forge-surface p-2">
                  <summary className="cursor-pointer list-none">
                    <div className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${STATUS_DOT[node.status] ?? "bg-forge-muted"}`} />
                        {node.node_label}
                      </span>
                      <span>{node.duration_ms ?? 0} ms</span>
                    </div>
                    <div className="mt-1 h-2 rounded bg-black/30">
                      <div
                        className="h-2 rounded bg-[#f97316]"
                        style={{ width: `${Math.max(((node.duration_ms ?? 0) / maxDuration) * 100, 4)}%` }}
                      />
                    </div>
                  </summary>
                  <textarea
                    readOnly
                    value={node.log ?? ""}
                    className="mt-2 h-20 w-full rounded border border-forge-border bg-[#0a0c10] p-2 text-[11px]"
                  />
                </details>
              ))}

              {runs.find((r) => r.run_id === selectedRunId)?.status === "running" && (
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={async () => {
                    if (!selectedRunId) return;
                    await cancelWorkflowRun(workflowId, selectedRunId);
                  }}
                >
                  Cancel Run
                </Button>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </motion.div>
  );
}
