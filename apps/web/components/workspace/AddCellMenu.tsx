"use client";

import { useState, useRef } from "react";
import { Plus, Code2, FileText, BarChart2, Bot, Database } from "lucide-react";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import type { CellType } from "@/types";

const CELL_OPTIONS: { type: CellType; label: string; icon: React.ElementType; language?: string }[] = [
  { type: "code", label: "Python cell", icon: Code2, language: "python" },
  { type: "code", label: "R cell", icon: Code2, language: "r" },
  { type: "sql", label: "SQL cell", icon: Database, language: "sql" },
  { type: "markdown", label: "Markdown", icon: FileText, language: "markdown" },
  { type: "chart", label: "Chart", icon: BarChart2 },
  { type: "ai_chat", label: "AI Chat", icon: Bot },
];

interface AddCellMenuProps {
  workspaceId: string;
}

let _cellCounter = 0;

export default function AddCellMenu({ workspaceId }: AddCellMenuProps) {
  const [open, setOpen] = useState(false);
  const createCell = useWorkspaceStore((s) => s.createCell);
  const menuRef = useRef<HTMLDivElement>(null);

  const add = async (type: CellType, language?: string) => {
    _cellCounter += 1;
    await createCell(workspaceId, {
      cell_type: type,
      ...(language ? { language: language as never } : {}),
      content: "",
      position_x: 80 + (_cellCounter % 6) * 360,
      position_y: 80 + Math.floor(_cellCounter / 6) * 240,
    });
    setOpen(false);
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 rounded-full bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg shadow-lg hover:bg-forge-accent-dim"
      >
        <Plus className="h-4 w-4" />
        Add cell
      </button>

      {open && (
        <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 overflow-hidden rounded-lg border border-forge-border bg-forge-surface shadow-xl">
          {CELL_OPTIONS.map(({ type, label, icon: Icon, language }) => (
            <button
              key={type}
              onClick={() => add(type, language)}
              className="flex w-48 items-center gap-2.5 px-4 py-2.5 text-sm text-foreground hover:bg-forge-accent/10 hover:text-forge-accent"
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
