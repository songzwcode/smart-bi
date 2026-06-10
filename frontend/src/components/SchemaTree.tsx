import { useMemo, useState } from 'react';
import { useStore } from '../store/useStore';
import { api } from '../api/client';

export function SchemaTree() {
  const schema = useStore((s) => s.schema);
  const setSchema = useStore((s) => s.setSchema);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [filter, setFilter] = useState('');

  async function refresh() {
    setBusy(true);
    try {
      const s = await api.getSchema(true);
      setSchema(s);
    } finally {
      setBusy(false);
    }
  }

  const visibleTables = useMemo(() => {
    if (!schema) return [];
    const q = filter.trim().toLowerCase();
    if (!q) return schema.tables;
    return schema.tables.filter((t) => t.name.toLowerCase().includes(q));
  }, [schema, filter]);

  if (!schema) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-ink-tertiary text-sm gap-2">
        <div className="inline-block w-4 h-4 border-2 border-primary-500/30 border-t-primary-500 rounded-full animate-spin" />
        <div>加载中…</div>
      </div>
    );
  }

  return (
    <div className="text-sm h-full flex flex-col min-h-0">
      <div className="sticky top-0 z-10 bg-surface-1/95 backdrop-blur border-b border-edge-subtle px-2.5 py-2 space-y-1.5">
        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold text-ink-primary text-xs uppercase tracking-wider">
            {schema.dialect}
          </span>
          <span className="text-[11px] text-ink-tertiary truncate flex-1" title={schema.database}>
            {schema.database}
          </span>
          <button
            onClick={refresh}
            disabled={busy}
            className="btn-ghost text-[11px] disabled:opacity-50"
            type="button"
          >
            {busy ? '⟳' : '↻ 刷新'}
          </button>
        </div>
        <div className="relative">
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索表…"
            className="input-base text-xs py-1 pl-7"
          />
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-ink-muted text-xs pointer-events-none">
            🔍
          </span>
        </div>
      </div>
      <ul className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1.5">
        {visibleTables.length === 0 && (
          <li className="text-xs text-ink-tertiary px-2 py-4 text-center">无匹配表</li>
        )}
        {visibleTables.map((t) => {
          const isOpen = !!open[t.name];
          return (
            <li
              key={t.name}
              className="card overflow-hidden animate-fade-in"
            >
              <button
                onClick={() => setOpen({ ...open, [t.name]: !isOpen })}
                className="w-full flex items-center px-2.5 py-1.5 hover:bg-surface-2 transition-colors"
                type="button"
              >
                <span
                  className={`mr-1.5 text-ink-tertiary inline-block transition-transform duration-200 ${
                    isOpen ? 'rotate-90' : ''
                  }`}
                >
                  ▶
                </span>
                <span className="font-mono font-medium text-ink-primary text-sm">{t.name}</span>
                <span className="ml-auto flex items-center gap-1.5 text-[10px] text-ink-tertiary">
                  <span className="px-1.5 py-0.5 rounded bg-surface-2 text-ink-secondary font-mono">
                    {t.columns.length} 列
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-surface-2 text-ink-secondary font-mono">
                    {t.row_count} 行
                  </span>
                </span>
              </button>
              {isOpen && (
                <ul className="px-2 pb-2 pt-1 space-y-0.5 border-t border-edge-subtle">
                  {t.columns.map((c) => (
                    <li
                      key={c.name}
                      className="flex items-center text-xs pl-4 py-0.5 hover:bg-surface-2 rounded transition-colors"
                    >
                      <span className="flex items-center gap-1 mr-1.5 shrink-0">
                        {c.pk && (
                          <span
                            className="inline-flex items-center justify-center w-3.5 h-3.5 rounded bg-warning/20 text-warning font-bold text-[9px]"
                            title="Primary Key"
                          >
                            PK
                          </span>
                        )}
                        {!c.nullable && !c.pk && (
                          <span
                            className="inline-flex items-center justify-center w-3.5 h-3.5 rounded bg-danger/20 text-danger font-bold text-[9px]"
                            title="NOT NULL"
                          >
                            NN
                          </span>
                        )}
                      </span>
                      <span className="font-mono text-ink-primary flex-1 truncate">{c.name}</span>
                      <span className="ml-2 text-ink-tertiary text-[10px] font-mono shrink-0">{c.type}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
