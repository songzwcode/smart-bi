import axios from 'axios';
import type {
  ConnectionConfigFE,
  HealthResponse,
  LLMInfo,
  QueryResponse,
  SchemaResponse,
  ScriptResponse,
} from '../types';

const client = axios.create({
  baseURL: '/',
  timeout: 120_000,
});

export const api = {
  async health(): Promise<HealthResponse> {
    const { data } = await client.get<HealthResponse>('/api/health');
    return data;
  },

  async getSchema(reindex = false): Promise<SchemaResponse> {
    const { data } = await client.get<SchemaResponse>('/api/schema', {
      params: reindex ? { reindex: true } : {},
    });
    return data;
  },

  async listLLM(): Promise<LLMInfo> {
    const { data } = await client.get<LLMInfo>('/api/llm/list');
    return data;
  },

  async switchLLM(payload: {
    provider: string;
    model?: string;
    ollama_url?: string;
    custom_url?: string;
    api_key?: string;
  }): Promise<LLMInfo> {
    const { data } = await client.post<LLMInfo>('/api/llm/switch', payload);
    return data;
  },

  async testLLM(payload: {
    provider: string;
    model?: string;
    ollama_url?: string;
    custom_url?: string;
    api_key?: string;
  }): Promise<{ ok: boolean; status_code?: number; url?: string; error?: string }> {
    const { data } = await client.post('/api/llm/test', payload);
    return data;
  },

  async testConnection(config: ConnectionConfigFE, readonly = true) {
    const { data } = await client.post('/api/connection/test', {
      config,
      readonly,
    });
    return data as { ok: boolean; url?: string; dialect?: string; error?: string };
  },

  async connect(config: ConnectionConfigFE, readonly = true) {
    const { data } = await client.post('/api/connection/connect', config, {
      params: { readonly },
    });
    return data as { ok: boolean; url: string; dialect: string };
  },

  async query(payload: {
    question: string;
    chart_type?: string;
    llm_provider?: string;
    llm_model?: string;
  }): Promise<QueryResponse> {
    const { data } = await client.post<QueryResponse>('/api/query', payload);
    return data;
  },

  async generateScript(payload: {
    requirement: string;
    script_subtype?: 'query' | 'dml' | 'procedure';
    llm_provider?: string;
    llm_model?: string;
  }): Promise<ScriptResponse> {
    const { data } = await client.post<ScriptResponse>('/api/script', payload);
    return data;
  },

  async refineScript(payload: {
    original_sql: string;
    feedback: string;
    llm_provider?: string;
    llm_model?: string;
  }): Promise<ScriptResponse> {
    const { data } = await client.post<ScriptResponse>('/api/script/refine', payload);
    return data;
  },

  /**
   * Stream script generation. Calls onEvent for each SSE event
   * ({type: 'phase'|'think'|'content'|'final'|'error', ...}). Resolves
   * with the final ScriptResponse.
   */
  async streamScript(
    payload: {
      requirement: string;
      script_subtype?: 'query' | 'dml' | 'procedure';
    },
    onEvent: (ev: ScriptStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<ScriptResponse> {
    const resp = await fetch('/api/script/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}: ${await resp.text().catch(() => '')}`);
    }
    return consumeScriptStream(resp.body, onEvent);
  },

  /**
   * Stream script refinement. Same event contract as streamScript.
   */
  async streamRefineScript(
    payload: { original_sql: string; feedback: string },
    onEvent: (ev: ScriptStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<ScriptResponse> {
    const resp = await fetch('/api/script/refine/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    });
    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}: ${await resp.text().catch(() => '')}`);
    }
    return consumeScriptStream(resp.body, onEvent);
  },

  async executeSQL(sql: string, max_rows?: number) {
    const { data } = await client.post('/api/sql/execute', { sql, max_rows });
    return data;
  },

  async formatSQL(sql: string, dialect?: string) {
    const { data } = await client.post('/api/sql/format', { sql, dialect });
    return data as { success: boolean; formatted: string; violations: Array<{ rule: string; line: number; description: string }>; error?: string };
  },

  async lintSQL(sql: string, dialect?: string) {
    const { data } = await client.post('/api/sql/lint', { sql, dialect });
    return data as { success: boolean; violations: Array<{ rule: string; line: number; description: string }> };
  },

  async exportSQL(content: string) {
    const { data } = await client.post('/api/export/sql', { content });
    return data as { path: string; filename: string; size_bytes: number; format: string };
  },

  async exportCSV(columns: string[], rows: Array<Array<unknown>>) {
    const { data } = await client.post('/api/export/csv', { columns, rows });
    return data as { path: string; filename: string; size_bytes: number; format: string };
  },

  async getPersistedSettings() {
    const { data } = await client.get('/api/settings');
    return data as {
      llm: {
        provider: string;
        model?: string;
        ollama_url?: string;
        custom_url?: string;
        custom_api_key?: string;
      } | null;
      db: Record<string, unknown> | null;
      ui: { show_thinking?: boolean; theme?: 'light' | 'dark-tech' | 'dark-neon' | 'system' } | null;
      has_persisted: boolean;
    };
  },

  async setUiPref(key: string, value: unknown) {
    const { data } = await client.post('/api/settings/ui', { key, value });
    return data as { ok: boolean; key: string; value: unknown };
  },

  async resetPersistedSettings() {
    const { data } = await client.post('/api/settings/reset');
    return data as { ok: boolean };
  },
};

// ---- Script streaming helpers ----------------------------------------------

export interface ScriptStreamEvent {
  type: 'phase' | 'think' | 'content' | 'final' | 'error';
  text?: string;
  phase?: string;
  result?: ScriptResponse;
  error?: string;
}

async function consumeScriptStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (ev: ScriptStreamEvent) => void,
): Promise<ScriptResponse> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let finalResult: ScriptResponse | null = null;
  let sawError = false;
  let errorMsg = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // Normalize \r\n → \n so leading \r from previous event terminator
    // doesn't break `startsWith('event:')` / `startsWith('data:')`.
    const normalized = buf.replace(/\r\n/g, '\n');
    const parts = normalized.split('\n\n');
    buf = parts.pop() || '';
    for (const part of parts) {
      const lines = part.split('\n');
      let eventName = 'message';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (!data) continue;
      let parsed: ScriptStreamEvent;
      try {
        parsed = JSON.parse(data);
      } catch {
        continue;
      }
      const ev: ScriptStreamEvent = {
        ...parsed,
        type: (parsed.type || (eventName as ScriptStreamEvent['type'])),
      };
      // Server sends the ScriptResponse directly as the final event data.
      if (ev.type === 'final' && !ev.result) {
        ev.result = parsed as unknown as ScriptResponse;
      }
      onEvent(ev);
      if (ev.type === 'error') {
        sawError = true;
        errorMsg = ev.error || 'unknown error';
        try { await reader.cancel(); } catch {}
        break;
      }
      if (ev.type === 'final' && ev.result) {
        finalResult = ev.result;
      }
    }
    if (sawError) break;
  }
  if (sawError) throw new Error(errorMsg);
  if (!finalResult) throw new Error('Stream ended without final result');
  return finalResult;
}
