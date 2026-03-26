"use client";

import { useCallback, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Play,
  Trash2,
  GripVertical,
  ChevronDown,
  ChevronRight,
  Code2,
  Database,
  FileText,
  BarChart2,
  Bot,
  Loader2,
  Check,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { CellLockInfo, CellState, CellRunStatus } from "@/lib/stores/workspaceStore";
import OutputRenderer from "./OutputRenderer";
import DataGrid from "@/components/data/DataGrid";
import type { CellType, CellOutput } from "@/types";
import { useToast } from "@/components/ui/use-toast";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const MarkdownPreview = dynamic(
  () => import("react-markdown"),
  { ssr: false }
);

// ── Constants ────────────────────────────────────────────────────────────────

const CELL_TYPE_META: Record<CellType, { icon: typeof Code2; label: string; color: string }> = {
  code:     { icon: Code2,     label: "Python", color: "text-green-400" },
  sql:      { icon: Database,  label: "SQL",    color: "text-blue-400" },
  markdown: { icon: FileText,  label: "Markdown", color: "text-purple-400" },
  chart:    { icon: BarChart2, label: "Chart",  color: "text-amber-400" },
  ai_chat:  { icon: Bot,       label: "AI Chat", color: "text-forge-accent" },
};

const STATUS_INDICATOR: Record<CellRunStatus, { cls: string }> = {
  idle:    { cls: "bg-forge-muted/50" },
  running: { cls: "bg-cyan-400 animate-pulse" },
  success: { cls: "bg-green-400" },
  error:   { cls: "bg-red-400" },
};

// ── Main Cell Component ──────────────────────────────────────────────────────

interface CellProps {
  cellState: CellState;
  workspaceId: string;
  isActive: boolean;
  /** True when AI is actively streaming code into this cell */
  isAiStreaming?: boolean;
  onRun: (cellId: string) => void;
  onDelete: (cellId: string) => void;
  onContentChange: (cellId: string, content: string) => void;
  onActivate: (cellId: string) => void;
  onFocusCell?: (cellId: string) => void;
  onBlurCell?: (cellId: string) => void;
  lockInfo?: CellLockInfo;
  typingIndicator?: { user_id: string; user_name: string; color: string; char_count: number; last_seen: number };
  currentUserId?: string | null;
  dragListeners?: Record<string, unknown>;
}

export default function CellComponent({
  cellState,
  workspaceId,
  isActive,
  isAiStreaming = false,
  onRun,
  onDelete,
  onContentChange,
  onActivate,
  onFocusCell,
  onBlurCell,
  lockInfo,
  typingIndicator,
  currentUserId,
  dragListeners,
}: CellProps) {
  const { toast } = useToast();
  const { cell, runStatus, outputs, localContent } = cellState;
  const [collapsed, setCollapsed] = useState(false);
  const [outputCollapsed, setOutputCollapsed] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const canRun = ["code", "sql", "chart", "ai_chat"].includes(cell.cell_type);
  const lockedByOther = !!lockInfo && lockInfo.user_id !== currentUserId;
  const lockLabel = lockedByOther ? `Locked by ${lockInfo.user_name}` : null;
  const meta = CELL_TYPE_META[cell.cell_type] ?? CELL_TYPE_META.code;

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && e.shiftKey && canRun) {
      e.preventDefault();
      e.stopPropagation();
      onRun(cell.id);
    }
  }, [canRun, onRun, cell.id]);

  const handleRootClick = () => {
    onActivate(cell.id);
    if (lockedByOther) {
      toast({ title: `This cell is being edited by ${lockInfo.user_name}` });
    }
  };

  return (
    <div
      ref={containerRef}
      onClick={handleRootClick}
      onKeyDown={handleKeyDown}
      className={cn(
        "group flex flex-col rounded-lg border bg-forge-surface shadow-lg transition-all duration-150 min-w-[400px]",
        isActive ? "border-forge-accent shadow-forge-accent/10 ring-1 ring-forge-accent/20" : "border-forge-border",
        isAiStreaming ? "border-cyan-400 ring-2 ring-cyan-400/30 shadow-cyan-400/20" : "",
        lockedByOther ? "ring-1 ring-amber-400/40 opacity-85" : "",
        lockInfo && !lockedByOther ? "ring-1 ring-offset-0" : "",
        "hover:shadow-xl"
      )}
      style={lockInfo && !lockedByOther ? { borderColor: lockInfo.color, boxShadow: `0 0 0 1px ${lockInfo.color}55` } : undefined}
    >
      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b border-forge-border bg-forge-bg/60 px-2 py-1">
        <div className="flex items-center gap-1.5">
          {/* Drag handle */}
          <div
            className="cursor-grab rounded p-0.5 text-forge-muted hover:bg-forge-border hover:text-forge-text active:cursor-grabbing"
            {...dragListeners}
          >
            <GripVertical className="h-3.5 w-3.5" />
          </div>

          {/* Status indicator */}
          <div className={cn("h-2 w-2 rounded-full", STATUS_INDICATOR[runStatus].cls)} />

          {/* Cell type badge */}
          <div className={cn("flex items-center gap-1 text-xs", meta.color)}>
            <meta.icon className="h-3 w-3" />
            <span className="font-medium">{meta.label}</span>
          </div>
          {lockLabel ? (
            <span
              className="rounded px-1.5 py-0.5 text-[10px]"
              style={{ backgroundColor: `${lockInfo?.color ?? "#f59e0b"}22`, color: lockInfo?.color ?? "#f59e0b" }}
            >
              {lockLabel}
            </span>
          ) : null}

          {/* Language tag for code cells */}
          {cell.cell_type === "code" && (
            <span className="ml-1 rounded bg-forge-border px-1.5 py-0.5 font-mono text-[10px] text-forge-muted">
              {cell.language ?? "python"}
            </span>
          )}

          {/* Collapse toggle */}
          <button
            onClick={(e) => { e.stopPropagation(); setCollapsed(!collapsed); }}
            className="rounded p-0.5 text-forge-muted hover:text-forge-text"
          >
            {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {/* AI streaming badge */}
          {isAiStreaming && (
            <span className="flex items-center gap-1 rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[10px] text-cyan-300">
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              AI writing…
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {lockedByOther ? (
            <span className="text-[10px] font-medium" style={{ color: lockInfo.color }}>
              🔒
            </span>
          ) : null}
          {canRun && (
            <button
              onClick={(e) => { e.stopPropagation(); onRun(cell.id); }}
              disabled={runStatus === "running"}
              className={cn(
                "flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium transition-colors",
                runStatus === "running"
                  ? "text-forge-muted"
                  : "text-forge-accent hover:bg-forge-accent/10"
              )}
            >
              {runStatus === "running" ? (
                <><Loader2 className="h-3 w-3 animate-spin" /> Running</>
              ) : (
                <><Play className="h-3 w-3" /> Run</>
              )}
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(cell.id); }}
            className="rounded p-0.5 text-forge-muted hover:bg-red-900/30 hover:text-red-400"
            title="Delete cell"
            aria-label="Delete cell"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* ── Editor / Content ───────────────────────────────────────────── */}
      {!collapsed && (
        <>
          {cell.cell_type === "code" ? (
            <CodeCellEditor
              content={localContent}
              language={cell.language ?? "python"}
              onChange={(v) => onContentChange(cell.id, v)}
              onRun={() => onRun(cell.id)}
              readOnly={lockedByOther}
              onFocus={() => onFocusCell?.(cell.id)}
              onBlur={() => onBlurCell?.(cell.id)}
            />
          ) : cell.cell_type === "sql" ? (
            <SQLCellEditor
              content={localContent}
              onChange={(v) => onContentChange(cell.id, v)}
              onRun={() => onRun(cell.id)}
              readOnly={lockedByOther}
              onFocus={() => onFocusCell?.(cell.id)}
              onBlur={() => onBlurCell?.(cell.id)}
            />
          ) : cell.cell_type === "markdown" ? (
            <MarkdownCellEditor
              content={localContent}
              onChange={(v) => onContentChange(cell.id, v)}
              isActive={isActive}
              readOnly={lockedByOther}
              onFocus={() => onFocusCell?.(cell.id)}
              onBlur={() => onBlurCell?.(cell.id)}
            />
          ) : cell.cell_type === "chart" ? (
            <ChartCellEditor
              content={localContent}
              onChange={(v) => onContentChange(cell.id, v)}
              onRun={() => onRun(cell.id)}
              readOnly={lockedByOther}
              onFocus={() => onFocusCell?.(cell.id)}
              onBlur={() => onBlurCell?.(cell.id)}
            />
          ) : cell.cell_type === "ai_chat" ? (
            <AIChatCellEditor
              content={localContent}
              onChange={(v) => onContentChange(cell.id, v)}
              onRun={() => onRun(cell.id)}
              readOnly={lockedByOther}
              onFocus={() => onFocusCell?.(cell.id)}
              onBlur={() => onBlurCell?.(cell.id)}
            />
          ) : null}

          {typingIndicator && typingIndicator.user_id !== currentUserId && lockInfo ? (
            <div className="border-t border-forge-border px-3 py-1 text-[10px]" style={{ color: typingIndicator.color }}>
              {typingIndicator.user_name} typing · {typingIndicator.char_count} chars
            </div>
          ) : null}

          {/* ── Output ─────────────────────────────────────────────────── */}
          {outputs.length > 0 && (
            <CellOutputSection
              cellState={cellState}
              collapsed={outputCollapsed}
              onToggle={() => setOutputCollapsed(!outputCollapsed)}
            />
          )}
        </>
      )}
    </div>
  );
}

// ── Code Cell Editor ─────────────────────────────────────────────────────────

function CodeCellEditor({
  content,
  language,
  onChange,
  onRun,
  readOnly,
  onFocus,
  onBlur,
}: {
  content: string;
  language: string;
  onChange: (v: string) => void;
  onRun: () => void;
  readOnly?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const lineCount = Math.max(content.split("\n").length, 3);
  const height = Math.max(80, Math.min(lineCount * 19 + 16, 500));

  return (
    <div className="monaco-wrapper">
      <MonacoEditor
        height={height}
        language={language}
        theme="vs-dark"
        value={content}
        onChange={(v) => onChange(v ?? "")}
        onMount={(editor) => {
          editor.addAction({
            id: "forge-run-cell",
            label: "Run Cell",
            keybindings: [2048 + 3], // Shift+Enter
            run: () => onRun(),
          });
          editor.onDidFocusEditorWidget(() => onFocus?.());
          editor.onDidBlurEditorWidget(() => onBlur?.());
        }}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'DM Mono', monospace",
          lineNumbers: "on",
          folding: true,
          wordWrap: "off",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: "gutter",
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
          scrollbar: { vertical: "auto", horizontal: "auto" },
        }}
      />
    </div>
  );
}

