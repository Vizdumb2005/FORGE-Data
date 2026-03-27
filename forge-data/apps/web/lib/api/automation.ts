import api from "@/lib/api";
import type {
  AutomationEdge,
  AutomationNode,
  AutomationNodeExecution,
  AutomationNodeType,
  AutomationRun,
  AutomationRunSummary,
  AutomationWorkflow,
  AutomationWorkflowStatus,
  Workspace,
} from "@/types";

const BASE = "/api/v1/workspaces";

export interface CreateWorkflowPayload {
  name: string;
  description?: string;
}

export interface UpdateWorkflowPayload {
  name?: string;
  is_active?: boolean;
}

export interface CreateNodePayload {
  type: AutomationNodeType;
  label?: string;
  position_x: number;
  position_y: number;
  config?: Record<string, unknown>;
}

export interface UpdateNodePayload {
  label?: string;
  position_x?: number;
  position_y?: number;
  retry_count?: number;
  timeout_seconds?: number;
  on_failure?: "stop" | "continue" | "branch";
  config?: Record<string, unknown>;
}

export interface CreateFromTemplatePayload {
  template_id: string;
  name: string;
  config: Record<string, unknown>;
}

type WorkflowDetailResponse = {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  trigger_type: string;
  created_at: string;
  updated_at: string;
  nodes: Array<{
    id: string;
    workflow_id: string;
    node_type: string;
    label: string;
    config: Record<string, unknown>;
    position_x: number;
    position_y: number;
    retry_count: number;
    timeout_seconds: number;
    on_failure_node_id?: string | null;
  }>;
  edges: Array<{
    id: string;
    workflow_id: string;
    source_node_id: string;
    target_node_id: string;
    condition: "always" | "on_success" | "on_failure";
  }>;
  recent_runs: Array<{ status: string }>;
  run_count?: number;
  last_run_status?: string | null;
};

type WorkflowRunResponse = {
  id: string;
  workflow_id: string;
  status: string;
  triggered_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  node_runs?: Array<{
    node_id: string;
    status: string;
    started_at: string | null;
    finished_at: string | null;
    logs: string | null;
  }>;
};

let workspaceIdCache: string | null = null;

async function resolveWorkspaceId(): Promise<string> {
  if (workspaceIdCache) return workspaceIdCache;
  const { data } = await api.get<Workspace[]>("/api/v1/workspaces");
  if (!data.length) throw new Error("No workspace available");
  workspaceIdCache = data[0].id;
  return workspaceIdCache;
}

function normalizeNodeType(nodeType: string): AutomationNodeType {
  if (nodeType === "dataset_upload") return "upload_dataset";
  if (nodeType === "model_retrain") return "retrain";
  if (nodeType === "dashboard_publish") return "publish_dashboard";
  return nodeType as AutomationNodeType;
}

function toBackendNodeType(nodeType: AutomationNodeType): string {
  if (nodeType === "upload_dataset") return "dataset_upload";
  if (nodeType === "retrain") return "model_retrain";
  if (nodeType === "publish_dashboard") return "dashboard_publish";
  if (nodeType === "trigger") return "wait";
  return nodeType;
}

function toWorkflowStatus(status: string | null | undefined): AutomationWorkflowStatus {
  return deriveWorkflowStatus(status ?? null);
}

function mapWorkflow(wf: WorkflowDetailResponse): AutomationWorkflow {
  const lastStatus = wf.last_run_status ?? wf.recent_runs?.[0]?.status ?? null;
  return {
    id: wf.id,
    name: wf.name,
    is_active: wf.is_active,
    trigger_label: wf.trigger_type ?? "manual",
    last_run_status: toWorkflowStatus(lastStatus),
    run_count: wf.run_count ?? 0,
    created_at: wf.created_at,
    updated_at: wf.updated_at,
  };
}

function mapNode(node: WorkflowDetailResponse["nodes"][number]): AutomationNode {
  return {
    id: node.id,
    workflow_id: node.workflow_id,
    type: normalizeNodeType(node.node_type),
    label: node.label,
    position_x: node.position_x,
    position_y: node.position_y,
    retry_count: node.retry_count,
    timeout_seconds: node.timeout_seconds,
    on_failure: node.on_failure_node_id ? "branch" : "stop",
    config: node.config ?? {},
    created_at: "",
    updated_at: "",
  };
}

function mapEdge(edge: WorkflowDetailResponse["edges"][number]): AutomationEdge {
  return {
    id: edge.id,
    workflow_id: edge.workflow_id,
    source_node_id: edge.source_node_id,
    target_node_id: edge.target_node_id,
    type: edge.condition,
    created_at: "",
  };
}

function mapRun(run: WorkflowRunResponse): AutomationRunSummary {
  return {
    run_id: run.id,
    workflow_id: run.workflow_id,
    status: (run.status === "pending" ? "queued" : run.status) as AutomationRunSummary["status"],
    triggered_by: run.triggered_by ?? null,
    started_at: run.started_at,
    completed_at: run.finished_at,
    duration_ms:
      run.started_at && run.finished_at
        ? Math.max(0, new Date(run.finished_at).getTime() - new Date(run.started_at).getTime())
        : null,
  };
}

export async function listWorkflows(): Promise<AutomationWorkflow[]> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowDetailResponse[]>(`${BASE}/${workspaceId}/workflows`);
  return data.map(mapWorkflow);
}

