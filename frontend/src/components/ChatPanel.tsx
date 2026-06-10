import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { useStore, newId } from '../store/useStore';
import { api } from '../api/client';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage, QueryResponse } from '../types';

const SUGGESTIONS = [
  '显示销售额最高的前 10 个客户',
  '统计每个区域最近 30 天的订单数',
  '查询所有库存不足 50 件的产品',
  '按品类统计销售额并画饼图',
];

interface StreamEvent {
  type: 'think' | 'content' | 'phase' | 'plan' | 'plan_ready' | 'step' | 'step_done' | 'final' | 'error';
  text?: string;
  phase?: string;
  step_id?: number;
  description?: string;
  plan?: unknown;
  step?: Record<string, unknown>;
  result?: QueryResponse;
  error?: string;
}

async function streamQuery(
  payload: { question: string; chart_type?: string },
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  // Use fetch with ReadableStream since EventSource doesn't support POST.
  const resp = await fetch('/api/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`HTTP ${resp.status}: ${await resp.text().catch(() => '')}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let finalResult: QueryResponse | null = null;
  let sawError = false;
  let errorMsg = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    // SSE spec uses \r\n line endings, but be tolerant of either. Normalize
    // before splitting so a leading \r from the previous event's terminator
    // doesn't break `startsWith('event:')` / `startsWith('data:')` checks.
    const normalized = buf.replace(/\r\n/g, '\n');
    // SSE events are separated by blank lines; one event may span multiple lines.
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
      let parsed: StreamEvent;
      try {
        parsed = JSON.parse(data);
      } catch {
        continue;
      }
      // Map server event name → our internal type
      const ev: StreamEvent = { ...parsed, type: parsed.type || (eventName as StreamEvent['type']) };
      // For the final event, the server sends the QueryResponse directly as
      // the event data. The server uses `final_columns` / `final_rows` but
      // the TS type expects `columns` / `rows` — normalize here so downstream
      // components (TableView, QueryMode header) can read consistent fields.
      if (ev.type === 'final') {
        const p = parsed as unknown as Record<string, unknown>;
        if (p && Array.isArray(p.final_columns)) p.columns = p.final_columns;
        if (p && Array.isArray(p.final_rows)) p.rows = p.final_rows;
        if (!ev.result) {
          ev.result = parsed as unknown as QueryResponse;
        }
      }
      onEvent(ev);
      if (ev.type === 'error') {
        sawError = true;
        errorMsg = ev.error || 'unknown error';
        // Don't keep reading — the onEvent handler already updated the UI.
        try { await reader.cancel(); } catch {}
        break;
      }
      if (ev.type === 'final') {
        // The server sends the QueryResponse directly as the final event
        // data (not wrapped in {type, result}), so the parsed object IS
        // the result. Keep both shapes working for safety.
        finalResult = (ev.result ?? (parsed as unknown as QueryResponse));
      }
    }
    if (sawError) break;
  }
  if (sawError) throw new Error(errorMsg);
  if (!finalResult) throw new Error('Stream ended without final result');
  return finalResult;
}

