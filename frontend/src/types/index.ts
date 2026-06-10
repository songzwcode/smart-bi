// ---- Modes -------------------------------------------------------------------

export type Mode = 'query' | 'script' | 'settings';

// ---- API mirrors of backend Pydantic schemas --------------------------------

export interface HealthResponse {
  ok: boolean;
  app: string;
  version: string;
  llm_provider?: string | null;
  llm_model?: string;
  db_url: string;
  db_dialect: string;
}

export interface LLMInfo {
  current_provider: string;
  current_model: string;
  available: Array<{
    provider: string;
    available: boolean;
    base_url?: string;
    models?: string[];
    error?: string;
  }>;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  default?: string | null;
  pk?: boolean;
}

export interface TableInfo {
  name: string;
  columns: ColumnInfo[];
  primary_key: string[];
  foreign_keys: Array<{
    columns: string[];
    referred_table?: string;
    referred_columns?: string[];
  }>;
  row_count: number;
  sample: Array<Record<string, unknown>>;
  comment: string;
}

export interface SchemaResponse {
  database: string;
  dialect: string;
  tables: TableInfo[];
  schema_text: string;
  reindexed: boolean;
}

export interface IntentResult {
  intent: 'query_data' | 'generate_chart' | 'generate_script' | 'explain_data';
  confidence: number;
  params: Record<string, unknown>;
  reasoning?: string;
  thinking?: string;
}

export interface PlanStep {
  id: number;
  description: string;
  action: string;
  depends_on: number[];
}

export interface Plan {
  is_multi_step: boolean;
  steps: PlanStep[];
  thinking?: string;
}

export interface StepResult {
  description: string;
  sql: string;
  columns: string[];
  rows: Array<Array<unknown>>;
  error: string;
  thinking?: string;
}

export interface QueryResponse {
  success: boolean;
  question: string;
  intent: IntentResult | Record<string, never>;
  plan: Plan | Record<string, never>;
  steps: StepResult[];
  final_sql: string;
  columns: string[];
  rows: Array<Array<unknown>>;
  chart: unknown | null;
  chart_type?: string | null;
  chart_auto?: boolean;
  elapsed_ms: number;
  llm_model: string;
  error?: string | null;
}

export interface ScriptResponse {
  success: boolean;
  requirement: string;
  code: string;
  language: string;
  script_subtype: 'query' | 'dml' | 'procedure';
  intent?: IntentResult | null;
  elapsed_ms: number;
  error?: string | null;
}

export interface ConnectionConfigFE {
  db_type: 'sqlite' | 'mysql' | 'postgres';
  host?: string;
  port?: number;
  user?: string;
  password?: string;
  database?: string;
  file_path?: string;
}

// ---- Chat messages ----------------------------------------------------------

export type MessageRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  queryResult?: QueryResponse;
  scriptResult?: ScriptResponse;
  pending?: boolean;
  error?: string;
  thinking?: string;
}
