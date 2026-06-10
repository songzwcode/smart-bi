import { useState, useRef, useEffect } from 'react';
import { SqlEditor } from '../components/SqlEditor';
import { SchemaTree } from '../components/SchemaTree';
import { useStore, newId } from '../store/useStore';
import { api } from '../api/client';
import type { ScriptResponse } from '../types';

type Subtype = 'query' | 'dml' | 'procedure';

const SUBTYPE_META: Record<Subtype, { label: string; icon: string; desc: string }> = {
  query: { label: '查询', icon: '🔍', desc: 'SELECT 语句' },
  dml: { label: 'DML', icon: '✏️', desc: 'INSERT/UPDATE/DELETE' },
  procedure: { label: '存储过程', icon: '⚙️', desc: 'CREATE PROCEDURE' },
};

export function ScriptMode() {
  const scriptCode = useStore((s) => s.scriptCode);
  const setScriptCode = useStore((s) => s.setScriptCode);
  const addHistory = useStore((s) => s.addScriptHistory);
  const history = useStore((s) => s.scriptHistory);

  const [requirement, setRequirement] = useState('');
  const [subtype, setSubtype] = useState<Subtype>('query');
  const [refine, setRefine] = useState('');
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{
    columns: string[];
    rows: Array<Array<unknown>>;
  } | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [exportMsg, setExportMsg] = useState('');
  const [showSchema, setShowSchema] = useState(true);

  const editorLang = subtype === 'procedure' ? 'sql' : 'sql';

  async function generate() {
    if (!requirement.trim() || busy) return;
    setBusy(true);
    setExportMsg('');
    setPreview(null);
    setPreviewError('');
    setScriptCode('');
    let buf = '';
    try {
      const r = await api.streamScript(
        { requirement, script_subtype: subtype },
        (ev) => {
          if (ev.type === 'content') {
            buf += ev.text || '';
            setScriptCode(buf);
          } else if (ev.type === 'error') {
            setExportMsg(`生成失败: ${ev.error || 'unknown'}`);
          }
        },
      );
      if (r.success) {
        setScriptCode(r.code || buf);
        addHistory({ id: newId(), requirement, result: r });
      } else {
        setExportMsg(`生成失败: ${r.error}`);
      }
    } catch (e) {
      setExportMsg(`请求失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function doRefine() {
    if (!refine.trim() || !scriptCode.trim() || busy) return;
    setBusy(true);
    setScriptCode('');
    let buf = '';
    try {
      const r = await api.streamRefineScript(
        { original_sql: scriptCode, feedback: refine },
        (ev) => {
          if (ev.type === 'content') {
            buf += ev.text || '';
            setScriptCode(buf);
          } else if (ev.type === 'error') {
            setExportMsg(`Refine 失败: ${ev.error || 'unknown'}`);
          }
        },
      );
      if (r.success) {
        setScriptCode(r.code || buf);
        setRefine('');
      } else {
        setExportMsg(`Refine 失败: ${r.error}`);
      }
    } catch (e) {
      setExportMsg(`请求失败: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function format() {
    if (!scriptCode.trim()) return;
    try {
      const r = await api.formatSQL(scriptCode);
      if (r.success) setScriptCode(r.formatted);
    } catch (e) {
      console.error(e);
    }
  }

  async function executePreview() {
    if (!scriptCode.trim()) return;
    setPreviewError('');
    setPreview(null);
    try {
      const r = await api.executeSQL(scriptCode, 200);
      if (r.success) {
        if (r.statement_type === 'SELECT') {
          setPreview({ columns: r.columns || [], rows: r.rows || [] });
        } else {
          setPreviewError(`执行成功，影响 ${r.affected_rows ?? 0} 行（${r.statement_type}）`);
        }
      } else {
        setPreviewError(r.error || '执行失败');
      }
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e));
    }
  }

  async function exportSql() {
    if (!scriptCode.trim()) return;
    try {
      const r = await api.exportSQL(scriptCode);
      setExportMsg(`✓ 已保存: ${r.path} (${r.size_bytes} bytes)`);
    } catch (e) {
      setExportMsg(`✗ 导出失败: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  function loadFromHistory(h: ScriptResponse) {
    setScriptCode(h.code);
    setRequirement(h.requirement);
  }

  const exportTimer = useRef<number | null>(null);
  useEffect(() => {
    if (exportMsg) {
      if (exportTimer.current) window.clearTimeout(exportTimer.current);
      exportTimer.current = window.setTimeout(() => setExportMsg(''), 4000);
    }
  }, [exportMsg]);

  return (
    <div className="flex h-full min-h-0 bg-surface-0">
      <div className="w-[320px] shrink-0 border-r border-edge-subtle bg-surface-1 flex flex-col min-h-0">
        <div className="px-4 py-2.5 border-b border-edge-subtle">
          <div className="text-sm font-semibold text-ink-primary">📝 SQL 脚本生成</div>
          <div className="text-xs text-ink-tertiary mt-0.5">用自然语言写 SQL / 存储过程</div>
        </div>

        <div className="p-3 space-y-3 border-b border-edge-subtle">
          <div>
            <div className="text-[11px] text-ink-tertiary uppercase tracking-wider mb-1.5 font-medium">
              类型
            </div>
            <div className="grid grid-cols-3 gap-1 p-0.5 rounded-lg bg-surface-2 border border-edge-subtle">
              {(['query', 'dml', 'procedure'] as Subtype[]).map((t) => {
                const meta = SUBTYPE_META[t];
                const active = subtype === t;
                return (
                  <button
                    key={t}
                    onClick={() => setSubtype(t)}
                    className={`px-2 py-1.5 rounded-md text-xs font-medium transition-all duration-150 ${
                      active
                        ? 'bg-primary-500 text-white shadow-soft'
                        : 'text-ink-secondary hover:text-ink-primary'
                    }`}
                    title={meta.desc}
                    type="button"
                  >
                    <span className="mr-1">{meta.icon}</span>
                    {meta.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="text-[11px] text-ink-tertiary uppercase tracking-wider mb-1.5 font-medium">
              需求描述
            </div>
            <textarea
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              placeholder={
                subtype === 'procedure'
                  ? '例如：写一个存储过程，归档一年前的订单到 orders_archive'
                  : '例如：按月统计各区域销售额'
              }
              rows={5}
              className="input-base resize-none"
            />
          </div>
          <button
            onClick={generate}
            disabled={busy || !requirement.trim()}
            className="btn-primary w-full"
            type="button"
          >
            {busy ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full bg-white animate-pulse"
                  style={{ animationDelay: '0.15s' }}
                />
                <span
                  className="inline-block w-1.5 h-1.5 rounded-full bg-white animate-pulse"
                  style={{ animationDelay: '0.3s' }}
                />
                <span>生成中…</span>
              </span>
            ) : (
              <>✨ 生成脚本</>
            )}
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto">
          <div className="px-4 py-2 text-[11px] font-semibold text-ink-tertiary uppercase tracking-wider border-b border-edge-subtle sticky top-0 bg-surface-1 z-10">
            历史
          </div>
          {history.length === 0 && (
            <div className="px-4 py-3 text-xs text-ink-muted">尚无历史</div>
          )}
          <div className="p-2 space-y-1.5">
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => loadFromHistory(h.result)}
                className="card card-hover w-full text-left px-2.5 py-2 text-xs"
                type="button"
              >
                <div className="truncate text-ink-primary">{h.requirement}</div>
                <div className="text-ink-tertiary mt-1 font-mono text-[10px] flex items-center gap-1.5">
                  <span className="px-1 py-0.5 rounded bg-surface-2">{h.result.script_subtype}</span>
                  <span>·</span>
                  <span>{h.result.elapsed_ms}ms</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 min-w-0 min-h-0 flex flex-col">
        <div className="flex-1 min-h-0 flex flex-col">
          <SqlEditor
            value={scriptCode}
            onChange={setScriptCode}
            language={editorLang}
            onFormat={format}
            onExecute={executePreview}
            onExport={exportSql}
          />
        </div>

        <div className="border-t border-edge-subtle bg-surface-1 p-2.5 space-y-2">
          <div className="flex items-center gap-2">
            <input
              value={refine}
              onChange={(e) => setRefine(e.target.value)}
              placeholder="修改意见：例如 '加个错误处理'、'改成 CTE'"
              className="input-base flex-1"
              onKeyDown={(e) => {
                if (e.key === 'Enter') doRefine();
              }}
            />
            <button
              onClick={doRefine}
              disabled={busy || !refine.trim() || !scriptCode.trim()}
              className="btn-outline"
              type="button"
            >
              ↻ Refine
            </button>
          </div>

          {exportMsg && (
            <div
              className={`text-xs px-3 py-1.5 rounded-md animate-fade-in ${
                exportMsg.startsWith('✓')
                  ? 'bg-success/10 text-success border border-success/30'
                  : 'bg-danger/10 text-danger border border-danger/30'
              }`}
            >
              {exportMsg}
            </div>
          )}

          {previewError && (
            <div className="text-xs px-3 py-1.5 rounded-md bg-warning/10 text-warning border border-warning/30">
              {previewError}
            </div>
          )}

          {preview && preview.columns.length > 0 && (
            <div className="max-h-60 overflow-auto card">
              <table className="min-w-full text-xs">
                <thead className="sticky top-0 z-10 bg-surface-1">
                  <tr>
                    {preview.columns.map((c) => (
                      <th
                        key={c}
                        className="px-2.5 py-1.5 text-left font-medium text-ink-secondary text-[10px] uppercase tracking-wider border-b border-edge"
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.slice(0, 100).map((r, i) => (
                    <tr key={i} className="hover:bg-surface-2/60 transition-colors">
                      {r.map((cell, j) => (
                        <td key={j} className="px-2.5 py-1 border-b border-edge-subtle text-ink-primary">
                          {cell === null || cell === undefined || cell === '' ? (
                            <span className="text-ink-muted">—</span>
                          ) : (
                            String(cell)
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {showSchema && (
        <div className="w-[260px] shrink-0 border-l border-edge-subtle bg-surface-1 flex flex-col min-h-0">
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
    </div>
  );
}