// ── SQL Cell Editor ──────────────────────────────────────────────────────────

function SQLCellEditor({
  content,
  onChange,
  onRun,
  readOnly,
  onFocus,
  onBlur,
}: {
  content: string;
  onChange: (v: string) => void;
  onRun: () => void;
  readOnly?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const lineCount = Math.max(content.split("\n").length, 2);
  const height = Math.max(60, Math.min(lineCount * 19 + 16, 300));

  return (
    <div className="monaco-wrapper">
      <MonacoEditor
        height={height}
        language="sql"
        theme="vs-dark"
        value={content}
        onChange={(v) => onChange(v ?? "")}
        onMount={(editor) => {
          editor.addAction({
            id: "forge-run-cell",
            label: "Run Cell",
            keybindings: [2048 + 3],
            run: () => onRun(),
          });
          editor.onDidFocusEditorWidget(() => onFocus?.());
          editor.onDidBlurEditorWidget(() => onBlur?.());
        }}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'DM Mono', monospace",
          lineNumbers: "on",
          folding: true,
          wordWrap: "off",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: "gutter",
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
        }}
      />
    </div>
  );
}

// ── Markdown Cell Editor ─────────────────────────────────────────────────────

function MarkdownCellEditor({
  content,
  onChange,
  isActive,
  readOnly,
  onFocus,
  onBlur,
}: {
  content: string;
  onChange: (v: string) => void;
  isActive: boolean;
  readOnly?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const showEditor = isActive && editing;

  if (!showEditor) {
    return (
      <div
        className="cursor-text px-4 py-3 min-h-[60px]"
        onDoubleClick={() => { if (!readOnly) setEditing(true); }}
      >
        {content ? (
          <div className="prose prose-invert prose-sm max-w-none text-forge-text">
            <MarkdownPreview>{content}</MarkdownPreview>
          </div>
        ) : (
          <span className="text-forge-muted italic text-sm">Double-click to edit markdown...</span>
        )}
      </div>
    );
  }

  const lineCount = Math.max(content.split("\n").length, 4);
  const height = Math.max(100, Math.min(lineCount * 19 + 16, 400));

  return (
    <div>
      <div className="monaco-wrapper">
        <MonacoEditor
          height={height}
          language="markdown"
          theme="vs-dark"
          value={content}
          onChange={(v) => onChange(v ?? "")}
          onMount={(editor) => {
            editor.addAction({
              id: "forge-preview-markdown",
              label: "Preview Markdown",
              keybindings: [2048 + 3],
              run: () => setEditing(false),
            });
            editor.onDidFocusEditorWidget(() => onFocus?.());
            editor.onDidBlurEditorWidget(() => onBlur?.());
          }}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: "'DM Mono', monospace",
            lineNumbers: "off",
            wordWrap: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            padding: { top: 8, bottom: 8 },
          }}
        />
      </div>
      <div className="flex justify-end border-t border-forge-border px-2 py-1">
        <button
          onClick={() => setEditing(false)}
          className="text-xs text-forge-accent hover:text-forge-accent-dim"
        >
          Preview (Shift+Enter)
        </button>
      </div>
    </div>
  );
}

