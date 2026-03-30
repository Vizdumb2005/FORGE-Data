"use client";

import { Play, Trash2, Code2, FileText, BarChart2, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Cell } from "@/types";

const CELL_TYPE_ICONS = {
  code: Code2,
  sql: Code2,
  markdown: FileText,
  chart: BarChart2,
  ai_chat: Bot,
};

interface CellToolbarProps {
  cell: Cell;
  running: boolean;
  onRun: () => void;
  onDelete: () => void;
}

export default function CellToolbar({ cell, running, onRun, onDelete }: CellToolbarProps) {
  const Icon = CELL_TYPE_ICONS[cell.cell_type] ?? Code2;
  const canRun = cell.cell_type === "code" || cell.cell_type === "sql";

  return (
    <div className="flex items-center justify-between border-b border-forge-border bg-forge-bg/60 px-3 py-1.5">
      <div className="flex items-center gap-1.5 text-xs text-forge-muted">
        <Icon className="h-3.5 w-3.5" />
        <span className="capitalize">{cell.cell_type.replace("_", " ")}</span>
        {cell.language && (
          <span className="ml-1 rounded bg-forge-border px-1.5 py-0.5 font-mono text-[10px]">
            {cell.language}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1">
        {canRun && (
          <button
            onClick={onRun}
            disabled={running}
            className={cn(
              "flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors",
              running
                ? "text-forge-muted"
                : "text-forge-accent hover:bg-forge-accent/10"
            )}
          >
            <Play className="h-3 w-3" />
            {running ? "Running…" : "Run"}
          </button>
        )}
        <button
          onClick={onDelete}
          className="rounded p-0.5 text-forge-muted hover:bg-red-900/30 hover:text-red-400"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}
