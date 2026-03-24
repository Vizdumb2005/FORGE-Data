import api from "@/lib/api";
import type { MlflowExperiment, MlflowRun, RegistryModel } from "@/types";

export async function listWorkspaceExperiments(workspaceId: string): Promise<MlflowExperiment[]> {
  const { data } = await api.get<MlflowExperiment[]>(
    `/api/v1/experiments/workspaces/${workspaceId}/experiments`,
  );
  return data;
}

export async function createWorkspaceExperiment(
  workspaceId: string,
  name: string,
): Promise<{ experiment_id: string }> {
  const { data } = await api.post<{ experiment_id: string }>(
    `/api/v1/experiments/workspaces/${workspaceId}/experiments`,
    { name },
  );
  return data;
}

export async function listExperimentRuns(
  workspaceId: string,
  experimentId: string,
): Promise<MlflowRun[]> {
  const { data } = await api.get<MlflowRun[]>(
    `/api/v1/experiments/workspaces/${workspaceId}/experiments/${experimentId}/runs`,
  );
  return data;
}

export async function compareRuns(
  workspaceId: string,
  experimentId: string,
  runIds: string[],
): Promise<{
  run_ids: string[];
  params: Record<string, Record<string, string | null>>;
  metrics: Record<string, Record<string, number | null>>;
}> {
  const { data } = await api.get(
    `/api/v1/experiments/workspaces/${workspaceId}/experiments/${experimentId}/runs/compare`,
    { params: { run_ids: runIds.join(",") } },
  );
  return data;
}

export async function deployRunModel(
  workspaceId: string,
  experimentId: string,
  runId: string,
  modelName: string,
): Promise<{ model_uri: string; stage: string; model_name: string }> {
  const { data } = await api.post(
    `/api/v1/experiments/workspaces/${workspaceId}/experiments/${experimentId}/runs/${runId}/deploy`,
    { model_name: modelName },
  );
  return data;
}

export async function listRegistryModels(workspaceId: string): Promise<RegistryModel[]> {
  const { data } = await api.get<RegistryModel[]>(
    `/api/v1/experiments/workspaces/${workspaceId}/models`,
  );
  return data;
}