export async function getWorkflow(workflowId: string): Promise<AutomationWorkflow> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}`);
  return mapWorkflow({
    ...data,
    run_count: data.recent_runs?.length ?? 0,
    last_run_status: data.recent_runs?.[0]?.status ?? null,
  });
}

export async function createWorkflow(payload: CreateWorkflowPayload): Promise<AutomationWorkflow> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.post<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows`, {
    name: payload.name,
    description: payload.description,
    trigger_type: "manual",
    trigger_config: {},
  });
  return mapWorkflow({ ...data, run_count: 0, last_run_status: null, recent_runs: [] });
}

export async function updateWorkflow(workflowId: string, payload: UpdateWorkflowPayload): Promise<AutomationWorkflow> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.put<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}`, payload);
  return mapWorkflow({ ...data, run_count: 0, last_run_status: null, recent_runs: [] });
}

export async function listWorkflowNodes(workflowId: string): Promise<AutomationNode[]> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}`);
  return (data.nodes ?? []).map(mapNode);
}

export async function listWorkflowEdges(workflowId: string): Promise<AutomationEdge[]> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}`);
  return (data.edges ?? []).map(mapEdge);
}

export async function createWorkflowNode(workflowId: string, payload: CreateNodePayload): Promise<AutomationNode> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.post<WorkflowDetailResponse["nodes"][number]>(
    `${BASE}/${workspaceId}/workflows/${workflowId}/nodes`,
    {
      node_type: toBackendNodeType(payload.type),
      label: payload.label ?? payload.type,
      position_x: payload.position_x,
      position_y: payload.position_y,
      config: payload.config ?? {},
    },
  );
  return mapNode(data);
}

export async function updateWorkflowNode(
  workflowId: string,
  nodeId: string,
  payload: UpdateNodePayload,
): Promise<AutomationNode> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.put<WorkflowDetailResponse["nodes"][number]>(
    `${BASE}/${workspaceId}/workflows/${workflowId}/nodes/${nodeId}`,
    {
      label: payload.label,
      position_x: payload.position_x,
      position_y: payload.position_y,
      retry_count: payload.retry_count,
      timeout_seconds: payload.timeout_seconds,
      config: payload.config,
    },
  );
  return mapNode(data);
}

export async function deleteWorkflowNode(workflowId: string, nodeId: string): Promise<void> {
  const workspaceId = await resolveWorkspaceId();
  await api.delete(`${BASE}/${workspaceId}/workflows/${workflowId}/nodes/${nodeId}`);
}

export async function runWorkflow(workflowId: string): Promise<{ run_id: string }> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.post<WorkflowRunResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}/trigger`, {
    run_metadata: {},
  });
  return { run_id: data.id };
}

export async function listWorkflowRuns(workflowId: string): Promise<AutomationRunSummary[]> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowRunResponse[]>(`${BASE}/${workspaceId}/workflows/${workflowId}/runs`);
  return data.map(mapRun);
}

export async function getWorkflowRun(workflowId: string, runId: string): Promise<AutomationRun> {
  const workspaceId = await resolveWorkspaceId();
  const { data } = await api.get<WorkflowRunResponse>(`${BASE}/${workspaceId}/workflows/${workflowId}/runs/${runId}`);
  const summary = mapRun(data);
  return {
    ...summary,
    nodes: (data.node_runs ?? []).map((n) => ({
      node_id: n.node_id,
      node_label: n.node_id.slice(0, 8),
      status: n.status as AutomationNodeExecution["status"],
      started_at: n.started_at,
      completed_at: n.finished_at,
      duration_ms:
        n.started_at && n.finished_at
          ? Math.max(0, new Date(n.finished_at).getTime() - new Date(n.started_at).getTime())
          : null,
      log: n.logs,
    })),
  };
}

export async function listWorkflowRunNodes(workflowId: string, runId: string): Promise<AutomationNodeExecution[]> {
  const run = await getWorkflowRun(workflowId, runId);
  return run.nodes;
}

export async function cancelWorkflowRun(workflowId: string, runId: string): Promise<void> {
  const workspaceId = await resolveWorkspaceId();
  await api.post(`${BASE}/${workspaceId}/workflows/${workflowId}/runs/${runId}/cancel`);
}

export async function listAutomationRunHistory(): Promise<AutomationRunSummary[]> {
  const workflows = await listWorkflows();
  const runsByWorkflow = await Promise.all(workflows.map((wf) => listWorkflowRuns(wf.id)));
  return runsByWorkflow
    .flat()
    .sort((a, b) => {
      const at = a.started_at ? new Date(a.started_at).getTime() : 0;
      const bt = b.started_at ? new Date(b.started_at).getTime() : 0;
      return bt - at;
    })
    .slice(0, 100);
}

export async function createFromTemplate(payload: CreateFromTemplatePayload): Promise<AutomationWorkflow> {
  const workspaceId = await resolveWorkspaceId();
  const templateKeyMap: Record<string, string> = {
    "daily-drift": "daily_dataset_refresh",
    "retrain-and-publish": "ml_retrain_on_new_data",
    "sql-alert": "data_quality_gate",
    "api-sync": "weekly_dashboard_report",
  };
  const { data } = await api.post<WorkflowDetailResponse>(`${BASE}/${workspaceId}/workflows/from-template`, {
    template_key: templateKeyMap[payload.template_id] ?? payload.template_id,
    name: payload.name,
    config_overrides: payload.config ?? {},
  });
  return mapWorkflow({ ...data, run_count: 0, last_run_status: null, recent_runs: [] });
}

export function deriveWorkflowStatus(runStatus: string | null): AutomationWorkflowStatus {
  if (!runStatus) return "never";
  if (runStatus === "success" || runStatus === "completed") return "success";
  if (runStatus === "failed" || runStatus === "error") return "failed";
  if (runStatus === "running" || runStatus === "queued") return "running";
  return "never";
}