// ── Chart Cell Editor ────────────────────────────────────────────────────────

function ChartCellEditor({
  content,
  onChange,
  onRun,
  readOnly,
  onFocus,
  onBlur,
}: {
  content: string;
  onChange: (v: string) => void;
  onRun: () => void;
  readOnly?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const lineCount = Math.max(content.split("\n").length, 4);
  const height = Math.max(100, Math.min(lineCount * 19 + 16, 400));

  return (
    <div className="monaco-wrapper">
      <MonacoEditor
        height={height}
        language="json"
        theme="vs-dark"
        value={content || "{\n  \"data\": [],\n  \"layout\": {}\n}"}
        onChange={(v) => onChange(v ?? "")}
        onMount={(editor) => {
          editor.addAction({
            id: "forge-run-cell",
            label: "Run Cell",
            keybindings: [2048 + 3],
            run: () => onRun(),
          });
          editor.onDidFocusEditorWidget(() => onFocus?.());
          editor.onDidBlurEditorWidget(() => onBlur?.());
        }}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'DM Mono', monospace",
          lineNumbers: "on",
          folding: true,
          wordWrap: "off",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: "gutter",
        }}
      />
      <div className="border-t border-forge-border px-2 py-1 text-[10px] text-forge-muted">
        Enter Plotly JSON configuration
      </div>
    </div>
  );
}

