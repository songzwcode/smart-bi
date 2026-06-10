import { create } from 'zustand';
import type {
  ChatMessage,
  HealthResponse,
  LLMInfo,
  Mode,
  SchemaResponse,
  ScriptResponse,
  QueryResponse,
} from '../types';
import type { ThemeId } from '../theme/ThemeProvider';

interface StoreState {
  mode: Mode;
  setMode: (m: Mode) => void;

  health: HealthResponse | null;
  setHealth: (h: HealthResponse) => void;

  llmInfo: LLMInfo | null;
  setLlmInfo: (l: LLMInfo) => void;

  schema: SchemaResponse | null;
  setSchema: (s: SchemaResponse) => void;

  // UI prefs (persisted server-side, mirrored here for fast access)
  showThinking: boolean;
  setShowThinking: (v: boolean) => void;
  theme: ThemeId;
  setTheme: (t: ThemeId) => void;

  // Query Mode state
  queryMessages: ChatMessage[];
  addQueryMessage: (m: ChatMessage) => void;
  updateLastQueryMessage: (patch: Partial<ChatMessage>) => void;
  clearQueryMessages: () => void;
  lastQueryResult: QueryResponse | null;
  setLastQueryResult: (r: QueryResponse | null) => void;

  // Script Mode state
  scriptCode: string;
  setScriptCode: (c: string) => void;
  scriptHistory: Array<{ id: string; requirement: string; result: ScriptResponse }>;
  addScriptHistory: (h: { id: string; requirement: string; result: ScriptResponse }) => void;
  clearScriptHistory: () => void;
}

const newId = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export const useStore = create<StoreState>((set) => ({
  mode: 'query',
  setMode: (m) => set({ mode: m }),

  health: null,
  setHealth: (h) => set({ health: h }),

  llmInfo: null,
  setLlmInfo: (l) => set({ llmInfo: l }),

  schema: null,
  setSchema: (s) => set({ schema: s }),

  showThinking: false,
  setShowThinking: (v) => set({ showThinking: v }),

  theme: 'system',
  setTheme: (t) => set({ theme: t }),

  queryMessages: [],
  addQueryMessage: (m) => set((s) => ({ queryMessages: [...s.queryMessages, m] })),
  updateLastQueryMessage: (patch) =>
    set((s) => {
      const arr = [...s.queryMessages];
      if (arr.length === 0) return s;
      arr[arr.length - 1] = { ...arr[arr.length - 1], ...patch };
      return { queryMessages: arr };
    }),
  clearQueryMessages: () => set({ queryMessages: [], lastQueryResult: null }),

  lastQueryResult: null,
  setLastQueryResult: (r) => set({ lastQueryResult: r }),

  scriptCode: '',
  setScriptCode: (c) => set({ scriptCode: c }),
  scriptHistory: [],
  addScriptHistory: (h) => set((s) => ({ scriptHistory: [h, ...s.scriptHistory].slice(0, 50) })),
  clearScriptHistory: () => set({ scriptHistory: [] }),
}));

export { newId };
