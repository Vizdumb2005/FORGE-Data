"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Logo } from "@/components/Logo";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import DataGrid from "@/components/data/DataGrid";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import ReactMarkdown from "react-markdown";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface DashboardPayload {
  id: string;
  slug: string;
  title: string;
  workspace_id: string;
  snapshot: Array<{
    id: string;
    cell_type: string;
    language: string;
    content: string;
    output: Record<string, unknown> | null;
  }>;
  last_refreshed_at: string | null;
}

function minutesAgo(iso: string | null) {
  if (!iso) return "unknown";
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  return `${mins} min ago`;
}

export default function PublishedDashboardPage() {
  const { slug } = useParams<{ slug: string }>();
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [password, setPassword] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  const fetchDashboard = async (pwd?: string) => {
    setLoading(true);
    try {
      const query = pwd ? `?password=${encodeURIComponent(pwd)}` : "";
      const res = await fetch(`/api/v1/d/${slug}${query}`, { credentials: "include" });
      if (res.status === 403) {
        setNeedsPassword(true);
        setLoading(false);
        return;
      }
      const data = (await res.json()) as DashboardPayload;
      setDashboard(data);
      setNeedsPassword(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchDashboard();
  }, [slug]);

  useEffect(() => {
    const id = window.setInterval(() => setRefreshTick((v) => v + 1), 60000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!dashboard) return;
    void fetchDashboard(password || undefined);
  }, [refreshTick]);

  const rendered = useMemo(() => dashboard?.snapshot ?? [], [dashboard]);

  return (
    <div className="min-h-screen bg-forge-bg text-foreground">
      <header className="sticky top-0 z-10 border-b border-forge-border bg-forge-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Logo />
          <div className="text-xs text-forge-muted">
            Last updated: {minutesAgo(dashboard?.last_refreshed_at ?? null)} • Auto-refresh enabled
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <h1 className="text-2xl font-semibold">{dashboard?.title ?? "Published Dashboard"}</h1>
        {loading ? <p className="text-sm text-forge-muted">Loading dashboard...</p> : null}
        {rendered.map((cell) => {
          const output = (cell.output ?? {}) as Record<string, unknown>;
          const outputs = (output.outputs as Array<Record<string, unknown>> | undefined) ?? [];
          return (
            <section key={cell.id} className="rounded-lg border border-forge-border bg-forge-surface p-4">
              <div className="mb-2 text-xs uppercase tracking-wider text-forge-muted">
                {cell.cell_type} • {cell.language}
              </div>
              {cell.cell_type === "markdown" ? (
                <div className="prose prose-invert max-w-none">
                  <ReactMarkdown>{cell.content}</ReactMarkdown>
                </div>
              ) : (
                <SyntaxHighlighter language={cell.language || "python"} style={oneDark} customStyle={{ borderRadius: 8 }}>
                  {cell.content}
                </SyntaxHighlighter>
              )}

              <div className="mt-3">
                {outputs.map((evt, i) => {
                  const data = (evt.data as Record<string, unknown> | undefined) ?? {};
                  if (data["application/vnd.plotly.v1+json"]) {
                    const plot = data["application/vnd.plotly.v1+json"] as { data: Plotly.Data[]; layout?: Partial<Plotly.Layout> };
                    return (
                      <Plot
                        key={i}
                        data={plot.data}
                        layout={{
                          ...plot.layout,
                          paper_bgcolor: "transparent",
                          plot_bgcolor: "transparent",
                          font: { color: "#e2e8f0" },
                        }}
                        config={{ responsive: true, scrollZoom: true, displaylogo: false }}
                        style={{ width: "100%", height: 320 }}
                      />
                    );
                  }
                  const appJson = data["application/json"] as { columns?: string[]; rows?: unknown[][] } | undefined;
                  if (appJson?.columns && appJson?.rows) {
                    return <DataGrid key={i} columns={appJson.columns} rows={appJson.rows} maxHeight="320px" />;
                  }
                  if (data["image/png"]) {
                    return (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={i} src={`data:image/png;base64,${String(data["image/png"])}`} alt="chart" className="max-w-full rounded" />
                    );
                  }
                  if (data["text/plain"]) return <pre key={i} className="overflow-auto rounded bg-forge-bg p-2 text-xs">{String(data["text/plain"])}</pre>;
                  if (evt.text) return <pre key={i} className="overflow-auto rounded bg-forge-bg p-2 text-xs">{String(evt.text)}</pre>;
                  return null;
                })}
              </div>
            </section>
          );
        })}
      </main>

      {needsPassword ? (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/70">
          <div className="w-full max-w-sm rounded-lg border border-forge-border bg-forge-surface p-4">
            <h2 className="mb-2 text-lg font-semibold">Password required</h2>
            <p className="mb-3 text-sm text-forge-muted">
              This published dashboard is protected.
            </p>
            <div className="flex items-center gap-2">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <Button onClick={() => void fetchDashboard(password)}>Unlock</Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

