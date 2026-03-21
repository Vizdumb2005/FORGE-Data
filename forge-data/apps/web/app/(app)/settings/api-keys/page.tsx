"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, Save, Terminal, Play, Copy, Check, Info } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { cn } from "@/lib/utils";

const PLACEHOLDER_KEY = "[[ENCRYPTED_EXISTS]]";

// Ready-to-fill template shown when no config exists yet
const CONFIG_TEMPLATE = `{
  "providers": {

    // ── Local AI (runs on your machine) ─────────────────────────────────────
    // When the app runs in Docker, use host.docker.internal instead of
    // localhost so the container can reach your local AI server.

    "ollama": {
      "api_key": "",
      "default_model": "qwen3:8b",
      "base_url": "http://host.docker.internal:11434",
      "model_path": "",
      "params": { "temperature": 0.7, "num_ctx": 4096 }
    },

    "llama_cpp": {
      "api_key": "",
      "default_model": "llama-3.1-8b-instruct",
      "base_url": "http://host.docker.internal:8080/v1",
      "model_path": "/path/to/your/model.gguf",
      "params": { "temperature": 0.2 }
    },

    "vllm": {
      "api_key": "",
      "default_model": "Qwen/Qwen2.5-7B-Instruct",
      "base_url": "http://host.docker.internal:8001/v1",
      "model_path": "",
      "params": { "temperature": 0.2, "top_p": 0.95 }
    },

    // ── Cloud AI (requires API key) ──────────────────────────────────────────

    "openai": {
      "api_key": "sk-...",
      "default_model": "gpt-4o-mini",
      "base_url": "",
      "model_path": "",
      "params": { "temperature": 0.2 }
    },

    "anthropic": {
      "api_key": "sk-ant-...",
      "default_model": "claude-3-5-sonnet-latest",
      "base_url": "",
      "model_path": "",
      "params": { "temperature": 0.2 }
    },

    "gemini": {
      "api_key": "AIza...",
      "default_model": "gemini-2.0-flash",
      "base_url": "",
      "model_path": "",
      "params": {}
    }
  },

  "settings": {
    "active_provider": "ollama",
    "fallback_order": ["ollama", "llama_cpp", "vllm", "openai", "anthropic", "gemini"],
    "timeout": 30,
    "retry_attempts": 3
  }
}`;

