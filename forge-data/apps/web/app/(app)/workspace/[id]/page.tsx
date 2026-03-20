"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import {
  Play,
  RotateCcw,
  Square,
  Share2,
  Loader2,
  PanelRightOpen,
  PanelRightClose,
  FlaskConical,
  Workflow,
  BookOpenCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/hooks/useWorkspace";
import { useWorkspaceStore, type KernelStatus } from "@/lib/stores/workspaceStore";
import Canvas from "@/components/workspace/Canvas";
import ChatPanel from "@/components/ai/ChatPanel";
import PipelineBuilder from "@/components/ai/PipelineBuilder";
import StatAdvisorPanel from "@/components/ai/StatAdvisorPanel";
import SemanticLayerManager from "@/components/ai/SemanticLayerManager";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { listDatasets } from "@/lib/api/datasets";
import type { Dataset } from "@/types";

// ── Kernel status colors ─────────────────────────────────────────────────────

const KERNEL_STATUS_COLOR: Record<KernelStatus, string> = {
  idle: "bg-green-400",
  busy: "bg-cyan-400 animate-pulse",
  starting: "bg-yellow-400 animate-pulse",
  dead: "bg-red-400",
  unknown: "bg-forge-muted/50",
};

const KERNEL_STATUS_LABEL: Record<KernelStatus, string> = {
  idle: "Idle",
  busy: "Busy",
  starting: "Starting",
  dead: "Dead",
  unknown: "Unknown",
};

