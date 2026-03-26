"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Code2,
  FileText,
  Loader2,
  RefreshCw,
  Send,
  Square,
  User as UserIcon,
  WandSparkles,
  Wrench,
  X,
  Zap,
} from "lucide-react";
import { cn, parseSseLine } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import type { AIProviderOption, CellLanguage } from "@/types";

// --- Types ---

type ChatLanguage = "auto" | "python" | "sql" | "r";
type AiIntent = "agent" | "generate" | "patch" | "chat";
type MsgSubtype =
  | "text" | "summary" | "error" | "thinking" | "cell_ref"
  | "agent_plan" | "agent_step" | "agent_complete" | "plan_revised" | "ledger" | "agent_approval";
type ChatRole = "user" | "assistant" | "system";

interface TodoItem {
  step: string;
  status: string;
  cell_id: string | null;
}
interface ChangelogEntry {
  timestamp: string;
  action: string;
  detail: string;
  cell_id: string | null;
  step_index: number | null;
}
interface LedgerSnapshot {
  todo: TodoItem[];
  changelog: ChangelogEntry[];
}

interface PanelMessage {
  id: string;
  role: ChatRole;
  subtype?: MsgSubtype;
  content: string;
  linkedCellId?: string;
  complete?: boolean;
  steps?: string[];
  stepIndex?: number;
  stepStatus?: "running" | "success" | "error" | "fixing" | "fixed" | "failed";
  oldSteps?: string[];
  newSteps?: string[];
  toolName?: string;
  toolArgs?: any;
}

interface ModelChoice {
  id: string;
  label: string;
  provider: string;
  modelCode: string;
  configured: boolean;
  local: boolean;
}

interface ChatPanelProps {
  workspaceId: string;
  width: number;
  onClose: () => void;
}

// --- Keyword classifiers ---

function detectIntent(text: string, hasActiveCodeCell: boolean): AiIntent {
  const lower = text.toLowerCase();

  // Agent mode: any high-level data science goal or multi-action request
  const agentKw = [
    "full analysis", "full exploratory", "explore", "investigate",
    "build a dashboard", "clean the data", "do a complete", "autonomous",
    "analyze everything", "end to end", "step by step",
    "dashboard", "overview", "insight", "pattern", "trend", "distribution",
    "eda", "exploratory data", "data profil", "data quality", "data clean",
    "this dataset", "this data", "the data", "the dataset",
    "find correlation", "show me", "tell me about the data",
    "what can you find", "what patterns", "what trends",
    "run an analysis", "perform analysis", "do analysis",
    "sales data", "revenue", "customer", "segment",
  ];
  const actionVerbs = [
    "analyze", "visualize", "clean", "transform", "compute", "compare",
    "correlate", "predict", "classify", "cluster", "summarize", "test",
    "explore", "profile", "inspect", "examine", "investigate", "review",
    "chart", "plot", "graph", "dashboard", "report",
  ];
  const actionCount = actionVerbs.filter((v) => lower.includes(v)).length;
  // Single action verb + data mention = agent mode
  const dataWords = ["data", "dataset", "table", "column", "row", "csv", "sales", "revenue"];
  const mentionsData = dataWords.some((d) => lower.includes(d));
  if (agentKw.some((kw) => lower.includes(kw)) || actionCount >= 2 || (actionCount >= 1 && mentionsData)) return "agent";

  const patchKw = [
    "fix", "error", "bug", "broken", "wrong", "change", "update", "rename",
    "replace", "refactor", "improve", "optimis", "optimiz", "modify", "edit",
    "correct", "remove", "add a ", "add the", "adjust",
  ];
  const generateKw = [
    "write", "generate", "create", "build", "make", "code", "script",
    "plot", "chart", "visuali", "analys", "compute", "calculate",
    "show", "display", "draw", "train", "predict", "model", "query",
    "select", "group by", "join", "filter", "sort", "aggregate",
  ];

  if (hasActiveCodeCell && patchKw.some((kw) => lower.includes(kw))) return "patch";
  if (generateKw.some((kw) => lower.includes(kw))) return "generate";
  return "chat";
}

const QUICK_ACTIONS = [
  "Full analysis of this dataset",
  "Visualize key trends",
  "Find correlations",
  "Suggest statistical tests",
];

const STORAGE_KEY = "forge.ai.chat.model";

// --- Main component ---