export function ChatPanel() {
  const messages = useStore((s) => s.queryMessages);
  const addMessage = useStore((s) => s.addQueryMessage);
  const updateLast = useStore((s) => s.updateLastQueryMessage);
  const setLastResult = useStore((s) => s.setLastQueryResult);
  const showThinking = useStore((s) => s.showThinking);

  const [input, setInput] = useState('');
  const [chartType, setChartType] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<string>('');   // 'intent' | 'plan' | 'step' | ''
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length, messages[messages.length - 1]?.pending, messages[messages.length - 1]?.content]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    const userMsg: ChatMessage = { id: newId(), role: 'user', content: text };
    addMessage(userMsg);

    // Assistant message starts with empty content + live-thinking buffer.
    // `thinking` holds concatenated reasoning text across all phases.
    // `thinkingOpen` is true while the agent is running, false once the
    // final result arrives (auto-collapse).
    const pendingMsg: ChatMessage = {
      id: newId(),
      role: 'assistant',
      content: '',
      pending: true,
      thinking: '',
    };
    addMessage(pendingMsg);
    setBusy(true);

    // Mutable accumulator for live updates
    let thinkingBuf = '';
    let contentBuf = '';
    let intentData: Record<string, unknown> = {};
    let planData: Record<string, unknown> = {};
    const stepDatas: Array<Record<string, unknown>> = [];

    const flushUpdate = () => {
      updateLast({
        content: contentBuf,
        thinking: thinkingBuf,
        pending: true,
      });
    };

    try {
      await streamQuery(
        { question: text, chart_type: chartType || undefined },
        (ev) => {
          switch (ev.type) {
            case 'phase':
              setPhase(ev.phase || '');
              break;
            case 'think':
              thinkingBuf += ev.text || '';
              flushUpdate();
              break;
            case 'content':
              contentBuf += ev.text || '';
              flushUpdate();
              break;
            case 'plan':
              planData = (ev.plan as Record<string, unknown>) || planData;
              break;
            case 'step':
              stepDatas.push((ev.step as Record<string, unknown>) || {});
              break;
            case 'final': {
              // Build a final QueryResponse-shaped object from accumulated parts
              const r = ev.result;
              if (r) {
                setLastResult(r);
              }
              // Build a friendly summary message (markdown)
              const summary = r && r.success
                ? (r.rows && r.rows.length > 0
                  ? `**查询成功**，返回 **${r.rows.length}** 行。耗时 ${r.elapsed_ms} ms。\n\n**SQL：**\n\`\`\`sql\n${r.final_sql}\n\`\`\``
                  : `**查询完成（0 行）。**\n\n**SQL：**\n\`\`\`sql\n${r.final_sql}\n\`\`\``)
                : '';
              updateLast({
                content: summary,
                thinking: thinkingBuf,
                pending: false,
                error: r?.error || undefined,
                queryResult: r,
              });
              setPhase('');
              break;
            }
            case 'error':
              updateLast({
                pending: false,
                error: ev.error || 'unknown error',
                content: '',
              });
              setPhase('');
              break;
          }
        },
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      updateLast({ pending: false, error: msg, content: '' });
    } finally {
      setBusy(false);
      setPhase('');
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  }

  const phaseLabel: Record<string, string> = {
    intent: '识别意图…',
    plan: '规划任务…',
    step: '生成 SQL…',
  };
  const phaseHint = phase && busy ? phaseLabel[phase] : '';

  return (
    <div className="flex flex-col h-full min-h-0 bg-surface-0">
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="space-y-3 animate-fade-in">
            <div className="flex items-center gap-2 text-ink-tertiary text-xs uppercase tracking-wider">
              <span className="inline-block w-1 h-3 rounded-sm bg-primary-500" />
              试试这些问题
            </div>
            <div className="grid grid-cols-1 gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-left text-sm card card-hover px-3 py-2.5 text-ink-primary hover:border-primary-500/50 group"
                >
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 mr-2 align-middle transition-transform group-hover:scale-150" />
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} showThinking={showThinking} />
        ))}
        {phaseHint && (
          <div className="flex items-center gap-2 text-xs text-ink-tertiary pl-1 animate-fade-in">
            <span className="inline-flex gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" />
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse"
                style={{ animationDelay: '0.15s' }}
              />
              <span
                className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse"
                style={{ animationDelay: '0.3s' }}
              />
            </span>
            <span className="font-medium text-ink-secondary">{phaseHint}</span>
          </div>
        )}
      </div>

      <div className="border-t border-edge-subtle bg-surface-1/80 backdrop-blur p-3 space-y-2.5">
        {/* Segmented control: chart type */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-ink-tertiary mr-1">图表：</span>
          <div className="inline-flex p-0.5 rounded-lg bg-surface-2 border border-edge-subtle">
            {[
              { v: '', label: '无' },
              { v: 'bar', label: '柱状' },
              { v: 'line', label: '折线' },
              { v: 'pie', label: '饼图' },
              { v: 'scatter', label: '散点' },
            ].map((opt) => {
              const active = chartType === opt.v;
              return (
                <button
                  key={opt.v}
                  onClick={() => setChartType(opt.v)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 ${
                    active
                      ? 'bg-primary-500 text-white shadow-soft'
                      : 'text-ink-tertiary hover:text-ink-primary'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Input row */}
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder="用自然语言提问，例如：显示 2024 年 Q1 各区域销售额"
            rows={2}
            className="flex-1 resize-none input-base focus:shadow-glow-sm"
          />
          <button
            onClick={send}
            disabled={busy || !input.trim()}
            className="btn-primary h-[58px] px-5"
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
              </span>
            ) : (
              <span>发送 ↑</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
