"use client";

import { useAuth } from "@/lib/hooks/useAuth";
import { Settings } from "lucide-react";
import Link from "next/link";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="mb-6 text-2xl font-semibold text-foreground flex items-center gap-2">
        <Settings className="h-6 w-6 text-forge-accent" />
        Settings
      </h1>

      <div className="space-y-4">
        {/* Profile */}
        <section className="rounded-lg border border-forge-border bg-forge-surface p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-forge-muted">
            Profile
          </h2>
          <div className="space-y-3">
            <div>
              <p className="text-xs text-forge-muted">Name</p>
              <p className="text-sm text-foreground">{user?.full_name ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-forge-muted">Email</p>
              <p className="text-sm text-foreground">{user?.email}</p>
            </div>
          </div>
        </section>

        {/* AI API Keys */}
        <section className="rounded-lg border border-forge-border bg-forge-surface p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-forge-muted">
              AI API Keys
            </h2>
            <Link
              href="/settings/api-keys"
              className="text-xs text-forge-accent hover:underline"
            >
              Manage →
            </Link>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-foreground">OpenAI</span>
              <span
                className={
                  user?.has_openai_key
                    ? "text-green-400"
                    : "text-forge-muted"
                }
              >
                {user?.has_openai_key ? "Configured" : "Not set"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-foreground">Anthropic</span>
              <span
                className={
                  user?.has_anthropic_key
                    ? "text-green-400"
                    : "text-forge-muted"
                }
              >
                {user?.has_anthropic_key ? "Configured" : "Not set"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-foreground">Ollama (Local)</span>
              <span
                className={
                  user?.has_ollama_url
                    ? "text-green-400"
                    : "text-forge-muted"
                }
              >
                {user?.has_ollama_url ? "Configured" : "Not set"}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1 border-t border-forge-border/60">
              <span className="text-foreground">Preferred provider</span>
              <span className="text-forge-muted capitalize">
                {user?.preferred_llm_provider ?? "openai"}
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
