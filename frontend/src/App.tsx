import { useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { QueryMode } from './views/QueryMode';
import { ScriptMode } from './views/ScriptMode';
import { SettingsView } from './views/SettingsView';
import { useStore } from './store/useStore';
import { api } from './api/client';
import { ThemeProvider, useTheme, type ThemeId } from './theme/ThemeProvider';
import type { Mode } from './types';

const VIEWS: Record<Mode, () => JSX.Element> = {
  query: QueryMode,
  script: ScriptMode,
  settings: SettingsView,
};

function readLocalTheme(): ThemeId {
  try {
    const t = localStorage.getItem('smart-bi.theme');
    if (t === 'light' || t === 'dark-tech' || t === 'dark-neon' || t === 'system') {
      return t;
    }
  } catch {}
  return 'system';
}

function AppShell() {
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const setHealth = useStore((s) => s.setHealth);
  const setLlmInfo = useStore((s) => s.setLlmInfo);
  const setSchema = useStore((s) => s.setSchema);
  const setShowThinking = useStore((s) => s.setShowThinking);
  const storeTheme = useStore((s) => s.theme);
  const setStoreTheme = useStore((s) => s.setTheme);
  const { theme, setTheme } = useTheme();

  // Load persisted settings on first mount.
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [h, l, s, persisted] = await Promise.all([
          api.health(),
          api.listLLM(),
          api.getSchema(),
          api.getPersistedSettings().catch(() => null),
        ]);
        if (!mounted) return;
        setHealth(h);
        setLlmInfo(l);
        setSchema(s);
        if (persisted?.ui) {
          if (persisted.ui.show_thinking !== undefined) {
            setShowThinking(!!persisted.ui.show_thinking);
          }
          if (persisted.ui.theme) {
            const t = persisted.ui.theme as ThemeId;
            if (t === 'light' || t === 'dark-tech' || t === 'dark-neon' || t === 'system') {
              setStoreTheme(t);
              setTheme(t);
            }
          }
        }
      } catch (e) {
        console.error('Initial load failed', e);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [setHealth, setLlmInfo, setSchema, setShowThinking, setStoreTheme, setTheme]);

  // Bridge: when the user changes the theme in Settings (via the provider's
  // setTheme), keep the store + backend in sync.
  useEffect(() => {
    if (storeTheme !== theme) {
      setStoreTheme(theme);
      api.setUiPref('theme', theme).catch(() => {});
    }
  }, [theme, storeTheme, setStoreTheme]);

  const View = VIEWS[mode];
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface-0 text-ink-primary">
      <Sidebar mode={mode} onChange={setMode} />
      <main className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
        <View />
      </main>
    </div>
  );
}

export default function App() {
  const initial = readLocalTheme();
  return (
    <ThemeProvider initial={initial}>
      <AppShell />
    </ThemeProvider>
  );
}