export default function ChatPanel({ workspaceId, width, onClose }: ChatPanelProps) {
  const { user } = useAuth();
  const {
    createCell, setActiveCellId, applyRemoteCellContent,
    cellStates, activeCellId, setStreamingCellId, fetchCells,
  } = useWorkspaceStore();

  const [messages, setMessages] = useState<PanelMessage[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<ChatLanguage>("auto");
  const [modelId, setModelId] = useState<string>("");
  const [providers, setProviders] = useState<AIProviderOption[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingMsgId, setStreamingMsgId] = useState<string | null>(null);
  const [agentAbort, setAgentAbort] = useState<AbortController | null>(null);
  const [ledger, setLedger] = useState<LedgerSnapshot | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const [approvalPending, setApprovalPending] = useState<{ tool: string; args: any } | null>(null);
  const [isThinking, setIsThinking] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const activeCodeCell = useMemo(() => {
    if (!activeCellId) return null;
    const cs = cellStates[activeCellId];
    if (!cs) return null;
    return ["code", "sql"].includes(cs.cell.cell_type) ? cs : null;
  }, [activeCellId, cellStates]);

// --- Model choices ---

  const modelChoices = useMemo<ModelChoice[]>(() => {
    return [...providers]
      .sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999))
      .flatMap((p) => {
        if (!p.configured && !p.local) return [];
        return p.models.map((m) => ({
          id: `${p.id}:${m}`,
          label: `${m} (${p.name})`,
          provider: p.id,
          modelCode: m,
          configured: p.configured,
          local: Boolean(p.local),
        }));
      });
  }, [providers]);

  const currentModel = useMemo(
    () => modelChoices.find((m) => m.id === modelId) ?? modelChoices[0] ?? null,
    [modelChoices, modelId],
  );

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && modelChoices.some((m) => m.id === saved)) setModelId(saved);
    else if (modelChoices.length) setModelId(modelChoices[0].id);
  }, [modelChoices]);

  useEffect(() => {
    const load = async () => {
      try {
        const resp = await fetch("/api/v1/ai/providers", { credentials: "include" });
        if (!resp.ok) return;
        const data = (await resp.json()) as AIProviderOption[];
        const enriched = await Promise.all(
          data.map(async (p) => {
            if (!p.local) return p;
            try {
              const r = await fetch(`/api/v1/ai/providers/${p.id}/models`, { credentials: "include" });
              if (!r.ok) return p;
              const result = (await r.json()) as { models: string[] };
              if (result.models?.length) return { ...p, models: result.models, configured: true };
            } catch { /* offline */ }
            return p;
          }),
        );
        setProviders(enriched);
      } catch { /* ignore */ }
    };
    void load();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const getCellLanguage = (): CellLanguage => {
    if (language === "sql") return "sql";
    if (language === "r") return "r";
    return "python";
  };

// --- Helpers ---

  const pushMsg = (msg: PanelMessage) => setMessages((prev) => [...prev, msg]);
  const updateMsg = (id: string, patch: Partial<PanelMessage>) =>
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));

  async function consumeSse(
    resp: Response,
    onToken: (text: string) => void,
    onComplete: (payload: Record<string, unknown>) => void,
    onError: (msg: string) => void,
    onEvent?: (payload: Record<string, unknown>) => void,
  ) {
    const reader = resp.body!.pipeThrough(new TextDecoderStream()).getReader();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += value;
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        const payload = parseSseLine<Record<string, unknown>>(line);
        if (!payload) continue;
        const type = payload.type as string | undefined;
        if (type === "token" && typeof payload.text === "string") onToken(payload.text);
        if (type === "error") onError((payload.message ?? payload.text ?? "Unknown error") as string);
        if (type === "complete") { onComplete(payload); break; }
        if (onEvent && type && type !== "token" && type !== "error" && type !== "complete") {
          onEvent(payload);
        }
      }
    }
  }

