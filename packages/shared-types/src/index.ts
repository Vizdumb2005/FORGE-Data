// ── User ──────────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface UserCreate {
  email: string
  password: string
  full_name: string
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: 'bearer'
}

// ── Workbooks ─────────────────────────────────────────────────────────────────

export type CellType = 'python' | 'sql' | 'markdown' | 'ai'

export interface Cell {
  id: string
  type: CellType
  source: string
  output?: CellOutput | null
}

export interface CellOutput {
  status: 'ok' | 'error'
  data?: Record<string, unknown>
  text?: string
  error?: string
  execution_count?: number
}

export interface Workbook {
  id: string
  name: string
  cells: Cell[]
  owner_id: string
  created_at: string
  updated_at: string
}

export interface WorkbookCreate {
  name: string
  cells?: Cell[]
}

export interface ExecuteCellRequest {
  cell_id: string
  source: string
  kernel_id?: string
}

export interface ExecuteCellResponse {
  cell_id: string
  output: CellOutput
  kernel_id: string
}

// ── Connectors ────────────────────────────────────────────────────────────────

export type ConnectorType =
  | 'postgres'
  | 'mysql'
  | 'bigquery'
  | 'snowflake'
  | 'csv'
  | 'parquet'
  | 'rest'

export interface Connector {
  id: string
  name: string
  type: ConnectorType
  owner_id: string
  created_at: string
  updated_at: string
}

export interface ConnectorCreate {
  name: string
  type: ConnectorType
  config: Record<string, unknown>
}

export interface SchemaColumn {
  name: string
  type: string
  nullable: boolean
}

export interface SchemaTable {
  name: string
  columns: SchemaColumn[]
}

// ── LLM / BYOK ────────────────────────────────────────────────────────────────

export type LLMProvider = 'openai' | 'anthropic' | 'google' | 'azure' | 'ollama'

export interface LLMProviderConfig {
  provider: LLMProvider
  model: string
  api_key?: string
  base_url?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatRequest {
  messages: ChatMessage[]
  provider: LLMProviderConfig
  context?: Record<string, unknown>
  stream?: boolean
}

export interface ProviderInfo {
  id: LLMProvider
  name: string
  models: string[]
  requires_key: boolean
}

// ── Datasets ──────────────────────────────────────────────────────────────────

export interface Dataset {
  id: string
  name: string
  source_connector_id?: string | null
  storage_path?: string | null
  schema_snapshot?: SchemaTable[] | null
  owner_id: string
  created_at: string
  updated_at: string
}

// ── API responses ─────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string
  status_code?: number
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
