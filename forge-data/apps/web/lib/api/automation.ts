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
} from "@/types";

const BASE = "/api/v1/automation";

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

export async function listWorkflows(): Promise<AutomationWorkflow[]> {
  const { data } = await api.get<AutomationWorkflow[]>(`${BASE}/workflows`);
  return data;
}

export async function getWorkflow(workflowId: string): Promise<AutomationWorkflow> {
  const { data } = await api.get<AutomationWorkflow>(`${BASE}/workflows/${workflowId}`);
  return data;
}

export async function createWorkflow(payload: CreateWorkflowPayload): Promise<AutomationWorkflow> {
  const { data } = await api.post<AutomationWorkflow>(`${BASE}/workflows`, payload);
  return data;
}

export async function updateWorkflow(workflowId: string, payload: UpdateWorkflowPayload): Promise<AutomationWorkflow> {
  const { data } = await api.patch<AutomationWorkflow>(`${BASE}/workflows/${workflowId}`, payload);
  return data;
}

export async function listWorkflowNodes(workflowId: string): Promise<AutomationNode[]> {
  const { data } = await api.get<AutomationNode[]>(`${BASE}/workflows/${workflowId}/nodes`);
  return data;
}

export async function listWorkflowEdges(workflowId: string): Promise<AutomationEdge[]> {
  const { data } = await api.get<AutomationEdge[]>(`${BASE}/workflows/${workflowId}/edges`);
  return data;
}

export async function createWorkflowNode(workflowId: string, payload: CreateNodePayload): Promise<AutomationNode> {
  const { data } = await api.post<AutomationNode>(`${BASE}/workflows/${workflowId}/nodes`, payload);
  return data;
}

export async function updateWorkflowNode(
  workflowId: string,
  nodeId: string,
  payload: UpdateNodePayload,
): Promise<AutomationNode> {
  const { data } = await api.patch<AutomationNode>(`${BASE}/workflows/${workflowId}/nodes/${nodeId}`, payload);
  return data;
}

export async function deleteWorkflowNode(workflowId: string, nodeId: string): Promise<void> {
  await api.delete(`${BASE}/workflows/${workflowId}/nodes/${nodeId}`);
}

export async function runWorkflow(workflowId: string): Promise<{ run_id: string }> {
  const { data } = await api.post<{ run_id: string }>(`${BASE}/workflows/${workflowId}/run`);
  return data;
}

export async function listWorkflowRuns(workflowId: string): Promise<AutomationRunSummary[]> {
  const { data } = await api.get<AutomationRunSummary[]>(`${BASE}/workflows/${workflowId}/runs`);
  return data;
}

export async function getWorkflowRun(workflowId: string, runId: string): Promise<AutomationRun> {
  const { data } = await api.get<AutomationRun>(`${BASE}/workflows/${workflowId}/runs/${runId}`);
  return data;
}

export async function listWorkflowRunNodes(workflowId: string, runId: string): Promise<AutomationNodeExecution[]> {
  const { data } = await api.get<AutomationNodeExecution[]>(`${BASE}/workflows/${workflowId}/runs/${runId}/nodes`);
  return data;
}

export async function cancelWorkflowRun(workflowId: string, runId: string): Promise<void> {
  await api.post(`${BASE}/workflows/${workflowId}/runs/${runId}/cancel`);
}

export async function listAutomationRunHistory(): Promise<AutomationRunSummary[]> {
  const { data } = await api.get<AutomationRunSummary[]>(`${BASE}/runs`);
  return data;
}

export async function createFromTemplate(payload: CreateFromTemplatePayload): Promise<AutomationWorkflow> {
  const { data } = await api.post<AutomationWorkflow>(`${BASE}/from-template`, payload);
  return data;
}

export function deriveWorkflowStatus(runStatus: string | null): AutomationWorkflowStatus {
  if (!runStatus) return "never";
  if (runStatus === "success" || runStatus === "completed") return "success";
  if (runStatus === "failed" || runStatus === "error") return "failed";
  if (runStatus === "running" || runStatus === "queued") return "running";
  return "never";
}