// --- sendAgent ---

  const sendAgent = async (text: string, assistantId: string) => {
    const abort = new AbortController();
    setAgentAbort(abort);
    setLedger(null);
    setLedgerOpen(true);

    const planMsgId = crypto.randomUUID();
    pushMsg({
      id: planMsgId,
      role: "assistant",
      subtype: "agent_plan",
      content: "Planning analysis steps...",
      steps: [],
    });

    const stepMsgIds: Record<number, string> = {};

    try {
      const resp = await fetch(`/api/v1/ai/workspaces/${workspaceId}/agent`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        signal: abort.signal,
        body: JSON.stringify({
          goal: text,
          provider: currentModel?.provider,
          model: currentModel?.modelCode,
        }),
      });

      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      await consumeSse(
        resp,
        () => {},
        (complete) => {
          const report = (complete.full_report as string) ?? "Agent complete.";
          if (complete.ledger) setLedger(complete.ledger as LedgerSnapshot);
          updateMsg(assistantId, {
            subtype: "agent_complete",
            content: report,
            complete: true,
          });
        },
        (errMsg) => {
          updateMsg(assistantId, { subtype: "error", content: errMsg, complete: true });
        },
        (event) => {
          const type = event.type as string;
          const stepIndex = (event.step_index ?? event.stepIndex ?? -1) as number;
          const cellId = event.cell_id as string | undefined;
          const stepName = (event.step_name ?? "") as string;

          // Update ledger on every event
          if (event.ledger) setLedger(event.ledger as LedgerSnapshot);

          switch (type) {
            case "plan": {
              const steps = (event.steps ?? []) as string[];
              updateMsg(planMsgId, {
                subtype: "agent_plan",
                content: `Planning ${steps.length} steps...`,
                steps,
              });
              break;
            }
            case "plan_revised": {
              const oldSteps = (event.old_remaining ?? []) as string[];
              const newSteps = (event.new_remaining ?? []) as string[];
              const fullSteps = (event.full_steps ?? []) as string[];
              // Update the plan card
              updateMsg(planMsgId, { steps: fullSteps });
              // Add a revision indicator
              const revId = crypto.randomUUID();
              pushMsg({
                id: revId,
                role: "assistant",
                subtype: "plan_revised",
                content: "Plan revised based on results",
                oldSteps,
                newSteps,
              });
              break;
            }
            case "thinking": {
              setIsThinking(true);
              const id = crypto.randomUUID();
              pushMsg({
                id,
                role: "assistant",
                subtype: "thinking",
                content: (event.text ?? "") as string,
              });
              break;
            }
            case "code_streaming": {
              if (cellId) {
                const chunk = (event.chunk ?? "") as string;
                // Get current content and append
                const current = cellStates[cellId]?.localContent ?? "";
                applyRemoteCellContent(cellId, current + chunk);
              }
              break;
            }
            case "cell_ready": {
              setIsThinking(false);
              const mid = stepMsgIds[stepIndex];
              if (mid) updateMsg(mid, { stepStatus: "running", linkedCellId: cellId });
              setStreamingCellId(null);
              break;
            }
            case "approval_required": {
              const tool = (event.tool ?? "") as string;
              const args = (event.args ?? {}) as any;
              setApprovalPending({ tool, args });
              const id = crypto.randomUUID();
              pushMsg({
                id,
                role: "assistant",
                subtype: "agent_approval",
                content: `Approval required for dynamic action: ${tool}`,
                toolName: tool,
                toolArgs: args,
              });
              break;
            }
            case "cell_created": {
              setIsThinking(false);
              if (!stepMsgIds[stepIndex]) {
                const id = crypto.randomUUID();
                stepMsgIds[stepIndex] = id;
                pushMsg({
                  id,
                  role: "assistant",
                  subtype: "agent_step",
                  content: stepName,
                  stepIndex,
                  stepStatus: "running",
                  linkedCellId: cellId,
                });
              }
              if (cellId) {
                updateMsg(stepMsgIds[stepIndex], {
                  linkedCellId: cellId,
                  stepStatus: "running",
                });
                void fetchCells(workspaceId);
                setTimeout(() => {
                  const el = document.getElementById(`cell-${cellId}`);
                  if (el) {
                    el.scrollIntoView({ behavior: "smooth", block: "center" });
                    el.classList.add("ring-2", "ring-cyan-500", "ring-offset-2");
                    setTimeout(() => el.classList.remove("ring-2", "ring-cyan-500", "ring-offset-2"), 2000);
                  }
                  setActiveCellId(cellId);
                }, 300);
              }
              break;
            }
            case "cell_executing": {
              if (cellId) setStreamingCellId(cellId);
              break;
            }
            case "cell_executed": {
              const mid = stepMsgIds[stepIndex];
              const status = event.status as string;
              if (mid) updateMsg(mid, { stepStatus: status === "error" ? "error" : "success", linkedCellId: cellId });
              setStreamingCellId(null);
              void fetchCells(workspaceId);
              break;
            }
            case "cell_fixing": {
              const mid = stepMsgIds[stepIndex];
              if (mid) updateMsg(mid, { stepStatus: "fixing" });
              if (cellId) setStreamingCellId(cellId);
              break;
            }
            case "cell_fixed": {
              const mid = stepMsgIds[stepIndex];
              if (mid) updateMsg(mid, { stepStatus: "fixed" });
              void fetchCells(workspaceId);
              break;
            }
            case "step_complete": {
              const mid = stepMsgIds[stepIndex];
              if (mid) updateMsg(mid, { stepStatus: "success" });
              setStreamingCellId(null);
              break;
            }
            case "step_failed": {
              const mid = stepMsgIds[stepIndex];
              if (mid) updateMsg(mid, { stepStatus: "failed" });
              setStreamingCellId(null);
              break;
            }
          }
        },
      );
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        updateMsg(assistantId, { subtype: "text", content: "Agent stopped by user.", complete: true });
      } else {
        updateMsg(assistantId, { subtype: "error", content: err instanceof Error ? err.message : "Agent failed.", complete: true });
      }
    } finally {
      setAgentAbort(null);
      setStreamingCellId(null);
    }
  };

