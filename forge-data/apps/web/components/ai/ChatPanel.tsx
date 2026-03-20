"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  Bot,
  CheckCircle2,
  Loader2,
  Send,
  User as UserIcon,
  X,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { cn, parseSseLine } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { getAccessToken } from "@/lib/auth";
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
import type { AIProviderOption, CellLanguage, CellType } from "@/types";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });
const ReactMarkdown = dynamic(() => import("react-markdown"), { ssr: false });

type ChatLanguage = "auto" | "python" | "sql" | "r";

interface ChatPanelProps {
  workspaceId: string;
  width: number;
  onClose: () => void;
}

type AssistantSubtype = "text" | "code_block" | "error" | "thinking";
type ChatRole = "user" | "assistant" | "system";

interface PanelMessage {
  id: string;
  role: ChatRole;
  subtype?: AssistantSubtype;
  content: string;
  language?: CellLanguage;
  complete?: boolean;
}

interface ModelChoice {
  id: string;
  label: string;
  provider: string;
  configured: boolean;
  local: boolean;
}

const QUICK_ACTIONS = [
  "📊 Visualize this dataset",
  "🔍 Find correlations",
  "🧪 Suggest statistical tests",
  "📈 What are the trends?",
];

const STORAGE_KEY = "forge.ai.chat.model";

