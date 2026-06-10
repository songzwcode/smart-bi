import type { Mode } from '../types';
import { useStore } from '../store/useStore';
import { useTheme } from '../theme/ThemeProvider';

interface SidebarProps {
  mode: Mode;
  onChange: (m: Mode) => void;
}

const NAV: Array<{ id: Mode; label: string; icon: string; description: string }> = [
  { id: 'query', label: '智能问数', icon: '💬', description: '自然语言查询数据' },
  { id: 'script', label: 'SQL 脚本', icon: '📝', description: '生成 SQL / 存储过程' },
  { id: 'settings', label: '设置', icon: '⚙️', description: '数据库与 LLM 配置' },
];

export function Sidebar({ mode, onChange }: SidebarProps) {
  const health = useStore((s) => s.health);
  const llmInfo = useStore((s) => s.llmInfo);
  const { resolved } = useTheme();
  const isDark = resolved !== 'light';

  return (
    <aside
      className={`w-60 shrink-0 flex flex-col border-r border-edge-subtle ${
        isDark ? 'bg-surface-1/60' : 'bg-surface-1'
      }`}
    >
      {/* Logo block */}
      <div className="px-4 py-4 border-b border-edge-subtle">
        <div className="flex items-center gap-2.5">
          <div
            className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-sm font-bold shadow-glow-sm"
            style={{
              backgroundImage: `linear-gradient(135deg, rgb(var(--c-primary-500)), rgb(var(--c-accent-500)))`,
            }}
          >
            BI
          </div>
          <div>
            <div className="font-semibold text-ink-primary leading-tight">
              {health?.app ?? 'Smart BI'}
            </div>
            <div className="text-[11px] text-ink-tertiary mt-0.5">
              v{health?.version ?? '0.1.0'} · 桌面端
            </div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {NAV.map((item) => {
          const active = mode === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              className={`relative w-full text-left px-3 py-2.5 flex items-start gap-3 rounded-lg group overflow-hidden transition-all duration-200 ${
                active
                  ? 'text-ink-primary'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-surface-2'
              }`}
              style={
                active
                  ? {
                      backgroundImage: `linear-gradient(90deg, rgb(var(--c-primary-500) / 0.15), rgb(var(--c-primary-500) / 0.04))`,
                    }
                  : undefined
              }
            >
              {/* Sliding indicator bar on the left */}
              <span
                className={`absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full transition-all duration-200 ${
                  active ? 'opacity-100 scale-y-100' : 'opacity-0 scale-y-50'
                }`}
                style={{
                  backgroundImage: `linear-gradient(180deg, rgb(var(--c-primary-400)), rgb(var(--c-accent-500)))`,
                }}
              />
              <span className="text-lg shrink-0 mt-0.5">{item.icon}</span>
              <span className="flex-1 min-w-0">
                <div
                  className={`text-sm font-medium ${
                    active ? 'text-primary-600 dark:text-primary-300' : ''
                  }`}
                >
                  {item.label}
                </div>
                <div className="text-[11px] text-ink-tertiary mt-0.5 leading-snug">
                  {item.description}
                </div>
              </span>
            </button>
          );
        })}
      </nav>

      {/* Status block */}
      <div className="px-3 py-3 border-t border-edge-subtle space-y-2">
        <div
          className="glass rounded-lg px-2.5 py-2 border border-edge-subtle space-y-1.5"
        >
          <div className="flex items-center gap-1.5">
            <span
              className={`status-dot ${
                llmInfo?.current_provider ? 'bg-success animate-pulse-glow' : 'bg-ink-muted'
              }`}
              style={{ color: llmInfo?.current_provider ? 'rgb(16 185 129)' : undefined }}
            />
            <span className="text-[11px] text-ink-secondary font-medium uppercase tracking-wider">
              LLM
            </span>
          </div>
          <div className="text-xs text-ink-primary font-mono truncate" title={llmInfo?.current_model}>
            {llmInfo?.current_provider || 'no LLM'}
            {llmInfo?.current_model ? ` · ${llmInfo.current_model}` : ''}
          </div>
        </div>
        <div
          className="glass rounded-lg px-2.5 py-2 border border-edge-subtle space-y-1.5"
        >
          <div className="flex items-center gap-1.5">
            <span
              className={`status-dot ${
                health ? 'bg-success animate-pulse-glow' : 'bg-danger'
              }`}
              style={{ color: health ? 'rgb(16 185 129)' : 'rgb(244 63 94)' }}
            />
            <span className="text-[11px] text-ink-secondary font-medium uppercase tracking-wider">
              DB
            </span>
          </div>
          <div className="text-xs text-ink-primary font-mono truncate" title={health?.db_url}>
            {health ? health.db_dialect : 'disconnected'}
          </div>
        </div>
      </div>
    </aside>
  );
}
