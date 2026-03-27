"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  applyEdgeChanges,
  useReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type EdgeChange,
  type NodeMouseHandler,
  type Connection,
} from "@xyflow/react";
import type { DragEvent } from "react";
import "@xyflow/react/dist/style.css";
import { Loader2, CheckCircle2, CircleX, Dot } from "lucide-react";
import {
  createWorkflowNode,
  updateWorkflowNode,
  createWorkflowEdge,
  deleteWorkflowEdge,
} from "@/lib/api/automation";
import { getDraggedNodeType, setDraggedNodeType } from "@/lib/automation/dnd";
import type { AutomationEdge, AutomationNode, AutomationNodeRunStatus, AutomationNodeType } from "@/types";

const NODE_COLOR: Record<AutomationNodeType, string> = {
  code_cell: "#2563eb",
  sql_query: "#0ea5e9",
  upload_dataset: "#06b6d4",
  trigger: "#f97316",
  conditional: "#f59e0b",
  wait: "#eab308",
  email_notify: "#a855f7",
  api_call: "#22c55e",
  retrain: "#ef4444",
  publish_dashboard: "#f97316",
};

function statusIcon(status: AutomationNodeRunStatus | undefined) {
  if (status === "running") {
    return <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-300" />;
  }
  if (status === "success") {
    return <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />;
  }
  if (status === "failed") {
    return <CircleX className="h-3.5 w-3.5 text-red-400" />;
  }
  return <Dot className="h-4 w-4 text-forge-muted" />;
}

interface WorkflowCanvasProps {
  workflowId: string;
  nodes: AutomationNode[];
  edges: AutomationEdge[];
  nodeStatuses: Record<string, AutomationNodeRunStatus>;
  onNodeSelect: (nodeId: string) => void;
  onNodesUpdated: (nodes: AutomationNode[]) => void;
  onNodeAdded: (node: AutomationNode) => void;
  onEdgesUpdated: (edges: AutomationEdge[]) => void;
  onEdgeAdded: (edge: AutomationEdge) => void;
  onEdgeDeleted: (edgeId: string) => void;
}

export default function WorkflowCanvas(props: WorkflowCanvasProps) {
  return (
    <ReactFlowProvider>
      <FlowInner {...props} />
    </ReactFlowProvider>
  );
}

function FlowInner({
  workflowId,
  nodes,
  edges,
  nodeStatuses,
  onNodeSelect,
  onNodesUpdated,
  onNodeAdded,
  onEdgesUpdated,
  onEdgeAdded,
  onEdgeDeleted,
}: WorkflowCanvasProps) {
  const { screenToFlowPosition } = useReactFlow();

  const flowNodes: Node[] = nodes.map((node) => ({
    id: node.id,
    type: "default",
    position: { x: node.position_x, y: node.position_y },
    data: {
      label: (
        <div className="w-[220px] overflow-hidden rounded-lg border border-forge-border bg-[#111723] text-xs">
          <div
            className="flex items-center justify-between px-2 py-1 text-[11px] font-semibold text-black"
            style={{ backgroundColor: NODE_COLOR[node.type] }}
          >
            <span>{node.type.replace("_", " ")}</span>
            <span className="rounded bg-black/30 px-1 py-0.5 text-[10px] text-white">{node.label}</span>
          </div>
          <div className="flex items-center justify-between px-2 py-1.5 text-forge-muted">
            <span>{node.id.slice(0, 6)}</span>
            {statusIcon(nodeStatuses[node.id])}
          </div>
        </div>
      ),
    },
  }));

  const flowEdges: Edge[] = edges.map((edge) => ({
    id: edge.id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    animated: edge.type === "on_success",
    style:
      edge.type === "on_success"
        ? { stroke: "#22c55e", strokeDasharray: "6 4" }
        : edge.type === "on_failure"
          ? { stroke: "#ef4444", strokeDasharray: "2 5" }
          : { stroke: "#f8fafc" },
  }));

  const onNodesChange = (changes: NodeChange<Node>[]) => {
    const map = new Map(nodes.map((n) => [n.id, n]));
    const nextFlowNodes = applyNodeChanges(changes, flowNodes);
    const nextNodes = nextFlowNodes.map((n) => {
      const source = map.get(n.id);
      if (!source) return null;
      return {
        ...source,
        position_x: n.position.x,
        position_y: n.position.y,
      };
    }).filter(Boolean) as AutomationNode[];
    onNodesUpdated(nextNodes);
  };

  const onEdgesChange = async (changes: EdgeChange<Edge>[]) => {
    const nextFlowEdges = applyEdgeChanges(changes, flowEdges);
    for (const change of changes) {
      if (change.type === "remove" && onEdgeDeleted) {
        await deleteWorkflowEdge(workflowId, change.id);
        onEdgeDeleted(change.id);
      }
    }
  };

  const onConnect = async (params: Connection) => {
    if (!params.source || !params.target) return;
    const newEdge = await createWorkflowEdge(workflowId, {
      source_node_id: params.source,
      target_node_id: params.target,
      condition: "on_success",
    });
    if (onEdgeAdded) onEdgeAdded(newEdge);
  };

  const onNodeClick: NodeMouseHandler<Node> = (_, node) => {
    onNodeSelect(node.id);
  };

  const onNodeDragStop: NodeMouseHandler<Node> = async (_, node) => {
    const target = nodes.find((n) => n.id === node.id);
    if (!target) return;
    await updateWorkflowNode(workflowId, node.id, {
      position_x: node.position.x,
      position_y: node.position.y,
    });
  };

  const onDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    const fromDataTransfer =
      (e.dataTransfer.getData("application/forge-node-type") ||
        e.dataTransfer.getData("text/plain")) as AutomationNodeType;
    const nodeType = fromDataTransfer || getDraggedNodeType();
    if (!nodeType) return;
    const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
    try {
      const created = await createWorkflowNode(workflowId, {
        type: nodeType,
        position_x: position.x,
        position_y: position.y,
        label: nodeType.replace("_", " "),
        config: {},
      });
      onNodeAdded(created);
    } catch (error) {
      console.error("Failed to create workflow node on drop", error);
    } finally {
      setDraggedNodeType(null);
    }
  };

  return (
    <div className="h-full w-full bg-[#0a0c10]" onDragOver={onDragOver} onDrop={onDrop}>
      <ReactFlow
        fitView
        nodes={flowNodes}
        edges={flowEdges}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        proOptions={{ hideAttribution: true }}
      >
        <MiniMap nodeColor="#f97316" maskColor="rgba(10,12,16,0.7)" />
        <Controls />
        <Background variant={BackgroundVariant.Dots} color="#283042" gap={18} size={1.4} />
      </ReactFlow>
    </div>
  );
}
