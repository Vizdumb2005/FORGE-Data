"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import dagre from "dagre";
import {
  Background,
  Controls,
  MiniMap,
  type Edge as FlowEdge,
  type Node as FlowNode,
  MarkerType,
} from "@xyflow/react";
import { Database, Code2, Brain, Share2 } from "lucide-react";
import type { WorkspaceLineageResponse } from "@/lib/api/lineage";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

const ReactFlow = dynamic(
  () => import("@xyflow/react").then((m) => m.ReactFlow),
  { ssr: false },
);

type Direction = "LR" | "TB";
type NodeFilter = "all" | "dataset" | "cell" | "model";
type TimeFilter = "24h" | "7d" | "30d" | "all";

interface LineageViewProps {
  lineage: WorkspaceLineageResponse;
}

export default function LineageView({ lineage }: LineageViewProps) {
  const [direction, setDirection] = useState<Direction>("LR");
  const [nodeFilter, setNodeFilter] = useState<NodeFilter>("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const now = Date.now();
  const cutoffMs =
    timeFilter === "24h"
      ? 24 * 60 * 60 * 1000
      : timeFilter === "7d"
        ? 7 * 24 * 60 * 60 * 1000
        : timeFilter === "30d"
          ? 30 * 24 * 60 * 60 * 1000
          : null;

  const filtered = useMemo(() => {
    const nodes = lineage.nodes.filter((n) => (nodeFilter === "all" ? true : n.type === nodeFilter));
    const nodeIdSet = new Set(nodes.map((n) => n.id));
    const edges = lineage.edges.filter((e) => {
      if (!nodeIdSet.has(e.source) || !nodeIdSet.has(e.target)) return false;
      if (!cutoffMs || !e.last_seen_at) return true;
      const age = now - new Date(e.last_seen_at).getTime();
      return age <= cutoffMs;
    });
    const connectedNodeIds = new Set<string>();
    edges.forEach((e) => {
      connectedNodeIds.add(e.source);
      connectedNodeIds.add(e.target);
    });
    return {
      nodes: nodes.filter((n) => connectedNodeIds.size === 0 || connectedNodeIds.has(n.id)),
      edges,
    };
  }, [lineage, nodeFilter, cutoffMs, now]);

  const graph = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: direction, ranksep: 90, nodesep: 50 });

    for (const node of filtered.nodes) {
      g.setNode(node.id, { width: 250, height: 82 });
    }
    for (const edge of filtered.edges) {
      g.setEdge(edge.source, edge.target);
    }
    dagre.layout(g);

    const nodes: FlowNode[] = filtered.nodes.map((node) => {
      const pos = g.node(node.id) ?? { x: node.position.x, y: node.position.y };
      const style = nodeStyle(node.type);
      return {
        id: node.id,
        position: { x: pos.x, y: pos.y },
        data: { ...node },
        style,
        type: "default",
      };
    });

    const edges: FlowEdge[] = filtered.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label ?? undefined,
      animated: edge.is_active || edge.is_recent,
      style: edge.is_recent
        ? { stroke: "#22d3ee", strokeWidth: 2.2 }
        : { stroke: "#6b7280", strokeWidth: 1.4, strokeDasharray: "6 6" },
      markerEnd: { type: MarkerType.ArrowClosed, color: edge.is_recent ? "#22d3ee" : "#9ca3af" },
    }));

    return { nodes, edges };
  }, [filtered, direction]);

  const selected = useMemo(
    () => lineage.nodes.find((n) => n.id === selectedNodeId) ?? null,
    [lineage.nodes, selectedNodeId],
  );

  return (
    <div className="relative h-[78vh] rounded-xl border border-forge-border bg-[#0a0c10] text-foreground">
      <div className="absolute right-3 top-3 z-20 flex items-center gap-2 rounded-md border border-forge-border bg-forge-surface/90 p-2 backdrop-blur">
        <Select value={direction} onValueChange={(v) => setDirection(v as Direction)}>
          <SelectTrigger className="h-8 w-[90px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="LR">LR</SelectItem>
            <SelectItem value="TB">TB</SelectItem>
          </SelectContent>
        </Select>
        <Select value={nodeFilter} onValueChange={(v) => setNodeFilter(v as NodeFilter)}>
          <SelectTrigger className="h-8 w-[130px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="dataset">Datasets</SelectItem>
            <SelectItem value="cell">Cells</SelectItem>
            <SelectItem value="model">Models</SelectItem>
          </SelectContent>
        </Select>
        <Select value={timeFilter} onValueChange={(v) => setTimeFilter(v as TimeFilter)}>
          <SelectTrigger className="h-8 w-[120px]"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="24h">24h</SelectItem>
            <SelectItem value="7d">7d</SelectItem>
            <SelectItem value="30d">30d</SelectItem>
            <SelectItem value="all">All</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        fitView
        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
      >
        <Background gap={18} size={1} color="#111827" />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>

      <div className="pointer-events-none absolute inset-0">
        {graph.nodes.map((n) => (
          <div
            key={`overlay-${n.id}`}
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: n.position.x + 125, top: n.position.y + 41 }}
          >
            <NodeCard
              label={(n.data as any).label as string}
              type={(n.data as any).type as string}
              metadata={(n.data as any).metadata as Record<string, unknown>}
            />
          </div>
        ))}
      </div>

      {selected ? (
        <div className="absolute right-3 top-16 z-20 w-[340px] rounded-lg border border-forge-border bg-forge-surface/95 p-3 shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-semibold">{selected.label}</p>
            <Button size="sm" variant="ghost" onClick={() => setSelectedNodeId(null)}>Close</Button>
          </div>
          <p className="text-xs text-forge-muted">Type: {selected.type}</p>
          <pre className="mt-2 max-h-[260px] overflow-auto rounded bg-forge-bg p-2 text-[11px] text-forge-muted">
            {JSON.stringify(selected.metadata ?? {}, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function nodeStyle(type: string): React.CSSProperties {
  if (type === "dataset") return { background: "transparent", border: "none", width: 250, height: 82 };
  if (type === "cell") return { background: "transparent", border: "none", width: 250, height: 82 };
  if (type === "model") return { background: "transparent", border: "none", width: 250, height: 82 };
  return { background: "transparent", border: "none", width: 250, height: 82 };
}

function NodeCard({
  label,
  type,
  metadata,
}: {
  label: string;
  type: string;
  metadata: Record<string, unknown>;
}) {
  const icon = type === "dataset" ? <Database className="h-4 w-4" /> : type === "cell" ? <Code2 className="h-4 w-4" /> : type === "model" ? <Brain className="h-4 w-4" /> : <Share2 className="h-4 w-4" />;
  const palette = type === "dataset"
    ? "border-cyan-500/60 shadow-cyan-500/20 bg-cyan-500/5"
    : type === "cell"
      ? "border-amber-500/60 shadow-amber-500/20 bg-amber-500/5"
      : type === "model"
        ? "border-purple-500/60 shadow-purple-500/20 bg-purple-500/5"
        : "border-slate-500/60 shadow-slate-500/20 bg-slate-500/5";
  return (
    <div className={`w-[250px] rounded-lg border p-3 shadow-lg ${palette}`}>
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 text-[10px] text-forge-muted">
        {Object.entries(metadata).slice(0, 4).map(([k, v]) => (
          <div key={k} className="truncate">
            <span className="text-foreground/80">{k}:</span> {String(v)}
          </div>
        ))}
      </div>
    </div>
  );
}

