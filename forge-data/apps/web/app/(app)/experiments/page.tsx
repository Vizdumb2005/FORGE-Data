"use client";

import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Plus } from "lucide-react";
import { useWorkspace } from "@/lib/hooks/useWorkspace";
import { useToast } from "@/components/ui/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  createWorkspaceExperiment,
  deployRunModel,
  listExperimentRuns,
  listRegistryModels,
  listWorkspaceExperiments,
  compareRuns,
} from "@/lib/api/experiments";
import type { MlflowExperiment, MlflowRun, RegistryModel } from "@/types";
import RunDetailPanel from "@/components/experiments/RunDetailPanel";
import RunComparisonView from "@/components/experiments/RunComparisonView";
import ModelRegistry from "@/components/experiments/ModelRegistry";
import RunsTable from "@/components/experiments/RunsTable";

export default function ExperimentsPage() {
  const { workspaces } = useWorkspace();
  const { toast } = useToast();
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [experiments, setExperiments] = useState<MlflowExperiment[]>([]);
  const [selectedExpId, setSelectedExpId] = useState<string>("");
  const [runs, setRuns] = useState<MlflowRun[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<Set<string>>(new Set());
  const [activeRun, setActiveRun] = useState<MlflowRun | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [newExperimentName, setNewExperimentName] = useState("");
  const [compareData, setCompareData] = useState<{
    run_ids: string[];
    params: Record<string, Record<string, string | null>>;
    metrics: Record<string, Record<string, number | null>>;
  } | null>(null);
  const [models, setModels] = useState<RegistryModel[]>([]);

  useEffect(() => {
    if (workspaces.length && !workspaceId) setWorkspaceId(workspaces[0].id);
  }, [workspaces, workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    void (async () => {
      try {
        const [exp, reg] = await Promise.all([
          listWorkspaceExperiments(workspaceId),
          listRegistryModels(workspaceId),
        ]);
        setExperiments(exp);
        setModels(reg);
        if (exp.length > 0) setSelectedExpId((prev) => prev || exp[0].experiment_id);
      } catch {
        toast({ title: "Failed loading experiments", variant: "destructive" });
      }
    })();
  }, [workspaceId, toast]);

  useEffect(() => {
    if (!workspaceId || !selectedExpId) return;
    void (async () => {
      try {
        const data = await listExperimentRuns(workspaceId, selectedExpId);
        setRuns(data);
      } catch {
        setRuns([]);
      }
    })();
  }, [workspaceId, selectedExpId]);

  const createExperiment = async () => {
    if (!workspaceId || !newExperimentName.trim()) return;
    try {
      await createWorkspaceExperiment(workspaceId, newExperimentName.trim());
      const exp = await listWorkspaceExperiments(workspaceId);
      setExperiments(exp);
      setNewExperimentName("");
      toast({ title: "Experiment created" });
    } catch {
      toast({ title: "Failed to create experiment", variant: "destructive" });
    }
  };

  const toggleRun = (runId: string) => {
    const next = new Set(selectedRunIds);
    if (next.has(runId)) next.delete(runId);
    else next.add(runId);
    setSelectedRunIds(next);
  };

  const openRun = (run: MlflowRun) => {
    setActiveRun(run);
    setDetailOpen(true);
  };

  const doCompare = async () => {
    if (!workspaceId || !selectedExpId || selectedRunIds.size < 2) return;
    try {
      const data = await compareRuns(workspaceId, selectedExpId, Array.from(selectedRunIds));
      setCompareData(data);
    } catch {
      toast({ title: "Failed comparing runs", variant: "destructive" });
    }
  };

  const deploy = async (modelName: string) => {
    if (!workspaceId || !selectedExpId || !activeRun) return;
    try {
      await deployRunModel(workspaceId, selectedExpId, activeRun.run_id, modelName);
      setModels(await listRegistryModels(workspaceId));
      toast({ title: "Model deployed" });
    } catch {
      toast({ title: "Deployment failed", variant: "destructive" });
    }
  };

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <FlaskConical className="h-6 w-6 text-forge-accent" />
            Experiments
          </h1>
          <p className="mt-1 text-sm text-forge-muted">
            Lightweight MLflow-like tracking, comparison, model registry, and deployment.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={newExperimentName}
            onChange={(e) => setNewExperimentName(e.target.value)}
            placeholder="classification"
            className="w-52"
          />
          <Button onClick={createExperiment}>
            <Plus className="h-4 w-4" />
            New Experiment
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        <aside className="col-span-3 rounded border border-forge-border bg-forge-surface p-2">
          <h2 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-forge-muted">
            Experiments
          </h2>
          <div className="space-y-1">
            {experiments.map((exp) => (
              <button
                key={exp.experiment_id}
                onClick={() => {
                  setSelectedExpId(exp.experiment_id);
                  setCompareData(null);
                  setSelectedRunIds(new Set());
                }}
                className={`w-full rounded px-2 py-2 text-left text-sm ${
                  selectedExpId === exp.experiment_id ? "bg-forge-accent/20 text-foreground" : "hover:bg-forge-border/40"
                }`}
              >
                {exp.name}
              </button>
            ))}
          </div>
        </aside>

        <main className="col-span-9 space-y-4">
          {compareData ? (
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold">Run Comparison</h2>
                <Button variant="outline" onClick={() => setCompareData(null)}>Back to runs</Button>
              </div>
              <RunComparisonView
                runIds={compareData.run_ids}
                params={compareData.params}
                metrics={compareData.metrics}
              />
            </div>
          ) : (
            <div className="rounded border border-forge-border bg-forge-surface p-3">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold">Runs</h2>
                {selectedRunIds.size > 1 ? (
                  <Button size="sm" onClick={doCompare}>Compare Selected</Button>
                ) : null}
              </div>
              <RunsTable
                runs={runs}
                selectedRunIds={selectedRunIds}
                onToggleRun={toggleRun}
                onRowClick={openRun}
              />
            </div>
          )}

          <ModelRegistry models={models} />
        </main>
      </div>

      <RunDetailPanel open={detailOpen} onOpenChange={setDetailOpen} run={activeRun} onDeploy={deploy} />
    </div>
  );
}

