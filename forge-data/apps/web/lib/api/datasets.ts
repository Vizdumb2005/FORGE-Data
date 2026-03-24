/**
 * Dataset, versioning, and data quality API functions.
 * All calls go through the connectors router at /api/v1/connectors/workspaces/{wid}/...
 */

import api from "@/lib/api";
import type {
  Dataset,
  DatasetVersion,
  DatasetWithProfile,
  QualityReport,
  QualityRule,
  QualityRuleset,
  VersionDiff,
} from "@/types";

const BASE = "/api/v1/connectors/workspaces";

// ── Datasets ─────────────────────────────────────────────────────────────────

export async function listDatasets(workspaceId: string): Promise<Dataset[]> {
  const { data } = await api.get<Dataset[]>(`${BASE}/${workspaceId}/datasets`);
  return data;
}

export async function getDataset(
  workspaceId: string,
  datasetId: string,
): Promise<Dataset> {
  const { data } = await api.get<Dataset>(
    `${BASE}/${workspaceId}/datasets/${datasetId}`,
  );
  return data;
}

export async function uploadDataset(
  workspaceId: string,
  file: File,
): Promise<DatasetWithProfile> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<DatasetWithProfile>(
    `${BASE}/${workspaceId}/datasets/upload`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function connectDataset(
  workspaceId: string,
  name: string,
  sourceType: string,
  connectionConfig: Record<string, unknown>,
): Promise<{ dataset: Dataset; schema_info: Array<Record<string, unknown>> }> {
  const { data } = await api.post(
    `${BASE}/${workspaceId}/datasets/connect`,
    { name, source_type: sourceType, connection_config: connectionConfig },
  );
  return data;
}

export async function deleteDataset(
  workspaceId: string,
  datasetId: string,
): Promise<void> {
  await api.delete(`${BASE}/${workspaceId}/datasets/${datasetId}`);
}

// ── Query ────────────────────────────────────────────────────────────────────

export async function executeQuery(
  workspaceId: string,
  sql: string,
): Promise<{
  columns: string[];
  rows: unknown[][];
  row_count: number;
  execution_time_ms: number;
}> {
  const { data } = await api.post(`${BASE}/${workspaceId}/query`, { sql });
  return data;
}

// ── Versions ─────────────────────────────────────────────────────────────────

export async function listVersions(
  workspaceId: string,
  datasetId: string,
): Promise<DatasetVersion[]> {
  const { data } = await api.get<DatasetVersion[]>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/versions`,
  );
  return data;
}

export async function createVersion(
  workspaceId: string,
  datasetId: string,
  file: File,
  message?: string,
): Promise<DatasetVersion> {
  const form = new FormData();
  form.append("file", file);
  if (message) form.append("message", message);
  const { data } = await api.post<DatasetVersion>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/versions`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

export async function diffVersions(
  workspaceId: string,
  datasetId: string,
  v1: number,
  v2: number,
): Promise<VersionDiff> {
  const { data } = await api.get<VersionDiff>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/versions/diff`,
    { params: { v1, v2 } },
  );
  return data;
}

export async function rollbackVersion(
  workspaceId: string,
  datasetId: string,
  versionNumber: number,
): Promise<DatasetVersion> {
  const { data } = await api.post<DatasetVersion>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/versions/${versionNumber}/rollback`,
  );
  return data;
}

// ── Quality ──────────────────────────────────────────────────────────────────

export async function runQualityCheck(
  workspaceId: string,
  datasetId: string,
  rules: QualityRule[],
): Promise<QualityReport> {
  const { data } = await api.post<QualityReport>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/quality/check`,
    { rules },
  );
  return data;
}

export async function saveRuleset(
  workspaceId: string,
  datasetId: string,
  name: string,
  rules: QualityRule[],
): Promise<QualityRuleset> {
  const { data } = await api.post<QualityRuleset>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/quality/ruleset`,
    { name, rules },
  );
  return data;
}

export async function getQualityReports(
  workspaceId: string,
  datasetId: string,
): Promise<QualityReport[]> {
  const { data } = await api.get<QualityReport[]>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/quality/reports`,
  );
  return data;
}

export async function maskDatasetPII(workspaceId: string, datasetId: string): Promise<Dataset> {
  const { data } = await api.post<Dataset>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/pii/mask`,
  );
  return data;
}

export async function acknowledgeDatasetPII(workspaceId: string, datasetId: string): Promise<Dataset> {
  const { data } = await api.post<Dataset>(
    `${BASE}/${workspaceId}/datasets/${datasetId}/pii/acknowledge`,
  );
  return data;
}