// --- sendGenerate ---

  const sendGenerate = async (text: string, assistantId: string) => {
    const lang = getCellLanguage();
    let targetCellId = activeCodeCell?.cell.id ?? null;
    if (!targetCellId) {
      const newCell = await createCell(workspaceId, {
        cell_type: lang === "sql" ? "sql" : "code",
        language: lang, content: "",
        position_x: 60, position_y: 9_999_999, width: 600, height: 320,
      });
      targetCellId = newCell.id;
      setActiveCellId(targetCellId);
    }
    setStreamingCellId(targetCellId);
    let accumulated = "";
    try {
      const resp = await fetch(`/api/v1/ai/workspaces/${workspaceId}/generate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ prompt: text, language: lang, provider: currentModel?.provider, model: currentModel?.modelCode, max_tokens: 1024 }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      await consumeSse(resp,
        (chunk) => { accumulated += chunk; applyRemoteCellContent(targetCellId!, accumulated); updateMsg(assistantId, { subtype: "thinking", content: "" }); },
        (complete) => {
          const finalCode = (complete.full_code as string | undefined) ?? accumulated;
          applyRemoteCellContent(targetCellId!, finalCode);
          updateMsg(assistantId, { subtype: "cell_ref", content: (complete.summary as string) || `Code written to ${lang} cell.`, linkedCellId: targetCellId!, complete: true });
        },
        (errMsg) => { updateMsg(assistantId, { subtype: "error", content: errMsg, complete: true }); },
      );
    } catch (err) {
      updateMsg(assistantId, { subtype: "error", content: err instanceof Error ? err.message : "Generate failed.", complete: true });
    } finally { setStreamingCellId(null); }
  };

// --- sendPatch ---

  const sendPatch = async (text: string, assistantId: string) => {
    const cellId = activeCodeCell!.cell.id;
    const currentCode = activeCodeCell!.localContent;
    const lang = activeCodeCell!.cell.language ?? "python";
    setStreamingCellId(cellId);
    let accumulated = "";
    try {
      const resp = await fetch(`/api/v1/ai/workspaces/${workspaceId}/patch`, {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ cell_id: cellId, instruction: text, language: lang, error_output: null }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
      await consumeSse(resp,
        (chunk) => { accumulated += chunk; applyRemoteCellContent(cellId, accumulated); updateMsg(assistantId, { subtype: "thinking", content: "" }); },
        (complete) => {
          const finalCode = (complete.full_code as string | undefined) ?? accumulated;
          applyRemoteCellContent(cellId, finalCode);
          updateMsg(assistantId, { subtype: "cell_ref", content: (complete.summary as string) || `Patched ${lang} cell.`, linkedCellId: cellId, complete: true });
        },
        (errMsg) => { applyRemoteCellContent(cellId, currentCode); updateMsg(assistantId, { subtype: "error", content: errMsg, complete: true }); },
      );
    } catch (err) {
      applyRemoteCellContent(cellId, currentCode);
      updateMsg(assistantId, { subtype: "error", content: err instanceof Error ? err.message : "Patch failed.", complete: true });
    } finally { setStreamingCellId(null); }
  };

// --- sendChat ---

  const sendChat = async (text: string, assistantId: string) => {
    const history = messages.filter((m) => m.role !== "system" && m.subtype !== "thinking").map((m) => ({ role: m.role, content: m.content }));
    try {
      const resp = await fetch("/api/v1/ai/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ workspace_id: workspaceId, message: language === "auto" ? text : `[Prefer ${language.toUpperCase()}]\n${text}`, history, provider: currentModel?.provider, model: currentModel?.modelCode, max_tokens: 1200 }),
      });
      if (!resp.ok || !resp.body) throw new Error("Chat failed");
      let full = "";
      await consumeSse(resp,
        (chunk) => { full += chunk; updateMsg(assistantId, { subtype: "text", content: full }); },
        () => { updateMsg(assistantId, { complete: true }); },
        (errMsg) => { updateMsg(assistantId, { subtype: "error", content: errMsg, complete: true }); },
      );
    } catch (err) {
      updateMsg(assistantId, { subtype: "error", content: err instanceof Error ? err.message : "Chat failed.", complete: true });
    }
  };

// --- send dispatcher ---

  const handleApproval = async (approved: boolean) => {
    if (!approvalPending) return;
    setApprovalPending(null);
    try {
      await fetch(`/api/v1/ai/workspaces/${workspaceId}/agent/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ approved }),
      });
    } catch (err) {
      console.error("Failed to send approval:", err);
    }
  };

  const send = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    setInput("");
    resizeTextarea();

    const userMsg: PanelMessage = { id: crypto.randomUUID(), role: "user", content: text };
    const assistantId = crypto.randomUUID();
    const thinkingMsg: PanelMessage = { id: assistantId, role: "assistant", subtype: "thinking", content: "" };

    pushMsg(userMsg);
    pushMsg(thinkingMsg);
    setStreaming(true);
    setStreamingMsgId(assistantId);

    const intent = detectIntent(text, !!activeCodeCell);

    try {
      if (intent === "agent") await sendAgent(text, assistantId);
      else if (intent === "generate") await sendGenerate(text, assistantId);
      else if (intent === "patch") await sendPatch(text, assistantId);
      else await sendChat(text, assistantId);
    } finally {
      setStreaming(false);
      setStreamingMsgId(null);
    }
  };

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "enter") { e.preventDefault(); void send(); }
  };

  const stopAgent = () => agentAbort?.abort();

