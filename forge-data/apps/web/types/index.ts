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
  schema_snapshot: Record<string, unknown> | null;
  has_connection_config: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface DatasetPreview {
  columns: string[];
  rows: unknown[][];
  total_rows: number;
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

export type LLMProvider = "openai" | "anthropic" | "ollama" | "google" | "azure";

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
