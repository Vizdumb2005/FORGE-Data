"use client";

import type { AutomationNodeType } from "@/types";
import { setDraggedNodeType } from "@/lib/automation/dnd";

type PaletteItem = {
  type: AutomationNodeType;
  label: string;
  emoji: string;
};

const GROUPS: Array<{ title: string; items: PaletteItem[] }> = [
  {
    title: "Data",
    items: [
      { type: "code_cell", label: "Code Cell", emoji: "🧮" },
      { type: "sql_query", label: "SQL Query", emoji: "🗄️" },
      { type: "upload_dataset", label: "Upload Dataset", emoji: "📤" },
    ],
  },
  {
    title: "Control",
    items: [
      { type: "trigger", label: "Trigger", emoji: "⚡" },
      { type: "conditional", label: "Conditional", emoji: "🔀" },
      { type: "wait", label: "Wait", emoji: "⏱️" },
    ],
  },
  {
    title: "Actions",
    items: [
      { type: "email_notify", label: "Email", emoji: "📧" },
      { type: "api_call", label: "API Call", emoji: "🌐" },
      { type: "retrain", label: "Retrain", emoji: "🔬" },
      { type: "publish_dashboard", label: "Publish Dashboard", emoji: "📊" },
    ],
  },
  {
    title: "Quant & Markets",
    items: [
      { type: "fetch_market_data", label: "Market Data", emoji: "📈" },
      { type: "calc_indicators", label: "Technical Indicators", emoji: "📉" },
      { type: "backtest", label: "Run Backtest", emoji: "🧪" },
    ],
  },
  {
    title: "Execution & State",
    items: [
      { type: "broker_order", label: "Broker Order", emoji: "💸" },
      { type: "portfolio_rebalance", label: "Rebalance", emoji: "⚖️" },
      { type: "get_state", label: "Get State", emoji: "💾" },
      { type: "set_state", label: "Set State", emoji: "📝" },
      { type: "loop_start", label: "Loop Array", emoji: "🔁" },
    ],
  },
];

interface NodePaletteProps {
  className?: string;
}

export default function NodePalette({ className }: NodePaletteProps) {
  return (
    <aside
      className={[
        "h-full w-[220px] border-r border-forge-border bg-[#0a0c10] p-3",
        className ?? "",
      ].join(" ")}
    >
      <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-forge-muted">
        Node Palette
      </p>
      <div className="space-y-4">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-forge-muted/80">
              {group.title}
            </h3>
            <div className="space-y-2">
              {group.items.map((item) => (
                <div
                  key={item.type}
                  draggable
                  onDragStart={(e) => {
                    setDraggedNodeType(item.type);
                    e.dataTransfer.setData("application/forge-node-type", item.type);
                    e.dataTransfer.setData("text/plain", item.type);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  className="cursor-grab rounded-md border border-forge-border bg-forge-surface px-2.5 py-2 text-xs text-foreground transition hover:border-[#f97316]/50 hover:bg-[#1a1f2b]"
                >
                  <span className="mr-2">{item.emoji}</span>
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </aside>
  );
}
