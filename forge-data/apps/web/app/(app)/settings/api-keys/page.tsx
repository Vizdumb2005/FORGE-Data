"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, Save, Terminal, Play } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { cn } from "@/lib/utils";

const PLACEHOLDER_KEY = "[[ENCRYPTED_EXISTS]]";

export default function ApiKeysPage() {
  const { fetchMe } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingProvider, setTestingProvider] = useState<string>("");
  const [jsonText, setJsonText] = useState("");
  const [status, setStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [providerIds, setProviderIds] = useState<string[]>([]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const resp = await api.get("/api/v1/auth/me/provider-config");
        setJsonText(JSON.stringify(resp.data, null, 2));
        setProviderIds(Object.keys(resp.data?.providers ?? {}));
      } catch (e) {
        setError("Failed to load provider configuration JSON.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const parseConfig = () => {
    try {
      return JSON.parse(jsonText) as {
        providers: Record<
          string,
          {
            api_key?: string;
            default_model?: string;
            base_url?: string;
            model_path?: string;
            params?: Record<string, unknown>;
          }
        >;
        settings?: {
          active_provider?: string;
          fallback_order?: string[];
          timeout?: number;
          retry_attempts?: number;
        };
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
        if (!rawKey || rawKey === PLACEHOLDER_KEY) {
          provider_api_keys[providerId] = null;
        } else {
          provider_api_keys[providerId] = rawKey;
        }
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

      await api.patch("/api/v1/auth/me/api-keys", {
        provider_api_keys,
        provider_settings,
      });
      await api.patch("/api/v1/auth/me", {
        preferred_llm_provider: parsed.settings?.active_provider ?? "ollama",
      });
      await fetchMe();
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
        setStatus(`${providerId}: connection verified.`);
      } else {
        setError(`${providerId}: ${resp.data?.error ?? "validation failed"}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : `Failed to test ${providerId}.`);
    } finally {
      setTestingProvider("");
    }
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
        <div className="flex gap-2">
           <button
              onClick={() => void saveJsonConfig()}
              disabled={saving || Boolean(testingProvider)}
              className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2"
            >
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              {saving ? "Saving..." : "Save Configuration"}
            </button>
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
                  <span className="text-xs text-muted-foreground">JSON</span>
                </div>
                <div className="relative">
                  <label htmlFor="config-json" className="sr-only">Configuration JSON</label>
                  <textarea
                    id="config-json"
                    value={jsonText}
                    onChange={(e) => setJsonText(e.target.value)}
                    rows={24}
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
            <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6">
              <h3 className="font-semibold leading-none tracking-tight mb-4">Connection Test</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Verify your API keys and connectivity for each provider.
              </p>
              
              <div className="space-y-2">
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

            <div className="rounded-lg border bg-card text-card-foreground shadow-sm p-6">
               <h3 className="font-semibold leading-none tracking-tight mb-2">Help</h3>
               <ul className="text-sm text-muted-foreground space-y-2 list-disc list-inside">
                  <li>Local providers are prioritized.</li>
                  <li>Use <code className="bg-muted px-1 rounded">[[ENCRYPTED_EXISTS]]</code> to keep existing keys.</li>
                  <li>Check logs for detailed errors.</li>
               </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
