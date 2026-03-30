"use client";

import { useMemo, useState } from "react";
import { FlaskConical, Loader2, Play } from "lucide-react";
import api from "@/lib/api";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Dataset } from "@/types";

interface StatAdvisorPanelProps {
  workspaceId: string;
  datasets: Dataset[];
  onClose: () => void;
}

interface StatResult {
  test_name: string;
  assumptions: string[] | string;
  rationale: string;
  code: string;
  interpretation: string;
}

export default function StatAdvisorPanel({ workspaceId, datasets, onClose }: StatAdvisorPanelProps) {
  const { createCell, setActiveCellId } = useWorkspaceStore();
  const [datasetId, setDatasetId] = useState<string>(datasets[0]?.id ?? "");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<StatResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);

  const assumptionList = useMemo(() => {
    if (!result) return [];
    return Array.isArray(result.assumptions)
      ? result.assumptions
      : result.assumptions
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
  }, [result]);

  const runAdvisor = async () => {
    if (!datasetId || !question.trim()) return;
    setLoading(true);
    try {
      const { data } = await api.post<StatResult>(
        `/api/v1/ai/workspaces/${workspaceId}/stat-advisor`,
        {
          dataset_id: datasetId,
          question: question.trim(),
        },
      );
      setResult(data);
    } finally {
      setLoading(false);
    }
  };

  const runThisTest = async () => {
    if (!result?.code) return;
    setRunning(true);
    try {
      const created = await createCell(workspaceId, {
        cell_type: "code",
        language: "python",
        content: result.code,
        position_x: 60,
        position_y: 9_999_999,
      });
      setActiveCellId(created.id);
      await api.post(`/api/v1/workspaces/${workspaceId}/cells/${created.id}/run`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex h-full flex-col border-l border-forge-border bg-forge-surface">
      <div className="flex items-center justify-between border-b border-forge-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="h-4 w-4 text-forge-accent" />
          Statistical Advisor
        </div>
        <button onClick={onClose} className="text-xs text-forge-muted hover:text-foreground">
          Close
        </button>
      </div>

      <div className="space-y-3 p-3">
        <Select value={datasetId} onValueChange={setDatasetId}>
          <SelectTrigger className="bg-forge-bg">
            <SelectValue placeholder="Select dataset" />
          </SelectTrigger>
          <SelectContent>
            {datasets.map((d) => (
              <SelectItem key={d.id} value={d.id}>
                {d.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What hypothesis do you want to test?"
          className="min-h-[100px] bg-forge-bg"
        />
        <Button onClick={runAdvisor} disabled={loading || !datasetId || !question.trim()}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Get Recommendation"}
        </Button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto border-t border-forge-border p-3">
        {!result && <p className="text-xs text-forge-muted">Submit a question to get a test recommendation.</p>}
        {result && (
          <>
            <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
              <p className="text-[11px] uppercase tracking-wider text-forge-muted">Recommended test</p>
              <p className="mt-1 text-lg font-semibold text-foreground">{result.test_name}</p>
            </div>

            <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
              <p className="mb-2 text-[11px] uppercase tracking-wider text-forge-muted">Assumptions</p>
              <ul className="space-y-1 text-sm">
                {assumptionList.map((a) => (
                  <li key={a} className="flex items-start gap-2">
                    <span className="mt-0.5 text-green-400">✓</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-lg border border-forge-border bg-forge-bg p-3 text-sm text-foreground">
              <p className="mb-1 text-[11px] uppercase tracking-wider text-forge-muted">Rationale</p>
              {result.rationale}
            </div>

            <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
              <p className="mb-2 text-[11px] uppercase tracking-wider text-forge-muted">Code</p>
              <pre className="max-h-64 overflow-auto rounded-md border border-forge-border bg-[#0f172a] p-2 text-xs text-slate-100">
                <code>{result.code}</code>
              </pre>
              <Button className="mt-2" onClick={runThisTest} disabled={running}>
                {running ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Play className="h-4 w-4" />
                    Run this test
                  </>
                )}
              </Button>
            </div>

            <div className="rounded-lg border border-forge-border bg-forge-bg p-3 text-sm text-foreground">
              <p className="mb-1 text-[11px] uppercase tracking-wider text-forge-muted">Interpretation guide</p>
              {result.interpretation}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
