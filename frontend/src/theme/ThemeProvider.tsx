import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type ThemeId = 'light' | 'dark-tech' | 'dark-neon' | 'system';
export type ResolvedTheme = 'light' | 'dark-tech' | 'dark-neon';

const STORAGE_KEY = 'smart-bi.theme';

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolveTheme(id: ThemeId): ResolvedTheme {
  if (id === 'system') return systemPrefersDark() ? 'dark-tech' : 'light';
  return id;
}

function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = resolved;
}

interface ThemeContextValue {
  /** User-selected theme id (may be 'system') */
  theme: ThemeId;
  /** Concrete theme in effect after resolving 'system' */
  resolved: ResolvedTheme;
  /** Update the theme — persists to localStorage. Backend sync is the
   * caller's responsibility (handled by App.tsx wiring). */
  setTheme: (t: ThemeId) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({
  initial,
  children,
}: {
  initial?: ThemeId;
  children: React.ReactNode;
}) {
  const [theme, setThemeState] = useState<ThemeId>(initial ?? 'light');
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(initial ?? 'light'));

  // Apply on mount and whenever the chosen id changes.
  useEffect(() => {
    const r = resolveTheme(theme);
    setResolved(r);
    applyTheme(r);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {}
  }, [theme]);

  // When the user picked 'system', listen for OS theme changes.
  useEffect(() => {
    if (theme !== 'system') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      const r = resolveTheme('system');
      setResolved(r);
      applyTheme(r);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [theme]);

  const setTheme = useCallback((t: ThemeId) => {
    setThemeState(t);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved, setTheme }),
    [theme, resolved, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
}
