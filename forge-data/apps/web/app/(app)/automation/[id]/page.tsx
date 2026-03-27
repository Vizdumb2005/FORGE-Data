"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { ArrowLeft, Play, Save } from "lucide-react";
import NodePalette from "@/components/automation/NodePalette";
import NodeConfigPanel from "@/components/automation/NodeConfigPanel";
import RunLogPanel from "@/components/automation/RunLogPanel";
import WorkflowCanvas from "@/components/automation/WorkflowCanvas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listDatasets } from "@/lib/api/datasets";
import {
  deleteWorkflowNode,
  getWorkflow,
  listWorkflowEdges,
  listWorkflowNodes,
  runWorkflow,
  updateWorkflow,
  updateWorkflowNode,
} from "@/lib/api/automation";
import { useWebSocket } from "@/lib/hooks/useWebSocket";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import type { AutomationEdge, AutomationNode, Dataset } from "@/types";

const EMPTY_NODE_STATUS_MAP: Record<string, "pending" | "running" | "success" | "failed" | "skipped"> = {};

export default function WorkflowBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const workflowId = id;

  const setWorkflowStatus = useWorkspaceStore((s) => s.setWorkflowStatus);
  const rawNodeStatusMap = useWorkspaceStore((s) => s.workflowNodeStatusById[workflowId]);
  const handleRunStarted = useWorkspaceStore((s) => s.handleWorkflowRunStarted);
  const activeWorkspaceId = useWorkspaceStore((s) => s.activeWorkspace?.id ?? null);
  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const fetchWorkspaces = useWorkspaceStore((s) => s.fetchWorkspaces);
  const fallbackWorkspaceId = workspaces[0]?.id ?? null;
  const workspaceId = activeWorkspaceId ?? fallbackWorkspaceId;
  const nodeStatusMap = rawNodeStatusMap ?? EMPTY_NODE_STATUS_MAP;

  useWebSocket({ workflowId, workspaceId });

  const [loading, setLoading] = useState(true);
  const [workflowName, setWorkflowName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [nodes, setNodes] = useState<AutomationNode[]>([]);
  const [edges, setEdges] = useState<AutomationEdge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [logOpen, setLogOpen] = useState(true);
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    if (!workflowId) return;
    const load = async () => {
      setLoading(true);
      try {
        const [wf, wfNodes, wfEdges] = await Promise.all([
          getWorkflow(workflowId),
          listWorkflowNodes(workflowId),
          listWorkflowEdges(workflowId),
        ]);
        setWorkflowName(wf.name);
        setIsActive(wf.is_active);
        setNodes(wfNodes);
        setEdges(wfEdges);
        setWorkflowStatus(workflowId, wf.last_run_status);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [setWorkflowStatus, workflowId]);

  useEffect(() => {
    if (!workspaceId && workspaces.length === 0) {
      void fetchWorkspaces();
    }
  }, [fetchWorkspaces, workspaceId, workspaces.length]);

  useEffect(() => {
    if (!workspaceId) {
      setDatasets([]);
      return;
    }
    const loadDatasets = async () => {
      try {
        const data = await listDatasets(workspaceId);
        setDatasets(data);
      } catch {
        setDatasets([]);
      }
    };
    void loadDatasets();
  }, [workspaceId]);

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );

  if (loading) return <div className="p-6 text-sm text-forge-muted">Loading workflow...</div>;

  return (
    <div className="flex h-full flex-col bg-[#0a0c10]">
      <div className="flex h-12 items-center justify-between border-b border-forge-border px-3">
        <div className="flex items-center gap-2">
          <Link href="/automation" className="inline-flex items-center gap-1 text-xs text-forge-muted hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" />
            Back
          </Link>
          <Input
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            className="h-8 w-[260px] border-forge-border bg-forge-surface"
          />
          <button
            onClick={() => setIsActive((v) => !v)}
            className={`rounded-full px-2 py-1 text-[11px] ${isActive ? "bg-green-900/40 text-green-300" : "bg-forge-border text-forge-muted"}`}
          >
            {isActive ? "active" : "inactive"}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              await updateWorkflow(workflowId, { name: workflowName, is_active: isActive });
            }}
          >
            <Save className="h-4 w-4" />
            Save
          </Button>
          <Button
            className="bg-[#f97316] text-black hover:bg-[#ea580c]"
            onClick={async () => {
              const result = await runWorkflow(workflowId);
              handleRunStarted(workflowId, result.run_id);
            }}
          >
            <Play className="h-4 w-4" />
            Run Now
          </Button>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1">
        <NodePalette />

        <div className="relative min-h-0 flex-1">
          <WorkflowCanvas
            workflowId={workflowId}
            nodes={nodes}
            edges={edges}
            nodeStatuses={nodeStatusMap}
            onNodeSelect={(nodeId) => {
              setSelectedNodeId(nodeId);
              setConfigOpen(true);
            }}
            onNodesUpdated={setNodes}
            onNodeAdded={(node) => setNodes((prev) => [...prev, node])}
            onEdgesUpdated={setEdges}
            onEdgeAdded={(edge) => setEdges((prev) => [...prev, edge])}
            onEdgeDeleted={(edgeId) => setEdges((prev) => prev.filter((e) => e.id !== edgeId))}
          />

          <AnimatePresence>
            {configOpen && (
              <NodeConfigPanel
                open={configOpen}
                node={selectedNode}
                datasets={datasets}
                onClose={() => setConfigOpen(false)}
                onUpdate={async (nodeId, patch) => {
                  const updated = await updateWorkflowNode(workflowId, nodeId, patch);
                  setNodes((prev) => prev.map((n) => (n.id === updated.id ? updated : n)));
                }}
                onDelete={async (nodeId) => {
                  await deleteWorkflowNode(workflowId, nodeId);
                  setNodes((prev) => prev.filter((n) => n.id !== nodeId));
                }}
              />
            )}
          </AnimatePresence>
        </div>
      </div>

      <RunLogPanel workflowId={workflowId} open={logOpen} onToggle={() => setLogOpen((v) => !v)} />
    </div>
  );
}
