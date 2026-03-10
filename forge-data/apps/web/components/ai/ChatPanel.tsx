"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2 } from "lucide-react";
import { cn, parseSseLine } from "@/lib/utils";
import { getAccessToken } from "@/lib/auth";
import type { ChatMessage, LLMProvider } from "@/types";

interface ChatPanelProps {
  workspaceId: string;
}

const BASE_URL = typeof window !== "undefined" ? "" : process.env.NEXT_PUBLIC_API_URL ?? "";

export default function ChatPanel({ workspaceId }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "system",
      content: `You are a data assistant helping the user analyse data in workspace ${workspaceId}. Be concise and helpful.`,
    },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [provider, setProvider] = useState<LLMProvider>("openai");
  const bottomRef = useRef<HTMLDivElement>(null);

  const visibleMessages = messages.filter((m) => m.role !== "system");

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visibleMessages.length, streaming]);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");

    const newMessages: ChatMessage[] = [
      ...messages,
      { role: "user", content: text },
    ];
    setMessages(newMessages);
    setStreaming(true);

    // Append placeholder for assistant response
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const token = getAccessToken();
      const resp = await fetch(`${BASE_URL}/api/v1/ai/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ messages: newMessages, provider }),
      });

      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const line of value.split("\n")) {
          const payload = parseSseLine<{ delta?: string }>(line);
          if (payload?.delta) {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + payload.delta,
                };
              }
              return updated;
            });
          }
        }
      }
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === "assistant" && last.content === "") {
          updated[updated.length - 1] = {
            ...last,
            content: "Error: failed to get a response.",
          };
        }
        return updated;
      });
      console.error(err);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-forge-border px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          <Bot className="h-4 w-4 text-forge-accent" />
          AI Assistant
        </div>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as LLMProvider)}
          className="rounded border border-forge-border bg-forge-bg px-2 py-0.5 text-xs text-forge-muted focus:outline-none"
        >
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
          <option value="ollama">Ollama</option>
        </select>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {visibleMessages.length === 0 && (
          <p className="text-center text-xs text-forge-muted mt-8">
            Ask anything about your data…
          </p>
        )}
        {visibleMessages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex gap-2",
              msg.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {msg.role === "assistant" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-forge-accent/20 text-forge-accent">
                <Bot className="h-3.5 w-3.5" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-forge-accent/10 text-foreground"
                  : "bg-forge-surface border border-forge-border text-foreground"
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {streaming && i === visibleMessages.length - 1 && msg.role === "assistant" && (
                <Loader2 className="mt-1 h-3 w-3 animate-spin text-forge-muted" />
              )}
            </div>
            {msg.role === "user" && (
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-forge-border">
                <User className="h-3.5 w-3.5 text-foreground" />
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-forge-border p-3">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask about your data…"
            className="flex-1 rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
          />
          <button
            onClick={send}
            disabled={!input.trim() || streaming}
            className="rounded-md bg-forge-accent p-2 text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
