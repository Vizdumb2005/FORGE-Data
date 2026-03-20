"use client";

import { useState } from "react";
import api from "@/lib/api";
import { KeyRound, Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import type { LLMProvider } from "@/types";

const PROVIDERS: { key: LLMProvider; label: string; placeholder: string }[] = [
  { key: "openai", label: "OpenAI", placeholder: "sk-..." },
  { key: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
];

export default function ApiKeysPage() {
  const { user, fetchMe } = useAuth();
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<Record<string, "ok" | "err" | null>>({});
  const [testStatus, setTestStatus] = useState<Record<string, string>>({});
  const [preferredProvider, setPreferredProvider] = useState<LLMProvider>(
    (user?.preferred_llm_provider as LLMProvider) ?? "openai",
  );

  const saveAll = async () => {
    setSaving(true);
    setStatus({});
    try {
      await api.patch("/api/v1/auth/me/api-keys", {
        openai_api_key: values.openai?.trim() || null,
        anthropic_api_key: values.anthropic?.trim() || null,
        ollama_base_url: values.ollama?.trim() || null,
      });
      await api.patch("/api/v1/auth/me", {
        preferred_llm_provider: preferredProvider,
      });
      await fetchMe();
      setStatus({
        openai: values.openai ? "ok" : null,
        anthropic: values.anthropic ? "ok" : null,
        ollama: values.ollama ? "ok" : null,
        preferred_llm_provider: "ok",
      });
      setValues({});
    } catch {
      setStatus({
        openai: "err",
        anthropic: "err",
        ollama: "err",
        preferred_llm_provider: "err",
      });
    } finally {
      setSaving(false);
    }
  };

  const testProvider = async (provider: LLMProvider) => {
    setTesting((s) => ({ ...s, [provider]: true }));
    try {
      const resp = await api.post("/api/v1/auth/me/api-keys/test", { provider });
      const valid = Boolean(resp.data?.valid);
      const error = resp.data?.error;
      setTestStatus((s) => ({
        ...s,
        [provider]: valid ? "Connection successful." : `Failed: ${error ?? "Unknown error"}`,
      }));
    } catch {
      setTestStatus((s) => ({ ...s, [provider]: "Failed to test connection." }));
    } finally {
      setTesting((s) => ({ ...s, [provider]: false }));
    }
  };

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="mb-6 text-2xl font-semibold text-foreground flex items-center gap-2">
        <KeyRound className="h-6 w-6 text-forge-accent" />
        AI API Keys
      </h1>
      <p className="mb-6 text-sm text-forge-muted">
        Keys are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) and
        never returned in API responses.
      </p>
      <p className="mb-6 text-sm text-forge-muted">
        Prefer local AI? Configure Ollama below with your local endpoint (for example:
        <span className="font-mono"> http://localhost:11434</span>) and set preferred provider to Ollama.
      </p>

      <div className="space-y-4">
        {PROVIDERS.map(({ key, label, placeholder }) => (
          <div
            key={key}
            className="rounded-lg border border-forge-border bg-forge-surface p-5"
          >
            <p className="mb-3 text-sm font-medium text-foreground">{label}</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={visible[key] ? "text" : "password"}
                  value={values[key] ?? ""}
                  onChange={(e) =>
                    setValues((v) => ({ ...v, [key]: e.target.value }))
                  }
                  placeholder={placeholder}
                  className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none pr-10"
                />
                <button
                  type="button"
                  onClick={() =>
                    setVisible((v) => ({ ...v, [key]: !v[key] }))
                  }
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-forge-muted hover:text-foreground"
                >
                  {visible[key] ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
              <button
                onClick={() => testProvider(key)}
                disabled={testing[key]}
                className="rounded-md border border-forge-border px-3 py-2 text-sm font-semibold text-foreground hover:bg-forge-border/40 disabled:opacity-50"
              >
                {testing[key] ? "Testing…" : "Test"}
              </button>
            </div>
            {testStatus[key] && (
              <p className="mt-2 text-xs text-forge-muted">{testStatus[key]}</p>
            )}
            {status[key] === "ok" && (
              <p className="mt-2 text-xs text-green-400">Saved successfully.</p>
            )}
            {status[key] === "err" && (
              <p className="mt-2 text-xs text-red-400">Failed to save.</p>
            )}
          </div>
        ))}

        <div className="rounded-lg border border-forge-border bg-forge-surface p-5">
          <p className="mb-3 text-sm font-medium text-foreground">Ollama (Local)</p>
          <div className="flex gap-2">
            <input
              type="text"
              value={values.ollama ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, ollama: e.target.value }))}
              placeholder="http://localhost:11434"
              className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
            />
            <button
              onClick={() => testProvider("ollama")}
              disabled={testing.ollama}
              className="rounded-md border border-forge-border px-3 py-2 text-sm font-semibold text-foreground hover:bg-forge-border/40 disabled:opacity-50"
            >
              {testing.ollama ? "Testing…" : "Test"}
            </button>
          </div>
          <p className="mt-2 text-xs text-forge-muted">
            {user?.has_ollama_url
              ? "A local endpoint is currently configured."
              : "No local endpoint configured yet."}
          </p>
          {testStatus.ollama && <p className="mt-2 text-xs text-forge-muted">{testStatus.ollama}</p>}
          {status.ollama === "ok" && (
            <p className="mt-2 text-xs text-green-400">Saved successfully.</p>
          )}
          {status.ollama === "err" && (
            <p className="mt-2 text-xs text-red-400">Failed to save.</p>
          )}
        </div>

        <div className="rounded-lg border border-forge-border bg-forge-surface p-5">
          <p className="mb-3 text-sm font-medium text-foreground">Preferred provider</p>
          <select
            value={preferredProvider}
            onChange={(e) => setPreferredProvider(e.target.value as LLMProvider)}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground focus:border-forge-accent focus:outline-none"
          >
            <option value="ollama">Ollama (Local models)</option>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
          {status.preferred_llm_provider === "ok" && (
            <p className="mt-2 text-xs text-green-400">Preference updated.</p>
          )}
          {status.preferred_llm_provider === "err" && (
            <p className="mt-2 text-xs text-red-400">Failed to update preference.</p>
          )}
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={saveAll}
          disabled={saving}
          className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save configuration"}
        </button>
      </div>
    </div>
  );
}
