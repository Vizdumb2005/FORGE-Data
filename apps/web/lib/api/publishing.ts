import api from "@/lib/api";
import type { PublishedDashboardInfo, ScheduledReportInfo } from "@/types";

export interface PublishDashboardPayload {
  title: string;
  cell_ids: string[];
  is_public: boolean;
  password?: string;
  refresh_interval_minutes?: number | null;
}

export async function publishDashboard(workspaceId: string, payload: PublishDashboardPayload) {
  const { data } = await api.post(`/api/v1/workspaces/${workspaceId}/publish`, payload);
  return data as { slug: string; url: string; dashboard: Record<string, unknown> };
}

export async function exportWorkspace(
  workspaceId: string,
  format: "jupyter" | "html" | "pdf",
  cellIds: string[],
): Promise<Blob> {
  const { data } = await api.post(
    `/api/v1/workspaces/${workspaceId}/export`,
    { format, cell_ids: cellIds },
    { responseType: "blob" },
  );
  return data as Blob;
}

export async function scheduleReport(
  workspaceId: string,
  payload: {
    cell_ids: string[];
    format: "html" | "pdf";
    schedule: string;
    delivery: Record<string, unknown>;
  },
) {
  const { data } = await api.post(`/api/v1/workspaces/${workspaceId}/schedule-report`, payload);
  return data;
}

export async function listPublished(workspaceId: string): Promise<{
  dashboards: PublishedDashboardInfo[];
  scheduled_reports: ScheduledReportInfo[];
}> {
  const { data } = await api.get(`/api/v1/workspaces/${workspaceId}/published`);
  return data;
}

export async function unpublishDashboard(workspaceId: string, dashboardId: string): Promise<void> {
  await api.delete(`/api/v1/workspaces/${workspaceId}/published/${dashboardId}`);
}

