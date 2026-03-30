"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Plus, Sparkles } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import TemplateGallery from "@/components/automation/TemplateGallery";
import {
  createFromTemplate,
  createWorkflow,
  listAutomationRunHistory,
  listWorkflows,
} from "@/lib/api/automation";
import type { AutomationRunSummary, AutomationWorkflow } from "@/types";

const STATUS_COLORS: Record<string, string> = {
  success: "bg-green-400",
  failed: "bg-red-400",
  running: "bg-yellow-400",
  never: "bg-forge-muted",
};

export default function AutomationPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [workflows, setWorkflows] = useState<AutomationWorkflow[]>([]);
  const [runHistory, setRunHistory] = useState<AutomationRunSummary[]>([]);
  const [templateOpen, setTemplateOpen] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      const [wf, history] = await Promise.all([listWorkflows(), listAutomationRunHistory()]);
      setWorkflows(wf);
      setRunHistory(history);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const groupedHistory = useMemo(() => runHistory.slice(0, 12), [runHistory]);

  return (
    <div className="mx-auto max-w-7xl p-6">
      <TemplateGallery
        open={templateOpen}
        onClose={() => setTemplateOpen(false)}
        onSelect={async (templateId, name, config) => {
          const created = await createFromTemplate({ template_id: templateId, name, config });
          router.push(`/automation/${created.id}`);
        }}
      />

      <div className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Orion Automation</h1>
          <p className="mt-1 text-sm text-forge-muted">Mission control for real-time workflows.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setTemplateOpen(true)}
            className="border-[#f97316]/40 text-[#f97316] hover:bg-[#f97316]/10"
          >
            <Sparkles className="h-4 w-4" />
            From Template
          </Button>
          <Button
            className="bg-[#f97316] text-black hover:bg-[#ea580c]"
            onClick={async () => {
              const created = await createWorkflow({ name: `Workflow ${Date.now().toString().slice(-5)}` });
              router.push(`/automation/${created.id}`);
            }}
          >
            <Plus className="h-4 w-4" />
            New Workflow
          </Button>
        </div>
      </div>

      <Tabs defaultValue="workflows" className="w-full">
        <TabsList className="bg-forge-surface">
          <TabsTrigger value="workflows">My Workflows</TabsTrigger>
          <TabsTrigger value="history">Run History</TabsTrigger>
        </TabsList>

        <TabsContent value="workflows" className="mt-4">
          {loading ? (
            <div className="text-sm text-forge-muted">Loading workflows...</div>
          ) : workflows.length === 0 ? (
            <div className="rounded-xl border border-dashed border-forge-border bg-forge-surface p-10 text-center">
              <p className="text-sm text-forge-muted">No workflows yet.</p>
              <Button
                className="mt-4 bg-[#f97316] text-black hover:bg-[#ea580c]"
                onClick={async () => {
                  const created = await createWorkflow({ name: `Workflow ${Date.now().toString().slice(-5)}` });
                  router.push(`/automation/${created.id}`);
                }}
              >
                <Plus className="h-4 w-4" />
                Create your first workflow
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {workflows.map((wf) => (
                <Link
                  key={wf.id}
                  href={`/automation/${wf.id}`}
                  className="rounded-xl border border-forge-border bg-forge-surface p-4 transition hover:border-[#f97316]/60"
                >
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-foreground">{wf.name}</p>
                    <span className={`h-2.5 w-2.5 rounded-full ${STATUS_COLORS[wf.last_run_status] ?? STATUS_COLORS.never}`} />
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs text-forge-muted">
                    <Badge variant="secondary">{wf.trigger_label ?? "manual"}</Badge>
                    <span>{wf.run_count} runs</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-4">
          <div className="space-y-2">
            {groupedHistory.map((run) => (
              <div key={run.run_id} className="rounded-md border border-forge-border bg-forge-surface p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs">{run.run_id}</span>
                  <Badge variant={run.status === "success" ? "success" : run.status === "failed" ? "destructive" : "warning"}>
                    {run.status}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-forge-muted">
                  by {run.triggered_by ?? "system"} • {run.started_at ? new Date(run.started_at).toLocaleString() : "-"}
                </p>
              </div>
            ))}
            {groupedHistory.length === 0 && (
              <p className="text-sm text-forge-muted">No run history yet.</p>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