// ── AI Chat Cell Editor ──────────────────────────────────────────────────────

function AIChatCellEditor({
  content,
  onChange,
  onRun,
  readOnly,
  onFocus,
  onBlur,
}: {
  content: string;
  onChange: (v: string) => void;
  onRun: () => void;
  readOnly?: boolean;
  onFocus?: () => void;
  onBlur?: () => void;
}) {
  const lineCount = Math.max(content.split("\n").length, 2);
  const height = Math.max(80, Math.min(lineCount * 19 + 16, 300));

  return (
    <div className="monaco-wrapper">
      <MonacoEditor
        height={height}
        language="markdown"
        theme="vs-dark"
        value={content}
        onChange={(v) => onChange(v ?? "")}
        onMount={(editor) => {
          editor.addAction({
            id: "forge-run-cell",
            label: "Run Cell",
            keybindings: [2048 + 3],
            run: () => onRun(),
          });
          editor.onDidFocusEditorWidget(() => onFocus?.());
          editor.onDidBlurEditorWidget(() => onBlur?.());
        }}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: "'DM Mono', monospace",
          lineNumbers: "off",
          wordWrap: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          padding: { top: 8, bottom: 8 },
          renderLineHighlight: "gutter",
        }}
      />
      <div className="border-t border-forge-border px-2 py-1 text-[10px] text-forge-muted">
        Enter prompt and run to generate response
      </div>
    </div>
  );
}

// ── Cell Output Section ──────────────────────────────────────────────────────

function CellOutputSection({
  cellState,
  collapsed,
  onToggle,
}: {
  cellState: CellState;
  collapsed: boolean;
  onToggle: () => void;
}) {
  const { cell, outputs, runStatus } = cellState;

  const isSql = cell.cell_type === "sql";
  const sqlResult = isSql ? extractSqlResult(outputs) : null;

  return (
    <>
      <button
        onClick={(e) => { e.stopPropagation(); onToggle(); }}
        className="flex items-center gap-1.5 border-t border-forge-border px-3 py-1 text-[10px] text-forge-muted hover:text-forge-text"
      >
        {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        Output
        {runStatus === "success" && <Check className="h-3 w-3 text-green-400" />}
        {runStatus === "error" && <AlertCircle className="h-3 w-3 text-red-400" />}
      </button>
      {!collapsed && (
        <>
          {sqlResult ? (
            <div className="overflow-auto border-t border-forge-border">
              <div className="flex items-center justify-between px-3 py-1 text-[10px] text-forge-muted">
                <span>{sqlResult.rowCount} rows</span>
                {sqlResult.executionTime != null && <span>{sqlResult.executionTime}ms</span>}
              </div>
              <DataGrid
                columns={sqlResult.columns}
                rows={sqlResult.rows}
                maxHeight="300px"
              />
            </div>
          ) : (
            <OutputRenderer outputs={outputs} maxHeight="400px" />
          )}
        </>
      )}
    </>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

interface SqlResult {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
  executionTime?: number;
}

function extractSqlResult(outputs: CellState["outputs"]): SqlResult | null {
  for (const o of outputs) {
    if (!o?.data || typeof o.data !== "object") continue;
    const data = o.data as Record<string, unknown>;
    if (!data) continue;
    // SQL results may be at top level or nested under "application/json"
    const candidate = (data?.columns && data?.rows)
      ? data
      : (data["application/json"] as Record<string, unknown> | undefined);
    if (candidate && Array.isArray(candidate.columns) && Array.isArray(candidate.rows)) {
      return {
        columns: candidate.columns as string[],
        rows: candidate.rows as unknown[][],
        rowCount: (candidate.row_count as number) ?? (candidate.rows as unknown[][]).length,
        executionTime: candidate.execution_time_ms as number | undefined,
      };
    }
  }
  return null;
}
