import { useEffect, useRef } from 'react';
import Plotly from 'plotly.js/lib/index-basic';
import type { Data, Layout } from 'plotly.js';
import { useTheme } from '../theme/ThemeProvider';

interface Props {
  spec: { data: Data[]; layout: Partial<Layout> } | null;
  title?: string;
  rowCount?: number;
  chartType?: string | null;
}

export function ChartView({ spec, title, rowCount, chartType }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const { resolved } = useTheme();

  useEffect(() => {
    if (!ref.current || !spec) return;
    // Plotly has its own theming; we adapt colors based on the active theme
    // so the chart feels native to the surrounding UI.
    const isDark = resolved !== 'light';
    const accent = isDark
      ? resolved === 'dark-neon' ? '#A855F7' : '#0EA5E9'
      : '#6366F1';
    const axisColor = isDark ? '#94A3B8' : '#475569';
    const gridColor = isDark ? 'rgba(148,163,184,0.15)' : 'rgba(15,23,42,0.06)';
    const bg = 'transparent';

    const layout: Partial<Layout> = {
      ...spec.layout,
      paper_bgcolor: bg,
      plot_bgcolor: bg,
      font: { color: axisColor, family: 'Inter, system-ui, sans-serif' },
      xaxis: { ...(spec.layout?.xaxis ?? {}), gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor },
      yaxis: { ...(spec.layout?.yaxis ?? {}), gridcolor: gridColor, linecolor: gridColor, zerolinecolor: gridColor },
      legend: { ...(spec.layout?.legend ?? {}), font: { color: axisColor } },
      margin: { l: 48, r: 16, t: 8, b: 36, ...(spec.layout?.margin ?? {}) },
    };
    // Color each trace: use a small palette so multi-series charts stay readable.
    const palette = isDark
      ? ['#A855F7', '#0EA5E9', '#10B981', '#F59E0B', '#EC4899', '#22D3EE']
      : ['#6366F1', '#0EA5E9', '#10B981', '#F59E0B', '#EC4899', '#8B5CF6'];
    const data = (spec.data || []).map((trace, i) => {
      const t = trace as Data & { type?: string; marker?: { colors?: string[]; color?: string | string[] }; line?: { color?: string } };
      const color = palette[i % palette.length];
      if (t.type === 'pie') {
        return { ...t, marker: { ...(t.marker ?? {}), colors: t.marker?.colors ?? palette } };
      }
      if (t.type === 'scatter' && (t as { mode?: string }).mode?.includes('lines')) {
        return { ...t, line: { ...(t.line ?? {}), color } };
      }
      return {
        ...t,
        marker: { ...(t.marker ?? {}), color },
      } as Data;
    });

    Plotly.react(ref.current, data, layout, {
      displaylogo: false,
      responsive: true,
    }).catch((e: unknown) => console.error('Plotly render failed', e));
    return () => {
      if (ref.current) Plotly.purge(ref.current).catch(() => undefined);
    };
  }, [spec, resolved]);

  if (!spec || !spec.data || spec.data.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-ink-tertiary text-sm gap-2 animate-fade-in">
        <div className="text-3xl opacity-50">📊</div>
        <div>无图表数据</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col card overflow-hidden">
      {(title || chartType) && (
        <div className="px-3 py-2 border-b border-edge-subtle flex items-center gap-2 shrink-0">
          <div className="text-sm font-medium text-ink-primary truncate flex-1">
            {title || '图表'}
          </div>
          <div className="text-[11px] text-ink-tertiary shrink-0 flex items-center gap-2">
            {chartType && (
              <span className="px-1.5 py-0.5 rounded bg-primary-500/10 text-primary-600 dark:text-primary-300 font-mono">
                {chartType}
              </span>
            )}
            {typeof rowCount === 'number' && <span>{rowCount} 行</span>}
          </div>
        </div>
      )}
      <div ref={ref} className="flex-1 min-h-[320px] w-full" />
    </div>
  );
}
