"use client";

import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { KeyRound } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import type { AIProviderOption } from "@/types";

type ProviderFormState = {
  apiKey: string;
  baseUrl: string;
  modelPath: string;
  runtimeOptionsText: string;
};

function defaultRuntimeText() {
  return JSON.stringify({ temperature: 0.2 }, null, 2);
}

export default function ApiKeysPage() {
  const { user, fetchMe } = useAuth();
  const [providers, setProviders] = useState<AIProviderOption[]>([]);
  const [loadingProviders, setLoadingProviders] = useState(true);
  const [preferredProvider, setPreferredProvider] = useState<string>(
    user?.preferred_llm_provider ?? "ollama",
  );
  const [forms, setForms] = useState<Record<string, ProviderFormState>>({});
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState<Record<string, "ok" | "err" | null>>({});
  const [testStatus, setTestStatus] = useState<Record<string, string>>({});
  const [globalError, setGlobalError] = useState<string | null>(null);

  const sortedProviders = useMemo(
    () =>
      [...providers].sort((a, b) => {
        const pa = a.priority ?? 999;
        const pb = b.priority ?? 999;
        return pa - pb;
      }),
    [providers],
  );

  useEffect(() => {
    setPreferredProvider(user?.preferred_llm_provider ?? "ollama");
  }, [user?.preferred_llm_provider]);

  useEffect(() => {
    const loadProviders = async () => {
      setLoadingProviders(true);
      setGlobalError(null);
      try {
        const resp = await api.get<AIProviderOption[]>("/api/v1/ai/providers");
        setProviders(resp.data);
        const nextForms: Record<string, ProviderFormState> = {};
        for (const provider of resp.data) {
          const isLocal = Boolean(provider.local);
          nextForms[provider.id] = {
            apiKey: "",
            baseUrl: provider.id === "ollama" ? "http://localhost:11434" : "",
            modelPath: "",
            runtimeOptionsText: isLocal ? defaultRuntimeText() : "{}",
          };
        }
        setForms(nextForms);
      } catch {
        setGlobalError("Failed to load AI providers. Please refresh.");
      } finally {
        setLoadingProviders(false);
      }
    };
    void loadProviders();
  }, []);

  const updateForm = (providerId: string, patch: Partial<ProviderFormState>) => {
    setForms((prev) => ({
      ...prev,
      [providerId]: {
        ...(prev[providerId] ?? {
          apiKey: "",
          baseUrl: "",
          modelPath: "",
          runtimeOptionsText: "{}",
        }),
        ...patch,
      },
    }));
  };

  const testProvider = async (providerId: string) => {
    setTesting((s) => ({ ...s, [providerId]: true }));
    setTestStatus((s) => ({ ...s, [providerId]: "" }));
    try {
      const form = forms[providerId];
      const providerSettings: Record<string, any> = {};
      if (form?.baseUrl?.trim()) providerSettings.base_url = form.baseUrl.trim();
      if (form?.modelPath?.trim()) providerSettings.model_path = form.modelPath.trim();
      if (form?.runtimeOptionsText?.trim()) {
        try {
          providerSettings.runtime_options = JSON.parse(form.runtimeOptionsText);
        } catch {
          throw new Error("Runtime options must be valid JSON before testing.");
        }
      }

      await api.patch("/api/v1/auth/me/api-keys", {
        provider_settings: { [providerId]: providerSettings },
      });

      const resp = await api.post("/api/v1/auth/me/api-keys/test", { provider: providerId });
      const valid = Boolean(resp.data?.valid);
      const error = resp.data?.error;
      setTestStatus((s) => ({
        ...s,
        [providerId]: valid ? "Connection successful." : `Failed: ${error ?? "Unknown error"}`,
      }));
    } catch (error) {
      setTestStatus((s) => ({
        ...s,
        [providerId]: error instanceof Error ? error.message : "Failed to test provider.",
      }));
    } finally {
      setTesting((s) => ({ ...s, [providerId]: false }));
    }
  };

  const saveAll = async () => {
    setSaving(true);
    setStatus({});
    setGlobalError(null);
    try {
      const provider_api_keys: Record<string, string | null> = {};
      const provider_settings: Record<string, Record<string, any>> = {};

      for (const provider of sortedProviders) {
        const form = forms[provider.id];
        if (!form) continue;

        provider_api_keys[provider.id] = form.apiKey.trim() || null;
        provider_settings[provider.id] = {};
        if (form.baseUrl.trim()) provider_settings[provider.id].base_url = form.baseUrl.trim();
        if (form.modelPath.trim()) provider_settings[provider.id].model_path = form.modelPath.trim();
        if (form.runtimeOptionsText.trim()) {
          try {
            provider_settings[provider.id].runtime_options = JSON.parse(form.runtimeOptionsText);
          } catch {
            throw new Error(`Runtime options for ${provider.name} must be valid JSON.`);
          }
        }
      }

      await api.patch("/api/v1/auth/me/api-keys", {
        provider_api_keys,
        provider_settings,
      });
      await api.patch("/api/v1/auth/me", {
        preferred_llm_provider: preferredProvider,
      });
      await fetchMe();
      const okStatus: Record<string, "ok"> = { preferred_llm_provider: "ok" };
      for (const provider of sortedProviders) okStatus[provider.id] = "ok";
      setStatus(okStatus);
      setForms((prev) => {
        const next = { ...prev };
        for (const key of Object.keys(next)) {
          next[key] = { ...next[key], apiKey: "" };
        }
        return next;
      });
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : "Failed to save AI provider settings.";
      setGlobalError(errMsg);
      const errStatus: Record<string, "err"> = { preferred_llm_provider: "err" };
      for (const provider of sortedProviders) errStatus[provider.id] = "err";
      setStatus(errStatus);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="mb-6 text-2xl font-semibold text-foreground flex items-center gap-2">
        <KeyRound className="h-6 w-6 text-forge-accent" />
        AI Provider Configuration
      </h1>
      <p className="mb-4 text-sm text-forge-muted">
        Local runtimes are prioritized automatically. Configure local engines first, then optional cloud fallbacks.
      </p>

      {globalError && <p className="mb-4 text-sm text-red-400">{globalError}</p>}

      {loadingProviders ? (
        <p className="text-sm text-forge-muted">Loading providers...</p>
      ) : (
        <div className="space-y-4">
          {sortedProviders.map((provider) => {
            const form = forms[provider.id] ?? {
              apiKey: "",
              baseUrl: "",
              modelPath: "",
              runtimeOptionsText: provider.local ? defaultRuntimeText() : "{}",
            };
            return (
              <div key={provider.id} className="rounded-lg border border-forge-border bg-forge-surface p-5">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-sm font-medium text-foreground">{provider.name}</p>
                  <span className="text-xs text-forge-muted">
                    {provider.local ? "Local" : "Cloud"} · {provider.configured ? "Configured" : "Not set"}
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="text-xs text-forge-muted">
                    Models: {provider.models.join(", ")}
                  </div>

                  {provider.requires_api_key && (
                    <input
                      type="password"
                      value={form.apiKey}
                      onChange={(e) => updateForm(provider.id, { apiKey: e.target.value })}
                      placeholder="API key"
                      className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
                    />
                  )}

                  {(provider.required_settings ?? []).includes("base_url") && (
                    <input
                      type="text"
                      value={form.baseUrl}
                      onChange={(e) => updateForm(provider.id, { baseUrl: e.target.value })}
                      placeholder="Base URL (e.g. http://localhost:11434)"
                      className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
                    />
                  )}

                  {(provider.required_settings ?? []).includes("model_path") && (
                    <input
                      type="text"
                      value={form.modelPath}
                      onChange={(e) => updateForm(provider.id, { modelPath: e.target.value })}
                      placeholder="Model path"
                      className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
                    />
                  )}

                  <textarea
                    value={form.runtimeOptionsText}
                    onChange={(e) => updateForm(provider.id, { runtimeOptionsText: e.target.value })}
                    rows={4}
                    className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-xs font-mono text-foreground placeholder:text-forge-muted focus:border-forge-accent focus:outline-none"
                    placeholder='{"temperature":0.2}'
                  />

                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => void testProvider(provider.id)}
                      disabled={testing[provider.id]}
                      className="rounded-md border border-forge-border px-3 py-2 text-sm font-semibold text-foreground hover:bg-forge-border/40 disabled:opacity-50"
                    >
                      {testing[provider.id] ? "Testing…" : "Test"}
                    </button>
                    {status[provider.id] === "ok" && (
                      <span className="text-xs text-green-400">Saved</span>
                    )}
                    {status[provider.id] === "err" && (
                      <span className="text-xs text-red-400">Save failed</span>
                    )}
                  </div>

                  {testStatus[provider.id] && (
                    <p className="text-xs text-forge-muted">{testStatus[provider.id]}</p>
                  )}
                </div>
              </div>
            );
          })}

          <div className="rounded-lg border border-forge-border bg-forge-surface p-5">
            <p className="mb-3 text-sm font-medium text-foreground">Preferred provider</p>
            <select
              value={preferredProvider}
              onChange={(e) => setPreferredProvider(e.target.value)}
              className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-foreground focus:border-forge-accent focus:outline-none"
            >
              {sortedProviders.map((provider) => (
                <option key={provider.id} value={provider.id}>
                  {provider.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex justify-end">
            <button
              onClick={() => void saveAll()}
              disabled={saving}
              className="rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save configuration"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
