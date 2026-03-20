"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { KeyRound } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";

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
      setStatus("Configuration saved.");
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
        setStatus(`${providerId}: connection successful.`);
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
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="mb-4 text-2xl font-semibold text-foreground flex items-center gap-2">
        <KeyRound className="h-6 w-6 text-forge-accent" />
        Universal AI Provider JSON Config
      </h1>
      <p className="mb-4 text-sm text-forge-muted">
        Edit the full provider config JSON directly. Local providers are checked first, then cloud fallback.
      </p>

      {loading ? (
        <p className="text-sm text-forge-muted">Loading configuration...</p>
      ) : (
        <>
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            rows={26}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-3 text-xs font-mono text-foreground focus:border-forge-accent focus:outline-none"
          />

          <div className="mt-3 flex flex-wrap gap-2">
            {providerIds.map((providerId) => (
              <button
                key={providerId}
                onClick={() => void testProvider(providerId)}
                disabled={Boolean(testingProvider) || saving}
                className="rounded-md border border-forge-border px-3 py-2 text-xs text-foreground hover:bg-forge-border/40 disabled:opacity-50"
              >
                {testingProvider === providerId ? `Testing ${providerId}…` : `Test ${providerId}`}
              </button>
            ))}

            <button
              onClick={() => void saveJsonConfig()}
              disabled={saving || Boolean(testingProvider)}
              className="ml-auto rounded-md bg-forge-accent px-4 py-2 text-sm font-semibold text-forge-bg hover:bg-forge-accent-dim disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save JSON configuration"}
            </button>
          </div>

          {status && <p className="mt-3 text-sm text-green-400">{status}</p>}
          {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
        </>
      )}
    </div>
  );
}
