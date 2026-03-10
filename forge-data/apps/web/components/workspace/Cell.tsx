"use client";

import { useState, useCallback } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import dynamic from "next/dynamic";
import { cn } from "@/lib/utils";
import api from "@/lib/api";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import CellToolbar from "./CellToolbar";
import ChartRenderer from "@/components/charts/ChartRenderer";
import type { Cell, ExecuteResponse } from "@/types";

// Monaco Editor is SSR-incompatible — load client-side only
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface CellNodeData {
  cell: Cell;
  workspaceId: string;
}

export default function CellNode({ data, selected }: NodeProps<CellNodeData>) {
  const { cell, workspaceId } = data;
  const [content, setContent] = useState(cell.content);
  const [output, setOutput] = useState(cell.output);
  const [running, setRunning] = useState(false);
  const updateCell = useWorkspaceStore((s) => s.updateCellPosition); // reuse store
  const deleteCell = useWorkspaceStore((s) => s.deleteCell);

  const run = useCallback(async () => {
    if (cell.cell_type !== "code" && cell.cell_type !== "sql") return;
    setRunning(true);
    try {
      const resp = await api.post<ExecuteResponse>(
        `/api/v1/workspaces/${workspaceId}/cells/${cell.id}/execute`,
        { code: content }
      );
      setOutput(resp.data.output);
    } finally {
      setRunning(false);
    }
  }, [cell, workspaceId, content]);

  const handleDelete = () => deleteCell(cell.id, workspaceId);

  return (
    <div
      className={cn(
        "flex flex-col rounded-lg border bg-forge-surface shadow-lg transition-shadow",
        selected ? "border-forge-accent shadow-forge-accent/20" : "border-forge-border"
      )}
      style={{ minWidth: 340, minHeight: 160 }}
    >
      <Handle type="target" position={Position.Left} className="!bg-forge-accent" />

      <CellToolbar
        cell={cell}
        running={running}
        onRun={run}
        onDelete={handleDelete}
      />

      <div className="flex-1 overflow-hidden">
        {cell.cell_type === "code" || cell.cell_type === "sql" ? (
          <MonacoEditor
            height={180}
            language={cell.language ?? "python"}
            theme="vs-dark"
            value={content}
            onChange={(v) => setContent(v ?? "")}
            options={{
              minimap: { enabled: false },
              fontSize: 12,
              lineNumbers: "on",
              wordWrap: "on",
              scrollBeyondLastLine: false,
              padding: { top: 8, bottom: 8 },
            }}
          />
        ) : cell.cell_type === "markdown" ? (
          <div className="prose prose-invert max-w-none p-3 text-sm">
            {content || <span className="text-forge-muted italic">Empty markdown cell</span>}
          </div>
        ) : cell.cell_type === "chart" && output ? (
          <div className="p-2">
            <ChartRenderer output={output} />
          </div>
        ) : null}
      </div>

      {/* Output area */}
      {output && (cell.cell_type === "code" || cell.cell_type === "sql") && (
        <div className="border-t border-forge-border bg-forge-bg px-3 py-2 font-mono text-xs text-foreground max-h-32 overflow-auto">
          {output.error ? (
            <span className="text-red-400">{output.error}</span>
          ) : (
            <pre className="whitespace-pre-wrap">
              {JSON.stringify(output.data, null, 2)}
            </pre>
          )}
        </div>
      )}

      <Handle type="source" position={Position.Right} className="!bg-forge-accent" />
    </div>
  );
}
