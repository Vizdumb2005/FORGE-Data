"use client";

import { useCallback, useRef, useState, useMemo, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Plus,
  ZoomIn,
  ZoomOut,
  Maximize,
  Code2,
  Database,
  FileText,
  BarChart2,
  Bot,
  LayoutList,
  Grid3X3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspaceStore, type CellState } from "@/lib/stores/workspaceStore";
import CellComponent from "./Cell";
import type { CellType, CellLanguage } from "@/types";

// ── Canvas Props ─────────────────────────────────────────────────────────────

interface CanvasProps {
  workspaceId: string;
  onRunCell: (cellId: string) => void;
  onDeleteCell: (cellId: string) => void;
  onContentChange: (cellId: string, content: string) => void;
}

export default function Canvas({ workspaceId, onRunCell, onDeleteCell, onContentChange }: CanvasProps) {
  const cellStates = useWorkspaceStore((s) => s.cellStates);
  const cellOrder = useWorkspaceStore((s) => s.cellOrder);
  const activeCellId = useWorkspaceStore((s) => s.activeCellId);
  const zoom = useWorkspaceStore((s) => s.zoom);
  const setActiveCellId = useWorkspaceStore((s) => s.setActiveCellId);
  const setZoom = useWorkspaceStore((s) => s.setZoom);
  const reorderCells = useWorkspaceStore((s) => s.reorderCells);
  const createCell = useWorkspaceStore((s) => s.createCell);

  const [layoutMode, setLayoutMode] = useState<"list" | "free">("list");
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [addMenuIdx, setAddMenuIdx] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Scroll to newly created cell
  const prevOrderLenRef = useRef(cellOrder.length);
  useEffect(() => {
    if (cellOrder.length > prevOrderLenRef.current) {
      const lastId = cellOrder[cellOrder.length - 1];
      const el = document.getElementById(`cell-${lastId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    prevOrderLenRef.current = cellOrder.length;
  }, [cellOrder.length, cellOrder]);

  // ── DnD Sensors ──────────────────────────────────────────────────────────

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    })
  );

  const handleDragEnd = useCallback((event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = cellOrder.indexOf(active.id as string);
    const newIndex = cellOrder.indexOf(over.id as string);
    if (oldIndex === -1 || newIndex === -1) return;
    reorderCells(arrayMove(cellOrder, oldIndex, newIndex));
  }, [cellOrder, reorderCells]);

  // ── Zoom controls ────────────────────────────────────────────────────────

  const zoomIn = () => setZoom(Math.min(zoom + 0.1, 2));
  const zoomOut = () => setZoom(Math.max(zoom - 0.1, 0.5));
  const zoomReset = () => setZoom(1);

  // Ctrl+scroll zoom
  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.05 : 0.05;
      setZoom(Math.max(0.5, Math.min(2, zoom + delta)));
    }
  }, [zoom, setZoom]);

  // Click empty space to deselect
  const handleBackgroundClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget || e.target === scrollRef.current) {
      setActiveCellId(null);
      setAddMenuOpen(false);
      setAddMenuIdx(null);
    }
  };

  // ── Add cell ─────────────────────────────────────────────────────────────

  const addCell = useCallback(async (type: CellType, language?: CellLanguage, afterIdx?: number) => {
    const yBase = afterIdx != null
      ? (afterIdx + 1) * 300 + 100
      : cellOrder.length * 300 + 100;

    await createCell(workspaceId, {
      cell_type: type,
      ...(language ? { language } : {}),
      content: "",
      position_x: 60,
      position_y: yBase,
    });
    setAddMenuOpen(false);
    setAddMenuIdx(null);
  }, [workspaceId, cellOrder.length, createCell]);

  // ── Minimap ──────────────────────────────────────────────────────────────

  const cellPositions = useMemo(() => {
    return cellOrder.map((id) => {
      const cs = cellStates[id];
      if (!cs) return null;
      return { id, y: cs.cell.position_y, type: cs.cell.cell_type };
    }).filter(Boolean) as { id: string; y: number; type: CellType }[];
  }, [cellOrder, cellStates]);

  return (
    <div className="relative h-full w-full bg-forge-bg overflow-hidden" ref={containerRef}>
      {/* ── Scrollable viewport ───────────────────────────────────────── */}
      <div
        ref={scrollRef}
        className="h-full w-full overflow-auto"
        onWheel={handleWheel}
        onClick={handleBackgroundClick}
      >
        {/* Grid pattern background */}
        <div
          className="relative min-h-[200vh]"
          style={{
            backgroundImage: `
              radial-gradient(circle, #1e2433 1px, transparent 1px)
            `,
            backgroundSize: `${24 * zoom}px ${24 * zoom}px`,
          }}
        >
          <div
            className="mx-auto max-w-[900px] px-8 py-8"
            style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}
          >
            {layoutMode === "list" ? (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={cellOrder} strategy={verticalListSortingStrategy}>
                  <div className="flex flex-col gap-2">
                    {cellOrder.map((cellId, idx) => {
                      const cs = cellStates[cellId];
                      if (!cs) return null;
                      return (
                        <div key={cellId}>
                          {/* Add-cell button between cells */}
                          <AddCellDivider
                            idx={idx}
                            activeIdx={addMenuIdx}
                            onToggle={(i) => setAddMenuIdx(addMenuIdx === i ? null : i)}
                            onAdd={(type, lang) => addCell(type, lang, idx)}
                          />
                          <SortableCell
                            id={cellId}
                            cellState={cs}
                            workspaceId={workspaceId}
                            isActive={activeCellId === cellId}
                            onRun={onRunCell}
                            onDelete={onDeleteCell}
                            onContentChange={onContentChange}
                            onActivate={setActiveCellId}
                          />
                        </div>
                      );
                    })}
                  </div>
                </SortableContext>
              </DndContext>
            ) : (
              // Free-form layout
              <div className="relative" style={{ minHeight: "200vh" }}>
                {cellOrder.map((cellId) => {
                  const cs = cellStates[cellId];
                  if (!cs) return null;
                  return (
                    <div
                      key={cellId}
                      id={`cell-${cellId}`}
                      className="absolute"
                      style={{
                        left: cs.cell.position_x,
                        top: cs.cell.position_y,
                        width: cs.cell.width || 600,
                      }}
                    >
                      <CellComponent
                        cellState={cs}
                        workspaceId={workspaceId}
                        isActive={activeCellId === cellId}
                        onRun={onRunCell}
                        onDelete={onDeleteCell}
                        onContentChange={onContentChange}
                        onActivate={setActiveCellId}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Floating add-cell button ─────────────────────────────────── */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
        <div className="relative">
          <button
            onClick={() => setAddMenuOpen(!addMenuOpen)}
            className="flex items-center gap-1.5 rounded-full bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg shadow-lg hover:bg-forge-accent-dim transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add cell
          </button>

          {addMenuOpen && (
            <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 overflow-hidden rounded-lg border border-forge-border bg-forge-surface shadow-xl">
              {CELL_OPTIONS.map(({ type, label, icon: Icon, language }) => (
                <button
                  key={type + (language ?? "")}
                  onClick={() => addCell(type, language)}
                  className="flex w-48 items-center gap-2.5 px-4 py-2.5 text-sm text-foreground hover:bg-forge-accent/10 hover:text-forge-accent"
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Zoom controls ────────────────────────────────────────────── */}
      <div className="absolute bottom-6 right-6 z-10 flex flex-col gap-1">
        <button onClick={zoomIn} className="rounded-md border border-forge-border bg-forge-surface p-1.5 text-forge-muted hover:text-forge-text hover:bg-forge-border" title="Zoom in">
          <ZoomIn className="h-4 w-4" />
        </button>
        <button onClick={zoomReset} className="rounded-md border border-forge-border bg-forge-surface px-1.5 py-0.5 text-[10px] font-mono text-forge-muted hover:text-forge-text hover:bg-forge-border" title="Reset zoom">
          {Math.round(zoom * 100)}%
        </button>
        <button onClick={zoomOut} className="rounded-md border border-forge-border bg-forge-surface p-1.5 text-forge-muted hover:text-forge-text hover:bg-forge-border" title="Zoom out">
          <ZoomOut className="h-4 w-4" />
        </button>
        <div className="h-px bg-forge-border my-0.5" />
        <button
          onClick={() => setLayoutMode(layoutMode === "list" ? "free" : "list")}
          className="rounded-md border border-forge-border bg-forge-surface p-1.5 text-forge-muted hover:text-forge-text hover:bg-forge-border"
          title={layoutMode === "list" ? "Freeform layout" : "List layout"}
        >
          {layoutMode === "list" ? <Grid3X3 className="h-4 w-4" /> : <LayoutList className="h-4 w-4" />}
        </button>
      </div>

      {/* ── Minimap ──────────────────────────────────────────────────── */}
      <Minimap cells={cellPositions} activeCellId={activeCellId} />
    </div>
  );
}

// ── Sortable Cell Wrapper ────────────────────────────────────────────────────

function SortableCell({
  id,
  cellState,
  workspaceId,
  isActive,
  onRun,
  onDelete,
  onContentChange,
  onActivate,
}: {
  id: string;
  cellState: CellState;
  workspaceId: string;
  isActive: boolean;
  onRun: (cellId: string) => void;
  onDelete: (cellId: string) => void;
  onContentChange: (cellId: string, content: string) => void;
  onActivate: (cellId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 50 : undefined,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} id={`cell-${id}`}>
      <CellComponent
        cellState={cellState}
        workspaceId={workspaceId}
        isActive={isActive}
        onRun={onRun}
        onDelete={onDelete}
        onContentChange={onContentChange}
        onActivate={onActivate}
        dragListeners={listeners}
      />
    </div>
  );
}

// ── Add Cell Divider ─────────────────────────────────────────────────────────

function AddCellDivider({
  idx,
  activeIdx,
  onToggle,
  onAdd,
}: {
  idx: number;
  activeIdx: number | null;
  onToggle: (idx: number) => void;
  onAdd: (type: CellType, language?: CellLanguage) => void;
}) {
  const isOpen = activeIdx === idx;

  return (
    <div className="group/divider relative flex items-center justify-center py-1">
      <div className="h-px flex-1 bg-forge-border/30 group-hover/divider:bg-forge-border transition-colors" />
      <button
        onClick={() => onToggle(idx)}
        className={cn(
          "mx-2 rounded-full p-0.5 transition-all",
          isOpen
            ? "bg-forge-accent text-forge-bg"
            : "bg-forge-border/50 text-forge-muted opacity-0 group-hover/divider:opacity-100 hover:bg-forge-accent hover:text-forge-bg"
        )}
      >
        <Plus className="h-3 w-3" />
      </button>
      <div className="h-px flex-1 bg-forge-border/30 group-hover/divider:bg-forge-border transition-colors" />

      {isOpen && (
        <div className="absolute top-full z-20 mt-1 overflow-hidden rounded-lg border border-forge-border bg-forge-surface shadow-xl">
          <div className="flex gap-0.5 p-1">
            {CELL_OPTIONS.map(({ type, label, icon: Icon, language }) => (
              <button
                key={type + (language ?? "")}
                onClick={() => onAdd(type, language)}
                className="flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs text-foreground hover:bg-forge-accent/10 hover:text-forge-accent whitespace-nowrap"
                title={label}
              >
                <Icon className="h-3.5 w-3.5 shrink-0" />
                {label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Minimap ──────────────────────────────────────────────────────────────────

const MINIMAP_W = 180;
const MINIMAP_H = 120;

const CELL_TYPE_COLORS: Record<CellType, string> = {
  code: "#22c55e",
  sql: "#3b82f6",
  markdown: "#a855f7",
  chart: "#f59e0b",
  ai_chat: "#00e5ff",
};

function Minimap({
  cells,
  activeCellId,
}: {
  cells: { id: string; y: number; type: CellType }[];
  activeCellId: string | null;
}) {
  if (cells.length === 0) return null;

  const maxY = Math.max(...cells.map((c) => c.y), 600);
  const scale = MINIMAP_H / (maxY + 200);

  return (
    <div
      className="absolute bottom-20 right-6 z-10 rounded-md border border-forge-border bg-forge-surface/90 backdrop-blur-sm"
      style={{ width: MINIMAP_W, height: MINIMAP_H }}
    >
      <div className="relative h-full w-full overflow-hidden rounded-md">
        {cells.map((c) => (
          <div
            key={c.id}
            className={cn(
              "absolute left-2 rounded-sm transition-all",
              c.id === activeCellId ? "ring-1 ring-forge-accent" : ""
            )}
            style={{
              top: c.y * scale + 4,
              width: MINIMAP_W - 16,
              height: Math.max(4, 20 * scale),
              backgroundColor: CELL_TYPE_COLORS[c.type] ?? "#64748b",
              opacity: c.id === activeCellId ? 1 : 0.4,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Cell type options ────────────────────────────────────────────────────────

const CELL_OPTIONS: { type: CellType; label: string; icon: typeof Code2; language?: CellLanguage }[] = [
  { type: "code", label: "Python", icon: Code2, language: "python" },
  { type: "sql", label: "SQL", icon: Database, language: "sql" },
  { type: "markdown", label: "Markdown", icon: FileText, language: "markdown" },
  { type: "chart", label: "Chart", icon: BarChart2 },
  { type: "ai_chat", label: "AI Chat", icon: Bot },
];
