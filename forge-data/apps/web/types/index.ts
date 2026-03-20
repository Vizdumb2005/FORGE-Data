// ── User ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  preferred_llm_provider: string;
  has_openai_key: boolean;
  has_anthropic_key: boolean;
  has_ollama_url: boolean;
  created_at: string;
  updated_at: string;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface AuthResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

// ── Workspace ─────────────────────────────────────────────────────────────────

export type MemberRole = "viewer" | "analyst" | "editor" | "admin";

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  is_public: boolean;
  owner_id: string;
  created_at: string;
  updated_at: string;
  member_count: number;
  dataset_count: number;
  role: string | null;
}

export interface WorkspaceMember {
  user_id: string;
  workspace_id: string;
  role: MemberRole;
  email: string;
  full_name: string | null;
  joined_at: string;
}

export interface WorkspaceCreatePayload {
  name: string;
  description?: string;
  is_public?: boolean;
}

export interface WorkspaceUpdatePayload {
  name?: string;
  description?: string;
  is_public?: boolean;
}

// ── Dataset ───────────────────────────────────────────────────────────────────

export type SourceType =
  | "csv"
  | "parquet"
  | "json"
  | "excel"
  | "postgres"
  | "mysql"
  | "sqlite"
  | "rest_api"
  | "s3"
  | "snowflake"
  | "bigquery";

export interface Dataset {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  source_type: SourceType;
  storage_path: string | null;
  row_count: number | null;
  column_count: number | null;
  size_bytes: number | null;
  schema_snapshot: SchemaColumn[] | null;
  profile_data: DatasetProfile | null;
  has_connection_config: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SchemaColumn {
  name: string;
  dtype: string;
  nullable?: boolean;
  sample_values?: unknown[];
}

export interface DatasetPreview {
  columns: string[];
  rows: unknown[][];
  total_rows: number;
}

// ── Versioning ───────────────────────────────────────────────────────────────

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  message: string | null;
  schema_snapshot: SchemaColumn[] | null;
  row_count: number | null;
  size_bytes: number | null;
  parquet_path: string;
  created_by: string | null;
  created_at: string;
}

export interface VersionDiff {
  v1: number;
  v2: number;
  row_count_v1: number;
  row_count_v2: number;
  row_delta: number;
  added_columns: string[];
  removed_columns: string[];
  type_changes: Array<{ column: string; from: string; to: string }>;
  stat_changes: Array<{
    column: string;
    v1: Record<string, number | null>;
    v2: Record<string, number | null>;
    mean_delta: number | null;
    null_pct_delta: number | null;
  }>;
}

// ── Data Quality ─────────────────────────────────────────────────────────────

export interface QualityRule {
  type: string;
  column?: string;
  threshold?: number;
  pattern?: string;
  values?: unknown[];
}

export interface QualityReport {
  id: string;
  dataset_id: string;
  version_number: number | null;
  passed: number;
  failed: number;
  results: QualityCheckResult[];
  ruleset_id: string | null;
  created_by: string | null;
  created_at: string;
}

export interface QualityCheckResult {
  rule_type: string;
  column: string | null;
  status: "passed" | "failed";
  message: string;
  failing_rows_sample: unknown[];
}

export interface QualityRuleset {
  id: string;
  dataset_id: string;
  name: string;
  rules: QualityRule[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

// ── Profile ──────────────────────────────────────────────────────────────────

export interface ColumnProfile {
  name: string;
  dtype: string;
  distinct_count: number;
  null_count: number;
  min?: unknown;
  max?: unknown;
  avg?: number | null;
  sample_values?: unknown[];
}

export interface DatasetProfile {
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
}

export interface DatasetWithProfile {
  dataset: Dataset;
  profile: DatasetProfile;
}

// ── Cell ──────────────────────────────────────────────────────────────────────

export type CellType = "code" | "sql" | "markdown" | "chart" | "ai_chat";
export type CellLanguage = "python" | "sql" | "markdown" | "r" | "bash";

export interface CellOutput {
  mime_type: string;
  data: Record<string, unknown>;
  execution_count?: number | null;
  error?: string | null;
}

export interface Cell {
  id: string;
  workspace_id: string;
  cell_type: CellType;
  language: CellLanguage | null;
  content: string;
  output: CellOutput | null;
  kernel_id: string | null;
  position_x: number;
  position_y: number;
  width: number;
  height: number;
  created_at: string;
  updated_at: string;
}

export interface CellCreatePayload {
  cell_type: CellType;
  language?: CellLanguage;
  content?: string;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
}

export interface CellUpdatePayload {
  content?: string;
  position_x?: number;
  position_y?: number;
  width?: number;
  height?: number;
}

export interface ExecuteRequest {
  code: string;
  kernel_id?: string | null;
}

export interface ExecuteResponse {
  output: CellOutput;
  kernel_id: string;
  execution_time_ms: number;
}

// ── AI ────────────────────────────────────────────────────────────────────────

export type LLMProvider = string;

export interface AIProviderOption {
  id: string;
  name: string;
  models: string[];
  default_model: string;
  configured: boolean;
  requires_api_key: boolean;
  local?: boolean;
  priority?: number;
  required_settings?: string[];
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  provider?: LLMProvider;
  model?: string;
  api_key?: string;
  temperature?: number;
  max_tokens?: number;
}

// ── Connector ─────────────────────────────────────────────────────────────────

export interface ConnectorTestRequest {
  source_type: SourceType;
  connection_config: Record<string, unknown>;
}

export interface ConnectorTestResult {
  ok: boolean;
  message: string;
  latency_ms: number;
}

export interface ConnectorSchema {
  tables: Array<{
    name: string;
    columns: Array<{ name: string; type: string; nullable: boolean }>;
  }>;
}

// ── Experiment ────────────────────────────────────────────────────────────────

export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface Experiment {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  mlflow_experiment_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExperimentRun {
  id: string;
  experiment_id: string;
  name: string | null;
  status: RunStatus;
  params: Record<string, unknown> | null;
  metrics: Record<string, unknown> | null;
  mlflow_run_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditLog {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

// ── API error ─────────────────────────────────────────────────────────────────

export interface ApiError {
  detail?: string;
  code?: string;
  message?: string;
}

// ── Pagination ────────────────────────────────────────────────────────────────

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}
