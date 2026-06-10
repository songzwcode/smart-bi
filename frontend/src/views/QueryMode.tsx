import { useEffect, useState } from 'react';
import { ChatPanel } from '../components/ChatPanel';
import { TableView } from '../components/TableView';
import { ChartView } from '../components/ChartView';
import { SchemaTree } from '../components/SchemaTree';
import { useStore } from '../store/useStore';

type ResultTab = 'table' | 'chart' | 'sql';

export function QueryMode() {
  const result = useStore((s) => s.lastQueryResult);
  const [tab, setTab] = useState<ResultTab>('table');
  const [showSchema, setShowSchema] = useState(true);

  // When a new result comes in, auto-jump to the chart tab if the agent
  // produced a chart. Otherwise default to the table.
  useEffect(() => {
    if (result?.chart) {
      setTab('chart');
    } else {
      setTab('table');
    }
  }, [result]);

  return (
    <div className="relative flex h-full min-h-0 bg-surface-0">
      <div className="w-[420px] shrink-0 border-r border-edge-subtle flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-edge-subtle bg-surface-1">
          <div className="text-sm font-semibold text-ink-primary">💬 智能问数</div>
          <div className="text-xs text-ink-tertiary mt-0.5">用自然语言查询数据库</div>
        </div>
        <ChatPanel />
      </div>

      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        {result ? (
          <>
            <div className="border-b border-edge-subtle bg-surface-1 px-2 py-1.5 flex items-center gap-1 text-sm">
              {(['table', 'chart', 'sql'] as ResultTab[]).map((t) => {
                const isChart = t === 'chart';
                const chartAvail = !!result.chart;
                const disabled = isChart && !chartAvail;
                const active = tab === t && !disabled;
                return (
                  <button
                    key={t}
                    onClick={() => !disabled && setTab(t)}
                    disabled={disabled}
                    className={`relative px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 inline-flex items-center gap-1.5 ${
                      disabled
                        ? 'text-ink-muted cursor-not-allowed'
                        : active
                        ? 'text-ink-primary bg-primary-500/10'
                        : 'text-ink-secondary hover:bg-surface-2 hover:text-ink-primary'
                    }`}
                    type="button"
                  >
                    {t === 'table' ? '📋 表格' : t === 'chart' ? '📊 图表' : '⌨ SQL'}
                    {isChart && chartAvail && result.chart_auto && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-success/15 text-success font-mono">
                        自动
                      </span>
                    )}
                    {active && (
                      <span
                        aria-hidden
                        className="absolute bottom-0 left-2 right-2 h-[2px] rounded-t-full"
                        style={{
                          backgroundImage: `linear-gradient(90deg, rgb(var(--c-primary-500)), rgb(var(--c-accent-500)))`,
                        }}
                      />
                    )}
                  </button>
                );
              })}
              <div className="ml-auto text-[11px] text-ink-tertiary flex items-center gap-3 font-mono">
                <span>{result.rows.length} 行</span>
                <span className="text-ink-muted">·</span>
                <span>{result.elapsed_ms} ms</span>
                <span className="text-ink-muted">·</span>
                <span className="truncate max-w-[160px]" title={result.llm_model}>
                  {result.llm_model}
                </span>
              </div>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              {tab === 'table' && (
                <TableView
                  columns={result.columns}
                  rows={result.rows}
                />
              )}
              {tab === 'chart' && (
                <div className="p-2 h-full">
                  <ChartView
                    spec={result.chart as { data: any[]; layout: any } | null}
                    title={result.question}
                    rowCount={result.rows.length}
                    chartType={result.chart_type}
                  />
                </div>
              )}
              {tab === 'sql' && (
                <pre className="p-4 text-xs font-mono whitespace-pre-wrap text-ink-primary bg-surface-0 overflow-auto h-full leading-relaxed">
                  {result.final_sql}
                </pre>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center px-8 animate-fade-in">
            <div className="text-center max-w-md">
              <div
                className="w-24 h-24 mx-auto mb-4 rounded-3xl flex items-center justify-center text-5xl shadow-elevated"
                style={{
                  backgroundImage: `linear-gradient(135deg, rgb(var(--c-primary-500) / 0.15), rgb(var(--c-accent-500) / 0.15))`,
                }}
              >
                ✨
              </div>
              <div className="text-base font-semibold text-ink-primary mb-1.5">
                用一句话开始你的数据探索
              </div>
              <div className="text-sm text-ink-tertiary leading-relaxed">
                在左侧输入自然语言问题，例如"显示销售额最高的前 10 个客户"
                <br />
                AI 会自动理解意图、生成 SQL 并返回结果
              </div>
              <div className="mt-4 inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
                <span>←</span>
                <span>从左侧开始</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {showSchema && (
        <div className="w-[280px] shrink-0 border-l border-edge-subtle bg-surface-1 flex flex-col min-h-0">
          <div className="px-3 py-2.5 border-b border-edge-subtle flex items-center bg-surface-1">
            <span className="text-sm font-semibold text-ink-primary">🗂 Schema</span>
            <button
              onClick={() => setShowSchema(false)}
              className="ml-auto btn-ghost text-[11px]"
              type="button"
            >
              隐藏
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <SchemaTree />
          </div>
        </div>
      )}
      {!showSchema && (
        <button
          onClick={() => setShowSchema(true)}
          className="absolute right-3 top-3 z-10 btn-primary text-xs shadow-elevated animate-fade-in"
          type="button"
        >
          🗂 显示 Schema
        </button>
      )}
    </div>
  );
}