export default function ApiKeysPage() {
  const { fetchMe } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingProvider, setTestingProvider] = useState<string>("");
  const [jsonText, setJsonText] = useState("");
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [providerIds, setProviderIds] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const resp = await api.get("/api/v1/auth/me/provider-config");
        // If no providers configured yet, show the ready-to-fill template
        const hasConfig = Object.values(resp.data?.providers ?? {}).some(
          (p: any) => p.api_key || p.base_url
        );
        setJsonText(hasConfig ? JSON.stringify(resp.data, null, 2) : CONFIG_TEMPLATE);
        setProviderIds(Object.keys(resp.data?.providers ?? {}));
      } catch {
        setError("Failed to load provider configuration.");
        setJsonText(CONFIG_TEMPLATE);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const parseConfig = () => {
    // Strip JS-style comments before parsing
    const stripped = jsonText.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
    try {
      return JSON.parse(stripped) as {
        providers: Record<string, { api_key?: string; default_model?: string; base_url?: string; model_path?: string; params?: Record<string, unknown> }>;
        settings?: { active_provider?: string; fallback_order?: string[]; timeout?: number; retry_attempts?: number };
      };
    } catch {
      throw new Error("Config JSON is invalid. Fix syntax and try again.");
    }
  };

  const saveJsonConfig = async () => {
    setSaving(true);
    setStatus("");
    setError("");
    try {
      const parsed = parseConfig();
      const providers = parsed.providers ?? {};
      const provider_api_keys: Record<string, string | null> = {};
      const provider_settings: Record<string, Record<string, unknown>> = {};

      for (const [providerId, cfg] of Object.entries(providers)) {
        const rawKey = (cfg.api_key ?? "").trim();
        provider_api_keys[providerId] = !rawKey || rawKey === PLACEHOLDER_KEY ? null : rawKey;
        provider_settings[providerId] = {
          default_model: cfg.default_model ?? "",
          base_url: cfg.base_url ?? "",
          model_path: cfg.model_path ?? "",
          runtime_options: cfg.params ?? {},
        };
      }

      provider_settings.__settings__ = {
        fallback_order: parsed.settings?.fallback_order ?? [],
        timeout: parsed.settings?.timeout ?? 30,
        retry_attempts: parsed.settings?.retry_attempts ?? 3,
      };

      await api.patch("/api/v1/auth/me/api-keys", { provider_api_keys, provider_settings });
      await api.patch("/api/v1/auth/me", {
        preferred_llm_provider: parsed.settings?.active_provider ?? "ollama",
      });
      await fetchMe();
      setProviderIds(Object.keys(providers));
      setStatus("Configuration saved successfully.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save configuration.");
    } finally {
      setSaving(false);
    }
  };

  const testProvider = async (providerId: string) => {
    setTestingProvider(providerId);
    setStatus("");
    setError("");
    try {
      await saveJsonConfig();
      const resp = await api.post("/api/v1/auth/me/api-keys/test", { provider: providerId });
      if (resp.data?.valid) {
        setStatus(`✓ ${providerId}: connection verified.`);
      } else {
        setError(`✗ ${providerId}: ${resp.data?.error ?? "validation failed"}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to test ${providerId}.`);
    } finally {
      setTestingProvider("");
    }
  };

  const copyTemplate = async () => {
    await navigator.clipboard.writeText(CONFIG_TEMPLATE);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="container mx-auto max-w-5xl py-10 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">AI Configuration</h1>
          <p className="text-muted-foreground mt-2">
            Configure AI providers, API keys, and model parameters.
          </p>
        </div>
        <button
          onClick={() => void saveJsonConfig()}
          disabled={saving || Boolean(testingProvider)}
          className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
        >
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          {saving ? "Saving..." : "Save Configuration"}
        </button>
      </div>

      {/* Local AI notice */}
      <div className="flex gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 p-4 text-sm text-blue-300">
        <Info className="h-4 w-4 mt-0.5 shrink-0" />
        <div className="space-y-1">
          <p className="font-medium">Running local AI (Ollama / llama.cpp / vLLM)?</p>
          <p className="text-blue-300/80">
            Because the app runs inside Docker, use{" "}
            <code className="rounded bg-blue-900/50 px-1 font-mono">host.docker.internal</code>{" "}
            instead of <code className="rounded bg-blue-900/50 px-1 font-mono">localhost</code> in
            your <code className="rounded bg-blue-900/50 px-1 font-mono">base_url</code>. This is
            already pre-filled in the template below.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/50">
                <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <Terminal className="h-3.5 w-3.5" />
                  <span>config.json</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">JSON (// comments allowed)</span>
                  <button
                    onClick={() => void copyTemplate()}
                    className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                    title="Copy template"
                  >
                    {copied ? <Check className="h-3 w-3 text-green-400" /> : <Copy className="h-3 w-3" />}
                    {copied ? "Copied" : "Copy template"}
                  </button>
                </div>
              </div>
              <div className="relative">
                <label htmlFor="config-json" className="sr-only">Configuration JSON</label>
                <textarea
                  id="config-json"
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                  rows={32}
                  spellCheck={false}
                  className="flex w-full bg-slate-950 px-4 py-4 text-xs font-mono text-slate-50 placeholder:text-muted-foreground focus-visible:outline-none resize-none leading-relaxed"
                  aria-label="Configuration JSON editor"
                />
              </div>
            </div>

            {status && (
              <div className="rounded-md bg-green-500/15 p-3 text-sm text-green-500 border border-green-500/20">
                {status}
              </div>
            )}
            {error && (
              <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive border border-destructive/20">
                {error}
              </div>
            )}
          </div>

          <div className="space-y-6">
            {/* Connection test */}
            <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6">
              <h3 className="font-semibold leading-none tracking-tight mb-4">Connection Test</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Save first, then verify connectivity for each provider.
              </p>
              <div className="space-y-2">
                {providerIds.length === 0 && (
                  <p className="text-xs text-muted-foreground">Save your config to enable tests.</p>
                )}
                {providerIds.map((providerId) => (
                  <button
                    key={providerId}
                    onClick={() => void testProvider(providerId)}
                    disabled={Boolean(testingProvider) || saving}
                    className={cn(
                      "flex w-full items-center justify-between rounded-md border border-input bg-transparent px-4 py-2 text-sm shadow-sm transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-50",
                      testingProvider === providerId && "bg-accent text-accent-foreground"
                    )}
                  >
                    <span className="capitalize">{providerId}</span>
                    {testingProvider === providerId ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Play className="h-3.5 w-3.5 opacity-50" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick reference */}
            <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6 space-y-4">
              <h3 className="font-semibold leading-none tracking-tight">Quick Reference</h3>

              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Local AI base_url</p>
                <div className="space-y-1 text-xs font-mono">
                  <div className="flex justify-between gap-2 rounded bg-muted px-2 py-1">
                    <span className="text-muted-foreground">Ollama</span>
                    <span>:11434</span>
                  </div>
                  <div className="flex justify-between gap-2 rounded bg-muted px-2 py-1">
                    <span className="text-muted-foreground">llama.cpp</span>
                    <span>:8080/v1</span>
                  </div>
                  <div className="flex justify-between gap-2 rounded bg-muted px-2 py-1">
                    <span className="text-muted-foreground">vLLM</span>
                    <span>:8001/v1</span>
                  </div>
                  <div className="flex justify-between gap-2 rounded bg-muted px-2 py-1">
                    <span className="text-muted-foreground">GPT4All</span>
                    <span>:4891/v1</span>
                  </div>
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">
                  Prefix with <code className="bg-muted px-1 rounded">http://host.docker.internal</code> when running in Docker.
                </p>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">Tips</p>
                <ul className="text-xs text-muted-foreground space-y-1.5 list-disc list-inside">
                  <li>Local providers are tried first automatically.</li>
                  <li><code className="bg-muted px-1 rounded">[[ENCRYPTED_EXISTS]]</code> = key already saved, leave to keep it.</li>
                  <li>Comments (<code className="bg-muted px-1 rounded">{"// ..."}</code>) are stripped on save.</li>
                  <li>Set <code className="bg-muted px-1 rounded">active_provider</code> to your preferred default.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