// --- Render ---

  return (
    <TooltipProvider>
      <div className="flex h-full flex-col border-l border-forge-border bg-forge-surface" style={{ width }}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-forge-border px-3 py-2">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-forge-accent" />
            <span className="text-sm font-semibold text-foreground">AI Assistant</span>
            {agentAbort && (
              <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                <Zap className="h-2.5 w-2.5" /> Agent Mode
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {agentAbort && (
              <Button variant="destructive" size="sm" onClick={stopAgent} className="h-6 gap-1 px-2 text-[10px]">
                <Square className="h-2.5 w-2.5" /> Stop
              </Button>
            )}
            {ledger && (
              <button
                onClick={() => setLedgerOpen((o) => !o)}
                className={cn(
                  "flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] transition-colors",
                  ledgerOpen ? "border-cyan-700 bg-cyan-950/40 text-cyan-300" : "border-forge-border bg-forge-bg text-forge-muted hover:text-foreground",
                )}
              >
                <FileText className="h-3 w-3" /> Ledger
              </button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="rounded-md border border-forge-border bg-forge-bg px-2 py-1 text-xs text-foreground hover:bg-forge-border">
                  {currentModel?.label ?? "Select model"}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {modelChoices.map((model) => {
                  const enabled = model.configured;
                  const row = (
                    <DropdownMenuItem key={model.id} disabled={!enabled}
                      onClick={() => { if (enabled) { setModelId(model.id); localStorage.setItem(STORAGE_KEY, model.id); } }}
                      className="flex items-center justify-between gap-3">
                      <span>{model.label}</span>
                      {model.id === modelId && <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />}
                    </DropdownMenuItem>
                  );
                  if (enabled) return row;
                  return (<Tooltip key={model.id}><TooltipTrigger asChild><div>{row}</div></TooltipTrigger><TooltipContent>Configure provider in Settings</TooltipContent></Tooltip>);
                })}
              </DropdownMenuContent>
            </DropdownMenu>
            <button onClick={onClose} className="rounded-md p-1 text-forge-muted hover:bg-forge-border hover:text-foreground" aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Context banner */}
        {activeCodeCell && (
          <div className="flex items-center gap-1.5 border-b border-forge-border bg-cyan-950/30 px-3 py-1.5 text-[11px] text-cyan-300">
            <Wrench className="h-3 w-3 shrink-0" />
            <span className="truncate">
              Editing <span className="font-mono font-semibold">{activeCodeCell.cell.language ?? "python"}</span> cell - describe a change to patch
            </span>
          </div>
        )}

        {/* Ledger panel (collapsible) */}
        {ledger && ledgerOpen && <LedgerPanel ledger={ledger} onScrollToCell={(id) => {
          document.getElementById(`cell-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          setActiveCellId(id);
        }} />}

        {/* Messages */}
        <ScrollArea className="flex-1 px-3 py-3">
          <div className="space-y-3">
            {messages.length === 0 && (
              <div className="mt-8 space-y-2 text-center">
                <Bot className="mx-auto h-8 w-8 text-forge-muted/50" />
                <p className="text-xs text-forge-muted">
                  Describe a high-level goal for <strong>autonomous</strong> analysis, or ask a specific question.
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id}>
                {msg.role === "system" && <div className="text-center text-xs text-forge-muted">{msg.content}</div>}

                {msg.role === "user" && (
                  <div className="flex justify-end gap-2">
                    <div className="max-w-[85%] rounded-xl bg-forge-bg px-3 py-2 text-sm text-foreground">{msg.content}</div>
                    <div className="mt-0.5 rounded-full bg-forge-border p-1.5"><UserIcon className="h-3.5 w-3.5" /></div>
                  </div>
                )}

                {msg.role === "assistant" && (
                        <div className="flex gap-2">
                          <div className="mt-0.5 rounded-full bg-forge-accent/20 p-1.5 text-forge-accent">
                            <Bot className="h-3.5 w-3.5" />
                          </div>
                          <div className="max-w-[90%] space-y-1">
                            {msg.subtype === "thinking" && <ThinkingBubble text={msg.content} />}
                            {msg.subtype === "agent_approval" && (
                              <AgentApprovalCard
                                tool={msg.toolName ?? ""}
                                args={msg.toolArgs}
                                onApprove={() => handleApproval(true)}
                                onDeny={() => handleApproval(false)}
                                disabled={!approvalPending}
                              />
                            )}
                            {msg.subtype === "agent_plan" && <AgentPlanCard steps={msg.steps ?? []} />}
                      {msg.subtype === "plan_revised" && <PlanRevisedCard oldSteps={msg.oldSteps ?? []} newSteps={msg.newSteps ?? []} />}
                      {msg.subtype === "agent_step" && (
                        <AgentStepCard stepIndex={msg.stepIndex ?? 0} stepName={msg.content} status={msg.stepStatus ?? "running"} cellId={msg.linkedCellId ?? null}
                          onScrollTo={(id) => { document.getElementById(`cell-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); setActiveCellId(id); }} />
                      )}
                      {msg.subtype === "agent_complete" && (
                        <div className="rounded-xl border border-green-800/50 bg-green-950/30 px-3 py-2 text-sm text-green-200">
                          <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-green-400"><CheckCircle2 className="h-3.5 w-3.5" /> Agent Complete</div>
                          <div className="whitespace-pre-wrap text-xs leading-relaxed opacity-90">{msg.content}</div>
                        </div>
                      )}
                      {msg.subtype === "cell_ref" && (
                        <div className="rounded-xl border border-forge-border bg-forge-bg px-3 py-2 text-sm">
                          <CellRefMessage summary={msg.content} cellId={msg.linkedCellId ?? null}
                            onScrollTo={(id) => { document.getElementById(`cell-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); setActiveCellId(id); }} />
                        </div>
                      )}
                      {msg.subtype === "error" && <div className="rounded-xl border border-red-800 bg-red-950/40 px-3 py-2 text-sm text-red-200">{msg.content}</div>}
                      {msg.subtype === "text" && (
                        <div className="rounded-xl border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground">
                          <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap">
                            {msg.content}
                            {streamingMsgId === msg.id && <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-forge-accent align-middle" />}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="border-t border-forge-border p-3">
          <Textarea ref={textareaRef} value={input}
            onChange={(e) => { setInput(e.target.value); resizeTextarea(); }}
            onKeyDown={onInputKeyDown}
            placeholder={activeCodeCell ? "Describe a change to patch the active cell..." : "Describe a goal for autonomous analysis, or ask a question..."}
            className="max-h-[200px] min-h-[72px] resize-none bg-forge-bg" />

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1">
              {(["auto", "python", "sql", "r"] as const).map((lang) => (
                <button key={lang} onClick={() => setLanguage(lang)}
                  className={cn("rounded-md px-2 py-1 text-xs", language === lang ? "bg-forge-accent text-forge-bg" : "bg-forge-bg text-forge-muted hover:bg-forge-border hover:text-foreground")}>
                  {lang === "auto" ? "Auto" : lang.toUpperCase()}
                </button>
              ))}
            </div>
            <Button size="sm" onClick={() => void send()} disabled={streaming || !input.trim()} className="bg-forge-accent text-forge-bg hover:bg-forge-accent-dim">
              {streaming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            </Button>
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {QUICK_ACTIONS.map((action) => (
              <button key={action} onClick={() => void send(action)}
                className="rounded-full border border-forge-border bg-forge-bg px-2.5 py-1 text-[11px] text-forge-muted hover:border-forge-accent/60 hover:text-forge-accent">
                {action}
              </button>
            ))}
          </div>
          <p className="mt-1 text-[10px] text-forge-muted">Ctrl+Enter to send</p>
        </div>
      </div>
    </TooltipProvider>
  );
}

// --- Sub-components ---

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-forge-accent/60 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-forge-accent/60 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-forge-accent/60" />
    </div>
  );
}

function ThinkingBubble({ text }: { text: string }) {
  return (
    <div className="rounded-xl border border-purple-800/40 bg-purple-950/20 px-3 py-2 text-[11px] italic text-purple-200/80">
      <div className="mb-1 flex items-center gap-1.5 font-semibold text-purple-300">
        <Clock className="h-3 w-3" /> Thinking...
      </div>
      {text}
    </div>
  );
}

function AgentApprovalCard({ tool, args, onApprove, onDeny, disabled }: {
  tool: string;
  args: any;
  onApprove: () => void;
  onDeny: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-xl border border-red-800/50 bg-red-950/20 px-3 py-2">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-red-400">
        <Zap className="h-3 w-3" /> Approval Required
      </div>
      <p className="mb-3 text-[11px] text-red-100/90">
        The agent wants to perform a <span className="font-bold text-red-400">dangerous</span> action:
        <code className="mx-1 rounded bg-red-900/40 px-1 py-0.5 font-mono text-red-200">{tool}</code>
        {args?.step && <span>to {args.step}</span>}
      </p>
      <div className="flex gap-2">
        <Button size="sm" onClick={onApprove} disabled={disabled} className="h-7 bg-green-600 px-3 text-[10px] hover:bg-green-500">
          Approve
        </Button>
        <Button size="sm" variant="outline" onClick={onDeny} disabled={disabled} className="h-7 border-red-800/50 px-3 text-[10px] hover:bg-red-950/40">
          Deny
        </Button>
      </div>
    </div>
  );
}

function AgentPlanCard({ steps }: { steps: string[] }) {
  return (
    <div className="rounded-xl border border-amber-800/40 bg-amber-950/20 px-3 py-2">
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-amber-300"><Zap className="h-3 w-3" /> Agent Plan</div>
      {steps.length === 0 ? (
        <div className="flex items-center gap-1.5 text-xs text-amber-200/70"><Loader2 className="h-3 w-3 animate-spin" /> Planning steps...</div>
      ) : (
        <ol className="space-y-0.5 text-xs text-amber-100/80">
          {steps.map((step, i) => (<li key={i} className="flex gap-1.5"><span className="shrink-0 font-mono text-amber-400">{i + 1}.</span><span>{step}</span></li>))}
        </ol>
      )}
    </div>
  );
}

function PlanRevisedCard({ oldSteps, newSteps }: { oldSteps: string[]; newSteps: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-purple-800/40 bg-purple-950/20 px-3 py-2">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-1.5 text-xs font-semibold text-purple-300">
        <RefreshCw className="h-3 w-3" />
        Plan Revised
        {open ? <ChevronDown className="ml-auto h-3 w-3" /> : <ChevronRight className="ml-auto h-3 w-3" />}
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-xs">
          {oldSteps.length > 0 && (
            <div>
              <span className="text-[10px] font-medium uppercase text-red-400/70">Old (removed)</span>
              <ul className="mt-0.5 space-y-0.5 text-red-200/60 line-through">
                {oldSteps.map((s, i) => <li key={i}>* {s}</li>)}
              </ul>
            </div>
          )}
          <div>
            <span className="text-[10px] font-medium uppercase text-green-400/70">New steps</span>
            <ul className="mt-0.5 space-y-0.5 text-green-200/80">
              {newSteps.map((s, i) => <li key={i}>* {s}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

const STEP_STATUS_MAP: Record<string, { icon: typeof Loader2; color: string; label: string }> = {
  running: { icon: Loader2, color: "text-cyan-400", label: "Running..." },
  success: { icon: CheckCircle2, color: "text-green-400", label: "Done" },
  error: { icon: X, color: "text-red-400", label: "Error" },
  fixing: { icon: Wrench, color: "text-amber-400", label: "Fixing..." },
  fixed: { icon: WandSparkles, color: "text-amber-300", label: "Fixed -> re-run" },
  failed: { icon: X, color: "text-red-500", label: "Failed" },
};

function AgentStepCard({ stepIndex, stepName, status, cellId, onScrollTo }: {
  stepIndex: number; stepName: string; status: string; cellId: string | null; onScrollTo: (id: string) => void;
}) {
  const s = STEP_STATUS_MAP[status] ?? STEP_STATUS_MAP.running;
  const Icon = s.icon;
  const isAnimated = status === "running" || status === "fixing";
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono text-forge-muted">#{stepIndex + 1}</span>
          <span className="font-medium text-foreground">{stepName}</span>
        </div>
        <div className={cn("flex items-center gap-1 text-[10px]", s.color)}>
          <Icon className={cn("h-3 w-3", isAnimated && "animate-spin")} /> {s.label}
        </div>
      </div>
      {cellId && status !== "running" && (
        <button onClick={() => onScrollTo(cellId)}
          className="mt-1.5 flex items-center gap-1 rounded-md border border-forge-border bg-forge-surface px-2 py-1 text-[10px] text-forge-muted transition-colors hover:border-cyan-700/50 hover:text-cyan-300">
          <Code2 className="h-3 w-3 shrink-0" /> Jump to cell
        </button>
      )}
    </div>
  );
}

function CellRefMessage({ summary, cellId, onScrollTo }: { summary: string; cellId: string | null; onScrollTo: (id: string) => void }) {
  return (
    <div className="space-y-2">
      {summary && <p className="text-sm leading-relaxed">{summary}</p>}
      {cellId && (
        <button onClick={() => onScrollTo(cellId)}
          className="flex items-center gap-1.5 rounded-md border border-cyan-700/50 bg-cyan-950/40 px-2.5 py-1.5 text-xs text-cyan-300 transition-colors hover:border-cyan-500/70 hover:bg-cyan-900/40">
          <Code2 className="h-3.5 w-3.5 shrink-0" /> Jump to cell <WandSparkles className="h-3 w-3 shrink-0 opacity-60" />
        </button>
      )}
    </div>
  );
}

// --- Ledger Panel ---

const TODO_STATUS_ICON: Record<string, { icon: typeof CheckCircle2; color: string }> = {
  pending: { icon: Clock, color: "text-forge-muted" },
  running: { icon: Loader2, color: "text-cyan-400" },
  success: { icon: CheckCircle2, color: "text-green-400" },
  error: { icon: X, color: "text-red-400" },
  skipped: { icon: X, color: "text-forge-muted/50" },
  revised: { icon: RefreshCw, color: "text-purple-400" },
};

const LOG_ACTION_COLOR: Record<string, string> = {
  plan: "text-amber-400",
  code: "text-cyan-400",
  execute: "text-blue-400",
  fix: "text-amber-300",
  error: "text-red-400",
  replan: "text-purple-400",
  complete: "text-green-400",
};

function LedgerPanel({ ledger, onScrollToCell }: { ledger: LedgerSnapshot; onScrollToCell: (id: string) => void }) {
  const [tab, setTab] = useState<"todo" | "log">("todo");
  return (
    <div className="border-b border-forge-border bg-forge-bg/60">
      {/* Tabs */}
      <div className="flex border-b border-forge-border">
        <button onClick={() => setTab("todo")}
          className={cn("flex-1 px-3 py-1.5 text-[11px] font-medium transition-colors", tab === "todo" ? "border-b-2 border-cyan-500 text-cyan-300" : "text-forge-muted hover:text-foreground")}>
          To-Do ({ledger.todo.filter((t) => t.status === "success").length}/{ledger.todo.filter((t) => t.status !== "revised").length})
        </button>
        <button onClick={() => setTab("log")}
          className={cn("flex-1 px-3 py-1.5 text-[11px] font-medium transition-colors", tab === "log" ? "border-b-2 border-cyan-500 text-cyan-300" : "text-forge-muted hover:text-foreground")}>
          Changelog ({ledger.changelog.length})
        </button>
      </div>

      <ScrollArea className="max-h-[200px]">
        {tab === "todo" && (
          <div className="space-y-0.5 p-2">
            {ledger.todo.map((item, i) => {
              const s = TODO_STATUS_ICON[item.status] ?? TODO_STATUS_ICON.pending;
              const Icon = s.icon;
              const isAnimated = item.status === "running";
              return (
                <div key={i} className={cn("flex items-center gap-2 rounded-md px-2 py-1 text-xs", item.status === "revised" && "opacity-40 line-through")}>
                  <Icon className={cn("h-3 w-3 shrink-0", s.color, isAnimated && "animate-spin")} />
                  <span className={cn("flex-1", item.status === "success" ? "text-foreground" : "text-forge-muted")}>{item.step}</span>
                  {item.cell_id && (
                    <button onClick={() => onScrollToCell(item.cell_id!)}
                      className="text-[9px] text-cyan-400 hover:underline">
                      cell
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {tab === "log" && (
          <div className="space-y-0.5 p-2">
            {ledger.changelog.map((entry, i) => (
              <div key={i} className="flex items-start gap-2 rounded-md px-2 py-0.5 text-[11px]">
                <span className="shrink-0 font-mono text-forge-muted/60">{entry.timestamp}</span>
                <span className={cn("shrink-0 font-medium uppercase", LOG_ACTION_COLOR[entry.action] ?? "text-forge-muted")}>
                  {entry.action}
                </span>
                <span className="flex-1 text-forge-muted">{entry.detail}</span>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