// ── Workspace Page ───────────────────────────────────────────────────────────

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const {
    activeWorkspace,
    workspaces,
    cellOrder,
    kernelStatus,
    isRunningAll,
    setActive,
    runCell,
    runAll,
    deleteCell,
    syncContent,
    restartKernel,
    interruptKernel,
    loading,
  } = useWorkspace(id);

  const fetchWorkspaces = useWorkspaceStore((s) => s.fetchWorkspaces);

  // Set active workspace
  useEffect(() => {
    const ws = workspaces.find((w) => w.id === id);
    if (ws) setActive(ws);
  }, [id, workspaces]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Chat panel resize ──────────────────────────────────────────────────

  const [chatWidth, setChatWidth] = useState(360);
  const [chatOpen, setChatOpen] = useState(true);
  const [pipelineOpen, setPipelineOpen] = useState(false);
  const [statAdvisorOpen, setStatAdvisorOpen] = useState(false);
  const [semanticOpen, setSemanticOpen] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const resizing = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = true;

    const startX = e.clientX;
    const startWidth = chatWidth;

    const onMouseMove = (me: MouseEvent) => {
      if (!resizing.current) return;
      const delta = startX - me.clientX;
      setChatWidth(Math.max(300, Math.min(600, startWidth + delta)));
    };

    const onMouseUp = () => {
      resizing.current = false;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, [chatWidth]);

  useEffect(() => {
    if (!id) return;
    void listDatasets(id).then(setDatasets).catch(() => setDatasets([]));
  }, [id]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setChatOpen(true);
      }
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setPipelineOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // ── Loading state ──────────────────────────────────────────────────────

  if (!activeWorkspace) {
    return (
      <div className="flex h-full items-center justify-center text-forge-muted text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" />
        Loading workspace...
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── Top Bar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-forge-border bg-forge-surface px-4 py-2">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-foreground truncate max-w-[200px]">
            {activeWorkspace.name}
          </h1>

          {/* Kernel status */}
          <div className="flex items-center gap-1.5">
            <div className={cn("h-2 w-2 rounded-full", KERNEL_STATUS_COLOR[kernelStatus])} />
            <span className="text-[10px] text-forge-muted font-mono">
              Kernel: {KERNEL_STATUS_LABEL[kernelStatus]}
            </span>
          </div>

          {/* Cell count */}
          <span className="text-[10px] text-forge-muted">
            {cellOrder.length} cell{cellOrder.length !== 1 ? "s" : ""}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {/* Run All */}
          <button
            onClick={runAll}
            disabled={isRunningAll || cellOrder.length === 0}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              isRunningAll
                ? "text-forge-muted bg-forge-border"
                : "text-forge-accent hover:bg-forge-accent/10"
            )}
          >
            {isRunningAll ? (
              <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Running All...</>
            ) : (
              <><Play className="h-3.5 w-3.5" /> Run All</>
            )}
          </button>

          {/* Restart kernel */}
          <button
            onClick={restartKernel}
            className="rounded-md p-1.5 text-forge-muted hover:text-amber-400 hover:bg-amber-900/20 transition-colors"
            title="Restart kernel"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          {/* Interrupt kernel */}
          {kernelStatus === "busy" && (
            <button
              onClick={interruptKernel}
              className="rounded-md p-1.5 text-forge-muted hover:text-red-400 hover:bg-red-900/20 transition-colors"
              title="Interrupt kernel"
            >
              <Square className="h-3.5 w-3.5" />
            </button>
          )}

          {/* Share */}
          <button
            className="rounded-md p-1.5 text-forge-muted hover:text-forge-text hover:bg-forge-border transition-colors"
            title="Share workspace"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => setStatAdvisorOpen(true)}
            className="rounded-md p-1.5 text-forge-muted hover:text-foreground hover:bg-forge-border transition-colors"
            title="Stat advisor"
          >
            <FlaskConical className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => setPipelineOpen(true)}
            className="rounded-md p-1.5 text-forge-muted hover:text-foreground hover:bg-forge-border transition-colors"
            title="Pipeline builder"
          >
            <Workflow className="h-3.5 w-3.5" />
          </button>

          <button
            onClick={() => setSemanticOpen(true)}
            className="rounded-md p-1.5 text-forge-muted hover:text-foreground hover:bg-forge-border transition-colors"
            title="Semantic layer"
          >
            <BookOpenCheck className="h-3.5 w-3.5" />
          </button>

          {/* Toggle chat panel */}
          <button
            onClick={() => setChatOpen(!chatOpen)}
            className={cn(
              "rounded-md p-1.5 transition-colors",
              chatOpen ? "text-forge-accent hover:bg-forge-accent/10" : "text-forge-muted hover:text-forge-text hover:bg-forge-border"
            )}
            title={chatOpen ? "Hide AI panel" : "Show AI panel"}
          >
            {chatOpen ? <PanelRightClose className="h-3.5 w-3.5" /> : <PanelRightOpen className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* Canvas */}
        <div className="flex-1 overflow-hidden">
          <Canvas
            workspaceId={id}
            onRunCell={runCell}
            onDeleteCell={deleteCell}
            onContentChange={syncContent}
          />
        </div>

        {/* Resizable AI Chat Panel */}
        {chatOpen && (
          <>
            {/* Resize handle */}
            <div
              onMouseDown={onMouseDown}
              className="w-1 cursor-col-resize bg-forge-border hover:bg-forge-accent/50 transition-colors shrink-0"
            />
            <div className="shrink-0 overflow-hidden" style={{ width: chatWidth }}>
              {statAdvisorOpen ? (
                <StatAdvisorPanel
                  workspaceId={id}
                  datasets={datasets}
                  onClose={() => setStatAdvisorOpen(false)}
                />
              ) : (
                <ChatPanel workspaceId={id} width={chatWidth} onClose={() => setChatOpen(false)} />
              )}
            </div>
          </>
        )}
      </div>

      <PipelineBuilder
        workspaceId={id}
        open={pipelineOpen}
        onOpenChange={setPipelineOpen}
      />

      <Sheet open={semanticOpen} onOpenChange={setSemanticOpen}>
        <SheetContent side="right" className="w-[720px] max-w-[95vw] overflow-auto">
          <SheetHeader>
            <SheetTitle>Semantic Layer Manager</SheetTitle>
            <SheetDescription>
              Define reusable business metrics so AI understands your KPIs.
            </SheetDescription>
          </SheetHeader>
          <div className="p-4">
            <SemanticLayerManager workspaceId={id} datasets={datasets} />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
