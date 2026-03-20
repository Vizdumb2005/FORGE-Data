"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, Loader2, Play } from "lucide-react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

interface PipelineBuilderProps {
  workspaceId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface TimelineEvent {
  type: string;
  [key: string]: unknown;
}

interface PipelineRunSummary {
  id: string;
  status: string;
  goal: string;
  created_at: string;
}

const EXAMPLES = [
  "Find the strongest churn drivers and summarize actions",
  "Identify weekly revenue trends and anomalies",
  "Segment customers and compare retention behavior",
];

export default function PipelineBuilder({ workspaceId, open, onOpenChange }: PipelineBuilderProps) {
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [history, setHistory] = useState<PipelineRunSummary[]>([]);
  const [finalReport, setFinalReport] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const canRun = goal.trim().length > 0 && !running;

  const groupedSteps = useMemo(
    () => events.filter((e) => ["step_start", "step_complete", "output", "code"].includes(e.type)),
    [events],
  );

  useEffect(() => {
    if (!open) return;
    void loadHistory();
  }, [open, workspaceId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events, finalReport]);

  const loadHistory = async () => {
    const { data } = await api.get<PipelineRunSummary[]>(`/api/v1/ai/workspaces/${workspaceId}/pipelines`);
    setHistory(data);
  };

  const runPipeline = async () => {
    if (!canRun) return;
    setRunning(true);
    setEvents([]);
    setFinalReport("");
    try {
      const resp = await fetch(`/api/v1/ai/workspaces/${workspaceId}/pipelines/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal }),
      });
      if (!resp.ok || !resp.body) throw new Error("Failed to run pipeline");

      const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += value;
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const raw = line.replace(/^data:\s*/, "");
          if (!raw) continue;
          try {
            const event = JSON.parse(raw) as TimelineEvent;
            setEvents((prev) => [...prev, event]);
            if (event.type === "complete" && typeof event.full_report === "string") {
              setFinalReport(event.full_report);
            }
          } catch {
            // ignore malformed line
          }
        }
      }
      await loadHistory();
    } finally {
      setRunning(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[720px] max-w-[95vw] p-0">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-forge-accent" />
            Pipeline Builder
          </SheetTitle>
          <SheetDescription>Describe your analysis goal and run an agentic pipeline.</SheetDescription>
        </SheetHeader>

        <div className="space-y-3 border-b border-forge-border p-4">
          <Textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Describe your analysis goal..."
            className="min-h-[110px] bg-forge-bg"
          />
          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setGoal(ex)}
                className="rounded-full border border-forge-border bg-forge-bg px-2.5 py-1 text-[11px] text-forge-muted hover:text-forge-accent"
              >
                {ex}
              </button>
            ))}
          </div>
          <Button onClick={runPipeline} disabled={!canRun}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run Pipeline
          </Button>
        </div>

        <div className="grid h-[calc(100vh-220px)] grid-cols-2 gap-0">
          <div className="border-r border-forge-border">
            <div className="border-b border-forge-border px-3 py-2 text-xs font-semibold uppercase text-forge-muted">
              Live execution
            </div>
            <ScrollArea className="h-full p-3">
              <div className="space-y-2">
                {groupedSteps.map((event, idx) => (
                  <div key={`${event.type}-${idx}`} className="rounded-md border border-forge-border bg-forge-bg p-2">
                    <p className="text-xs font-medium text-foreground">{String(event.type)}</p>
                    <pre className="mt-1 whitespace-pre-wrap text-[11px] text-forge-muted">
                      {JSON.stringify(event, null, 2)}
                    </pre>
                  </div>
                ))}
                {finalReport && (
                  <div className="rounded-md border border-green-500/30 bg-green-900/10 p-2">
                    <p className="text-xs font-semibold text-green-300">Final report</p>
                    <p className="mt-1 whitespace-pre-wrap text-sm text-foreground">{finalReport}</p>
                  </div>
                )}
                <div ref={endRef} />
              </div>
            </ScrollArea>
          </div>

          <div>
            <div className="border-b border-forge-border px-3 py-2 text-xs font-semibold uppercase text-forge-muted">
              History
            </div>
            <ScrollArea className="h-full p-3">
              <div className="space-y-2">
                {history.map((run) => (
                  <div key={run.id} className="rounded-md border border-forge-border bg-forge-bg p-2">
                    <p className="line-clamp-2 text-sm text-foreground">{run.goal}</p>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-forge-muted">
                      <span>{run.status}</span>
                      <span>{new Date(run.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}
