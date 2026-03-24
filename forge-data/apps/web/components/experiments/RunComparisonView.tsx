"use client";

import dynamic from "next/dynamic";
import { Badge } from "@/components/ui/badge";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface RunComparisonViewProps {
  runIds: string[];
  params: Record<string, Record<string, string | null>>;
  metrics: Record<string, Record<string, number | null>>;
}

export default function RunComparisonView({ runIds, params, metrics }: RunComparisonViewProps) {
  const metricKeys = Object.keys(metrics);
  const bestRun =
    metricKeys.length > 0
      ? runIds.reduce((best, runId) => {
          const score = metricKeys.reduce((acc, key) => acc + (metrics[key][runId] ?? 0), 0);
          const bestScore = metricKeys.reduce((acc, key) => acc + (metrics[key][best] ?? 0), 0);
          return score > bestScore ? runId : best;
        }, runIds[0])
      : null;

  return (
    <div className="space-y-6">
      <div className="rounded border border-forge-border p-4">
        <h3 className="mb-3 text-sm font-semibold">Selected Runs</h3>
        <div className="flex flex-wrap items-center gap-2">
          {runIds.map((r) => (
            <Badge key={r} variant={r === bestRun ? "warning" : "outline"}>
              {r}
            </Badge>
          ))}
          {bestRun ? <Badge variant="success">Best run: {bestRun}</Badge> : null}
        </div>
      </div>

      <section className="rounded border border-forge-border p-4">
        <h3 className="mb-3 text-sm font-semibold">Params (side-by-side)</h3>
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-forge-muted">
                <th className="py-2">Param</th>
                {runIds.map((run) => (
                  <th key={run} className="py-2">{run}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(params).map(([key, values]) => {
                const unique = new Set(runIds.map((r) => values[r] ?? "—")).size > 1;
                return (
                  <tr key={key} className="border-t border-forge-border/50">
                    <td className="py-2 font-mono">{key}</td>
                    {runIds.map((run) => (
                      <td
                        key={`${key}-${run}`}
                        className={unique ? "bg-amber-500/10 py-2" : "py-2"}
                      >
                        {values[run] ?? "—"}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded border border-forge-border p-4">
        <h3 className="mb-3 text-sm font-semibold">Metrics</h3>
        <Plot
          data={metricKeys.flatMap((metric) =>
            runIds.map((runId) => ({
              x: [0, 1],
              y: [metrics[metric][runId] ?? 0, metrics[metric][runId] ?? 0],
              mode: "lines+markers",
              name: `${metric} (${runId})`,
            })),
          )}
          layout={{
            title: { text: "Metric comparison" },
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            font: { color: "#e2e8f0" },
            autosize: true,
          }}
          config={{ responsive: true, scrollZoom: true, displaylogo: false }}
          style={{ width: "100%", height: 360 }}
        />
        <div className="mt-4 overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-forge-muted">
                <th className="py-2">Metric</th>
                {runIds.map((runId) => (
                  <th key={runId} className="py-2">{runId}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {metricKeys.map((metric) => (
                <tr key={metric} className="border-t border-forge-border/50">
                  <td className="py-2 font-mono">{metric}</td>
                  {runIds.map((runId) => (
                    <td key={`${metric}-${runId}`} className="py-2">
                      {metrics[metric][runId] ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

