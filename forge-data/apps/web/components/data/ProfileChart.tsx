"use client";

import dynamic from "next/dynamic";
import type { ColumnProfile } from "@/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const NUMERIC_TYPES = new Set([
  "int64",
  "float64",
  "int32",
  "float32",
  "INTEGER",
  "BIGINT",
  "FLOAT",
  "DOUBLE",
  "DECIMAL",
  "NUMERIC",
  "REAL",
  "SMALLINT",
  "TINYINT",
]);

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#94a3b8", family: "DM Mono, monospace", size: 11 },
  margin: { t: 28, b: 32, l: 44, r: 12 },
  xaxis: {
    gridcolor: "#1e2433",
    zerolinecolor: "#1e2433",
  },
  yaxis: {
    gridcolor: "#1e2433",
    zerolinecolor: "#1e2433",
  },
};

interface ProfileChartProps {
  column: ColumnProfile;
  totalRows: number;
}

export default function ProfileChart({ column, totalRows }: ProfileChartProps) {
  const isNumeric = NUMERIC_TYPES.has(column.dtype.split("(")[0]);
  const nullPct =
    totalRows > 0 ? ((column.null_count / totalRows) * 100).toFixed(1) : "0";

  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
      <div className="mb-2 flex items-center justify-between">
        <h4 className="font-mono text-xs font-semibold text-foreground">
          {column.name}
        </h4>
        <span className="font-mono text-[10px] text-forge-muted">
          {column.dtype}
        </span>
      </div>

      {/* Stats row */}
      <div className="mb-3 flex gap-4 font-mono text-[10px] text-forge-muted">
        <span>
          Distinct:{" "}
          <span className="text-foreground">{column.distinct_count.toLocaleString()}</span>
        </span>
        <span>
          Nulls:{" "}
          <span className={column.null_count > 0 ? "text-yellow-400" : "text-foreground"}>
            {nullPct}%
          </span>
        </span>
        {isNumeric && column.avg != null && (
          <span>
            Mean: <span className="text-foreground">{column.avg.toFixed(2)}</span>
          </span>
        )}
        {column.min != null && (
          <span>
            Min: <span className="text-foreground">{String(column.min)}</span>
          </span>
        )}
        {column.max != null && (
          <span>
            Max: <span className="text-foreground">{String(column.max)}</span>
          </span>
        )}
      </div>

      {/* Chart */}
      {isNumeric && column.sample_values && column.sample_values.length > 0 ? (
        <NumericChart column={column} />
      ) : column.sample_values && column.sample_values.length > 0 ? (
        <CategoricalChart column={column} />
      ) : (
        <div className="flex h-24 items-center justify-center text-xs text-forge-muted">
          No sample data available
        </div>
      )}
    </div>
  );
}

function NumericChart({ column }: { column: ColumnProfile }) {
  const values = (column.sample_values || [])
    .map(Number)
    .filter((v) => !isNaN(v));
  if (values.length === 0) return null;

  return (
    <Plot
      data={[
        {
          x: values,
          type: "histogram" as const,
          marker: { color: "#00e5ff", opacity: 0.7 },
          nbinsx: Math.min(20, values.length),
        } as Partial<Plotly.PlotData> & { nbinsx: number },
      ]}
      layout={{
        ...DARK_LAYOUT,
        height: 120,
        xaxis: { ...DARK_LAYOUT.xaxis, title: undefined },
        yaxis: { ...DARK_LAYOUT.yaxis, title: undefined },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: 120 }}
    />
  );
}

function CategoricalChart({ column }: { column: ColumnProfile }) {
  const values = (column.sample_values || []).map(String).slice(0, 10);
  const labels = values;
  const counts = values.map(() => 1); // sample values don't have counts, show presence

  return (
    <Plot
      data={[
        {
          x: counts,
          y: labels,
          type: "bar",
          orientation: "h",
          marker: { color: "#00e5ff", opacity: 0.7 },
        },
      ]}
      layout={{
        ...DARK_LAYOUT,
        height: Math.max(80, values.length * 20),
        xaxis: { ...DARK_LAYOUT.xaxis, visible: false },
        yaxis: { ...DARK_LAYOUT.yaxis, automargin: true },
      }}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: Math.max(80, values.length * 20) }}
    />
  );
}
