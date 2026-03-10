"use client";

import { useState } from "react";
import api from "@/lib/api";
import { KeyRound, Eye, EyeOff } from "lucide-react";
import type { LLMProvider } from "@/types";

const PROVIDERS: { key: LLMProvider; label: string; placeholder: string }[] = [
  { key: "openai", label: "OpenAI", placeholder: "sk-..." },
  { key: "anthropic", label: "Anthropic", placeholder: "sk-ant-..." },
];

export default function ApiKeysPage() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<Record<string, "ok" | "err" | null>>({});

  const save = async (provider: LLMProvider) => {
    const key = values[provider];
    if (!key) return;
    setSaving((s) => ({ ...s, [provider]: true }));
    try {
      await api.put(`/api/v1/users/me/llm-keys/${provider}`, { api_key: key });
      setStatus((s) => ({ ...s, [provider]: "ok" }));
      setValues((v) => ({ ...v, [provider]: "" }));
    } catch {
      setStatus((s) => ({ ...s, [provider]: "err" }));
    } finally {
      setSaving((s) => ({ ...s, [provider]: false }));
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
                onClick={() => save(key)}
                disabled={!values[key] || saving[key]}
                className="rounded-md bg-forge-accent px-3 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
              >
                {saving[key] ? "Saving…" : "Save"}
              </button>
            </div>
            {status[key] === "ok" && (
              <p className="mt-2 text-xs text-green-400">Saved successfully.</p>
            )}
            {status[key] === "err" && (
              <p className="mt-2 text-xs text-red-400">Failed to save.</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
