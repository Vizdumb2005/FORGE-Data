"use client";

import dynamic from "next/dynamic";
import type { CellOutput } from "@/types";

// Plotly is SSR-incompatible
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ChartRendererProps {
  output: CellOutput;
}

export default function ChartRenderer({ output }: ChartRendererProps) {
  const { data } = output;

  // Plotly JSON: { data: [...traces], layout: {...} }
  if (data["application/vnd.plotly.v1+json"]) {
    const plotly = data["application/vnd.plotly.v1+json"] as {
      data: Plotly.Data[];
      layout?: Partial<Plotly.Layout>;
    };
    return (
      <Plot
        data={plotly.data}
        layout={{
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { color: "#e2e8f0", size: 11 },
          margin: { t: 24, r: 16, b: 32, l: 40 },
          ...plotly.layout,
        }}
        config={{ responsive: true, displayModeBar: false }}
        style={{ width: "100%", height: 240 }}
      />
    );
  }

  // Plain image/png
  if (data["image/png"]) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={`data:image/png;base64,${data["image/png"]}`}
        alt="chart"
        className="max-w-full rounded"
      />
    );
  }

  // text/html (for Vega-Lite or other iframe content)
  if (data["text/html"]) {
    return (
      <div
        className="text-sm text-foreground"
        dangerouslySetInnerHTML={{ __html: data["text/html"] as string }}
      />
    );
  }

  // Fallback: display raw JSON
  return (
    <pre className="overflow-auto rounded bg-forge-bg p-2 font-mono text-xs text-forge-muted">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
