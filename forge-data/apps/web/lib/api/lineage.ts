import api from "@/lib/api";

export type LineageNodeType = "dataset" | "cell" | "model" | "export";

export interface LineageNodeDTO {
  id: string;
  type: LineageNodeType;
  label: string;
  position: { x: number; y: number };
  metadata: Record<string, unknown>;
  last_executed_at?: string | null;
}

export interface LineageEdgeDTO {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string | null;
  is_active: boolean;
  is_recent: boolean;
  metadata: Record<string, unknown>;
  last_seen_at?: string | null;
}

export interface WorkspaceLineageResponse {
  nodes: LineageNodeDTO[];
  edges: LineageEdgeDTO[];
}

export async function getWorkspaceLineage(workspaceId: string): Promise<WorkspaceLineageResponse> {
  const { data } = await api.get<WorkspaceLineageResponse>(`/api/v1/workspaces/${workspaceId}/lineage`);
  return data;
}

