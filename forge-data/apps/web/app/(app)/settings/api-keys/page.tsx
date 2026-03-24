"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Loader2, Play, Check, Trash2, Plus, RefreshCw } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const PLACEHOLDER_KEY = "********";

type ProviderConfig = {
  api_key: string;
  default_model: string;
  base_url: string;
};

export default function ApiKeysPage() {
  const { fetchMe } = useAuth();
  const [loading, setLoading] = useState(true);
  const [savingProvider, setSavingProvider] = useState<string>("");
  const [testingProvider, setTestingProvider] = useState<string>("");
  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({});
  const [activeProvider, setActiveProvider] = useState("ollama");
  const [statusMsg, setStatusMsg] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [newProvider, setNewProvider] = useState("");
  const [newKey, setNewKey] = useState("");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setErrorMsg("");
      try {
        const resp = await api.get("/api/v1/auth/me/provider-config");
        const dataProviders = (resp.data?.providers ?? {}) as Record<string, ProviderConfig>;
        setProviders(dataProviders);
        setActiveProvider(resp.data?.settings?.active_provider ?? "ollama");
      } catch {
        setErrorMsg("Failed to load provider configuration.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const saveAllProviders = async (nextProviders: Record<string, ProviderConfig>, preferredProvider = activeProvider) => {
    const provider_api_keys: Record<string, string | null> = {};
    const provider_settings: Record<string, Record<string, unknown>> = {};
    for (const [providerId, cfg] of Object.entries(nextProviders)) {
      const key = (cfg.api_key ?? "").trim();
      provider_api_keys[providerId] = !key || key === PLACEHOLDER_KEY ? null : key;
      provider_settings[providerId] = {
        default_model: cfg.default_model ?? "",
        base_url: cfg.base_url ?? "",
        model_path: "",
        runtime_options: {},
      };
    }
    await api.patch("/api/v1/auth/me/api-keys", { provider_api_keys, provider_settings });
    await api.patch("/api/v1/auth/me", { preferred_llm_provider: preferredProvider });
    await fetchMe();
  };

  const saveProvider = async (providerId: string) => {
    setSavingProvider(providerId);
    setStatusMsg("");
    setErrorMsg("");
    try {
      await saveAllProviders(providers, activeProvider);
      setStatusMsg(`${providerId} saved.`);
    } catch {
      setErrorMsg(`Failed to save ${providerId}.`);
    } finally {
      setSavingProvider("");
    }
  };

  const testProvider = async (providerId: string) => {
    setTestingProvider(providerId);
    setStatusMsg("");
    setErrorMsg("");
    try {
      await saveAllProviders(providers, activeProvider);
      const resp = await api.post("/api/v1/auth/me/api-keys/test", { provider: providerId });
      if (resp.data?.valid) {
        setStatusMsg(`✓ ${providerId}: connection verified.`);
      } else {
        setErrorMsg(`✗ ${providerId}: ${resp.data?.error ?? "validation failed"}`);
      }
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : `Failed to test ${providerId}.`);
    } finally {
      setTestingProvider("");
    }
  };

  const testAll = async () => {
    for (const providerId of Object.keys(providers)) {
      // eslint-disable-next-line no-await-in-loop
      await testProvider(providerId);
    }
  };

  return (
    <div className="container mx-auto max-w-5xl py-10 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">API Keys</h1>
          <p className="text-muted-foreground mt-2">
            Provider status, key management, and model preferences.
          </p>
        </div>
        <Button variant="outline" onClick={() => void testAll()} disabled={Boolean(testingProvider) || loading}>
          <RefreshCw className="h-4 w-4" />
          Test All
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-lg border bg-card p-4">
            <label className="text-xs text-muted-foreground">Preferred LLM Model Provider</label>
            <Select
              value={activeProvider}
              onValueChange={async (v) => {
                setActiveProvider(v);
                await api.patch("/api/v1/auth/me", { preferred_llm_provider: v });
                await fetchMe();
              }}
            >
              <SelectTrigger className="mt-2 max-w-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.keys(providers).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-3">
            {Object.entries(providers).map(([providerId, cfg]) => (
              <div key={providerId} className="rounded-lg border bg-card p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-semibold capitalize">{providerId}</p>
                    <p className="text-xs text-muted-foreground">
                      {cfg.api_key ? "✓ configured" : "not set"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={Boolean(testingProvider)} onClick={() => void testProvider(providerId)}>
                      {testingProvider === providerId ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                      Test
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setProviders((p) => ({ ...p, [providerId]: { ...p[providerId], api_key: "" } }))}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Delete
                    </Button>
                  </div>
                </div>
                <div className="mt-3 grid gap-2 md:grid-cols-3">
                  <Input
                    type="password"
                    value={cfg.api_key || PLACEHOLDER_KEY}
                    onChange={(e) => setProviders((p) => ({ ...p, [providerId]: { ...p[providerId], api_key: e.target.value } }))}
                    placeholder="API key"
                  />
                  <Input
                    value={cfg.default_model ?? ""}
                    onChange={(e) => setProviders((p) => ({ ...p, [providerId]: { ...p[providerId], default_model: e.target.value } }))}
                    placeholder="default model"
                  />
                  <Input
                    value={cfg.base_url ?? ""}
                    onChange={(e) => setProviders((p) => ({ ...p, [providerId]: { ...p[providerId], base_url: e.target.value } }))}
                    placeholder="base URL (optional)"
                  />
                </div>
                <div className="mt-2">
                  <Button size="sm" onClick={() => void saveProvider(providerId)} disabled={savingProvider === providerId}>
                    {savingProvider === providerId ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    Save
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border bg-card p-4">
            <p className="text-sm font-semibold">Add key</p>
            <div className="mt-2 grid gap-2 md:grid-cols-3">
              <Input value={newProvider} onChange={(e) => setNewProvider(e.target.value)} placeholder="Provider (e.g. openai)" />
              <Input type="password" value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="API key" />
              <Button
                onClick={() => {
                  if (!newProvider.trim()) return;
                  setProviders((prev) => ({
                    ...prev,
                    [newProvider.trim()]: {
                      api_key: newKey.trim(),
                      default_model: prev[newProvider.trim()]?.default_model ?? "",
                      base_url: prev[newProvider.trim()]?.base_url ?? "",
                    },
                  }));
                  setNewProvider("");
                  setNewKey("");
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </Button>
            </div>
          </div>

          {statusMsg ? <div className="rounded-md bg-green-500/15 p-3 text-sm text-green-500 border border-green-500/20">{statusMsg}</div> : null}
          {errorMsg ? <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive border border-destructive/20">{errorMsg}</div> : null}
        </div>
      )}
    </div>
  );
}