export default function ChatPanel({ workspaceId, width, onClose }: ChatPanelProps) {
  const { user } = useAuth();
  const { createCell, setActiveCellId } = useWorkspaceStore();
  const [messages, setMessages] = useState<PanelMessage[]>([]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<ChatLanguage>("auto");
  const [modelId, setModelId] = useState<string>("");
  const [providers, setProviders] = useState<AIProviderOption[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [justInsertedCellId, setJustInsertedCellId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const modelChoices = useMemo<ModelChoice[]>(() => {
    const sortedProviders = [...providers].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));
    const choices: ModelChoice[] = [];
    for (const provider of sortedProviders) {
      for (const model of provider.models) {
        choices.push({
          id: `${provider.id}:${model}`,
          label: `${model} (${provider.name})`,
          provider: provider.id,
          configured: provider.configured,
          local: Boolean(provider.local),
        });
      }
    }
    return choices;
  }, [providers]);

  const currentModel = useMemo(
    () => modelChoices.find((m) => m.id === modelId) ?? modelChoices[0] ?? null,
    [modelChoices, modelId],
  );

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && modelChoices.some((m) => m.id === saved)) {
      setModelId(saved);
      return;
    }
    if (!modelId && modelChoices.length > 0) {
      const localConfigured = modelChoices.find((m) => m.local && m.configured);
      setModelId(localConfigured?.id ?? modelChoices[0].id);
    }
  }, [modelChoices, modelId]);

  useEffect(() => {
    if (modelId) {
      localStorage.setItem(STORAGE_KEY, modelId);
    }
  }, [modelId]);

  useEffect(() => {
    const loadProviders = async () => {
      try {
        const resp = await fetch("/api/v1/ai/providers", {
          headers: {
            ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
          },
        });
        if (!resp.ok) return;
        const data = (await resp.json()) as AIProviderOption[];
        setProviders(data);
      } catch {
        // Keep existing UX if providers API fails.
      }
    };
    void loadProviders();
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

  const detectLanguage = (content: string): CellLanguage => {
    if (content.includes("```sql")) return "sql";
    if (content.includes("```r")) return "r";
    if (content.includes("```python")) return "python";
    if (language === "sql") return "sql";
    if (language === "r") return "r";
    return "python";
  };

  const extractCodeFence = (content: string): string | null => {
    const match = content.match(/```[a-zA-Z]*\n([\s\S]*?)```/);
    return match?.[1]?.trim() ?? null;
  };

  const getCellLanguageFromChatLanguage = (lang: ChatLanguage): CellLanguage => {
    if (lang === "sql") return "sql";
    if (lang === "r") return "r";
    return "python";
  };

  const insertAsCell = async (message: PanelMessage) => {
    const code = extractCodeFence(message.content) ?? message.content.trim();
    const inferredLanguage = message.language ?? detectLanguage(message.content);
    const created = await createCell(workspaceId, {
      cell_type: inferredLanguage === "sql" ? "sql" : "code",
      language: inferredLanguage,
      content: code,
      position_x: 60,
      position_y: 9_999_999,
      width: 600,
      height: 320,
    });
    setActiveCellId(created.id);
    setJustInsertedCellId(created.id);
    setTimeout(() => setJustInsertedCellId(null), 1800);
  };

  const send = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    setInput("");
    resizeTextarea();

    const userMsg: PanelMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const assistantId = crypto.randomUUID();
    const thinkingMsg: PanelMessage = {
      id: assistantId,
      role: "assistant",
      subtype: "thinking",
      content: "",
    };

    setMessages((prev) => [...prev, userMsg, thinkingMsg]);
    setStreaming(true);
    setStreamingMessageId(assistantId);

    const token = getAccessToken();
    const history = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const resp = await fetch("/api/v1/ai/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          workspace_id: workspaceId,
          message:
            language === "auto"
              ? text
              : `[Prefer ${language.toUpperCase()} when generating code]\n${text}`,
          history,
          provider: currentModel?.provider,
          model: currentModel?.id?.split(":")[1],
        }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error("Failed to stream AI response");
      }

      const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += value;
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const payload = parseSseLine<{ type?: string; text?: string; full_text?: string; message?: string }>(line);
          if (!payload) continue;
          if (payload.type === "token" && payload.text) {
            fullText += payload.text;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      subtype: fullText.includes("```") ? "code_block" : "text",
                      content: fullText,
                      language: detectLanguage(fullText),
                    }
                  : m,
              ),
            );
          }
          if (payload.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      subtype: "error",
                      content: payload.message || "An error occurred.",
                      complete: true,
                    }
                  : m,
              ),
            );
            break;
          }
          if (payload.type === "complete") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      subtype: (m.content || payload.full_text || "").includes("```")
                        ? "code_block"
                        : "text",
                      complete: true,
                      language: detectLanguage(m.content || payload.full_text || ""),
                    }
                  : m,
              ),
            );
          }
        }
      }
    } catch (error) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                subtype: "error",
                content: error instanceof Error ? error.message : "Failed to generate response.",
                complete: true,
              }
            : m,
        ),
      );
    } finally {
      setStreaming(false);
      setStreamingMessageId(null);
    }
  };

  const onInputKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "enter") {
      e.preventDefault();
      void send();
    }
  };

  const hasConfiguredModel = (model: ModelChoice) => model.configured;

  return (
    <TooltipProvider>
      <div 
        className="flex h-full flex-col border-l border-forge-border bg-forge-surface"
        style={{ width }}
      >
        <div className="flex items-center justify-between border-b border-forge-border px-3 py-2">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-forge-accent" />
            <span className="text-sm font-semibold text-foreground">AI Assistant</span>
          </div>

          <div className="flex items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                  <button className="rounded-md border border-forge-border bg-forge-bg px-2 py-1 text-xs text-foreground hover:bg-forge-border">
                    {currentModel?.label ?? "Select model"}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {modelChoices.map((model) => {
                    const enabled = hasConfiguredModel(model);
                    const row = (
                      <DropdownMenuItem
                        key={model.id}
                      disabled={!enabled}
                      onClick={() => enabled && setModelId(model.id)}
                      className="flex items-center justify-between gap-3"
                    >
                      <span>{model.label}</span>
                      {model.id === modelId && <CheckCircle2 className="h-3.5 w-3.5 text-green-400" />}
                    </DropdownMenuItem>
                    );
                  if (enabled) return row;
                  return (
                    <Tooltip key={model.id}>
                      <TooltipTrigger asChild>
                        <div>{row}</div>
                      </TooltipTrigger>
                      <TooltipContent>Configure provider in Settings</TooltipContent>
                    </Tooltip>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>

            <button
              onClick={onClose}
              className="rounded-md p-1 text-forge-muted hover:bg-forge-border hover:text-foreground"
              aria-label="Close AI panel"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <ScrollArea className="flex-1 px-3 py-3">
          <div className="space-y-3">
            {messages.length === 0 && (
              <p className="mt-10 text-center text-xs text-forge-muted">
                Ask anything about your data and analysis.
              </p>
            )}

            {messages.map((msg) => (
              <div key={msg.id}>
                {msg.role === "system" && (
                  <div className="text-center text-xs text-forge-muted">{msg.content}</div>
                )}

                {msg.role === "user" && (
                  <div className="flex justify-end gap-2">
                    <div className="max-w-[85%] rounded-xl bg-forge-bg px-3 py-2 text-sm text-foreground">
                      {msg.content}
                    </div>
                    <div className="mt-0.5 rounded-full bg-forge-border p-1.5">
                      <UserIcon className="h-3.5 w-3.5" />
                    </div>
                  </div>
                )}

                {msg.role === "assistant" && (
                  <div className="flex gap-2">
                    <div className="mt-0.5 rounded-full bg-forge-accent/20 p-1.5 text-forge-accent">
                      <Bot className="h-3.5 w-3.5" />
                    </div>
                    <div
                      className={cn(
                        "max-w-[88%] rounded-xl border px-3 py-2 text-sm",
                        msg.subtype === "error"
                          ? "border-red-800 bg-red-950/40 text-red-200"
                          : "border-forge-border bg-forge-bg text-foreground",
                      )}
                    >
                      {msg.subtype === "thinking" ? (
                        <ThinkingDots />
                      ) : msg.subtype === "code_block" ? (
                        <CodeMessage
                          message={msg}
                          onInsert={insertAsCell}
                          highlightedCellId={justInsertedCellId}
                        />
                      ) : (
                        <div className="prose prose-invert prose-sm max-w-none">
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                          {streamingMessageId === msg.id && (
                            <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-forge-accent align-middle" />
                          )}
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

        <div className="border-t border-forge-border p-3">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              resizeTextarea();
            }}
            onKeyDown={onInputKeyDown}
            placeholder="Ask AI to analyze, generate code, or explain output..."
            className="max-h-[200px] min-h-[72px] resize-none bg-forge-bg"
          />

          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1">
              {(["auto", "python", "sql", "r"] as const).map((lang) => (
                <button
                  key={lang}
                  onClick={() => setLanguage(lang)}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs",
                    language === lang
                      ? "bg-forge-accent text-forge-bg"
                      : "bg-forge-bg text-forge-muted hover:bg-forge-border hover:text-foreground",
                  )}
                >
                  {lang === "auto" ? "Auto" : lang.toUpperCase()}
                </button>
              ))}
            </div>

            <Button
              size="sm"
              onClick={() => void send()}
              disabled={streaming || !input.trim()}
              className="bg-forge-accent text-forge-bg hover:bg-forge-accent-dim"
            >
              {streaming ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            </Button>
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action}
                onClick={() => void send(action)}
                className="rounded-full border border-forge-border bg-forge-bg px-2.5 py-1 text-[11px] text-forge-muted hover:border-forge-accent/60 hover:text-forge-accent"
              >
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

function ThinkingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      <span className="h-2 w-2 animate-bounce rounded-full bg-forge-accent [animation-delay:-0.3s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-forge-accent [animation-delay:-0.15s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-forge-accent" />
    </div>
  );
}

function CodeMessage({
  message,
  onInsert,
  highlightedCellId,
}: {
  message: PanelMessage;
  onInsert: (message: PanelMessage) => Promise<void>;
  highlightedCellId: string | null;
}) {
  const fenced = message.content.match(/```([a-zA-Z]*)\n([\s\S]*?)```/);
  const lang = (fenced?.[1] || message.language || "python").toString().toLowerCase();
  const code = fenced?.[2] ?? message.content;

  return (
    <div className="space-y-2">
      <div className="overflow-hidden rounded-md border border-forge-border">
        <MonacoEditor
          height={220}
          language={lang}
          theme="vs-dark"
          value={code}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 12,
            scrollBeyondLastLine: false,
            wordWrap: "off",
          }}
        />
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-forge-muted">{lang}</span>
        {message.complete && (
          <button
            onClick={() => void onInsert(message)}
            className={cn(
              "rounded-md border px-2 py-1 text-xs",
              highlightedCellId
                ? "border-green-400 bg-green-500/15 text-green-300"
                : "border-forge-accent/50 bg-forge-accent/10 text-forge-accent hover:bg-forge-accent/20",
            )}
          >
            Insert into new cell
          </button>
        )}
      </div>
      {!fenced && (
        <SyntaxHighlighter language={lang} style={oneDark} customStyle={{ borderRadius: 8, margin: 0 }}>
          {code}
        </SyntaxHighlighter>
      )}
    </div>
  );
}
