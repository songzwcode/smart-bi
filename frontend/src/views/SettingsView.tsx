import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store/useStore';
import { ConnectionDialog } from '../components/ConnectionDialog';
import { useTheme, type ThemeId } from '../theme/ThemeProvider';

type ResolvedId = 'light' | 'dark-tech' | 'dark-neon';

const THEME_OPTIONS: Array<{
  id: ResolvedId;
  label: string;
  desc: string;
  preview: { bg: string; surface: string; primary: string; accent: string; text: string };
}> = [
  {
    id: 'light',
    label: '浅色',
    desc: '清爽明亮，办公环境',
    preview: { bg: '#F8FAFC', surface: '#FFFFFF', primary: '#6366F1', accent: '#0EA5E9', text: '#0F172A' },
  },
  {
    id: 'dark-tech',
    label: '深色科技',
    desc: '深邃蓝灰，青色高亮',
    preview: { bg: '#090D16', surface: '#111827', primary: '#0EA5E9', accent: '#14B8A6', text: '#F1F5F9' },
  },
  {
    id: 'dark-neon',
    label: '深色霓虹',
    desc: '紫黑底，粉紫渐变',
    preview: { bg: '#0D071A', surface: '#160E2A', primary: '#A855F7', accent: '#EC4899', text: '#F5F3FF' },
  },
];

export function SettingsView() {
  const health = useStore((s) => s.health);
  const llmInfo = useStore((s) => s.llmInfo);
  const setLlmInfo = useStore((s) => s.setLlmInfo);
  const showThinking = useStore((s) => s.showThinking);
  const setShowThinking = useStore((s) => s.setShowThinking);
  const [showConn, setShowConn] = useState(false);

  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [apiKey, setApiKey] = useState('');
  const [customUrl, setCustomUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const { theme, setTheme, resolved } = useTheme();

  const [persisted, setPersisted] = useState<Awaited<
    ReturnType<typeof api.getPersistedSettings>
  > | null>(null);
  const [persistedTick, setPersistedTick] = useState(0);

  useEffect(() => {
    let mounted = true;
    api
      .getPersistedSettings()
      .then((s) => {
        if (!mounted) return;
        setPersisted(s);
        if (s.llm) {
          if (s.llm.provider) setProvider(s.llm.provider);
          if (s.llm.model) setModel(s.llm.model);
          if (s.llm.ollama_url) setOllamaUrl(s.llm.ollama_url);
          if (s.llm.custom_url) setCustomUrl(s.llm.custom_url);
        }
      })
      .catch(() => {});
    return () => {
      mounted = false;
    };
  }, [persistedTick]);

  async function switchLLM() {
    setBusy(true);
    setMsg('');
    try {
      const r = await api.switchLLM({
        provider,
        model: model || undefined,
        ollama_url: provider === 'ollama' ? ollamaUrl : undefined,
        custom_url: provider === 'custom' ? customUrl : undefined,
        api_key: provider !== 'ollama' ? apiKey : undefined,
      });
      setLlmInfo(r);
      setMsg('✓ 已切换并保存到配置（重启后保留）');
      setApiKey('');
      setPersistedTick((n) => n + 1);
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function testLLM() {
    setBusy(true);
    setMsg('');
    try {
      const r = await api.testLLM({
        provider,
        model: model || undefined,
        ollama_url: provider === 'ollama' ? ollamaUrl : undefined,
        custom_url: provider === 'custom' ? customUrl : undefined,
        api_key: provider !== 'ollama' ? apiKey : undefined,
      });
      if (r.ok) {
        setMsg(`✓ 连通 (HTTP ${r.status_code ?? '200'})`);
      } else {
        setMsg(`✗ ${r.error ?? '连接失败'}`);
      }
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function resetPersisted() {
    if (!confirm('确认重置所有保存的配置？下次启动将使用 config.yaml 的默认值。')) return;
    setBusy(true);
    try {
      await api.resetPersistedSettings();
      setMsg('✓ 已清除持久化配置（重启后生效）');
      setPersistedTick((n) => n + 1);
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-surface-0">
      <div className="max-w-3xl mx-auto p-6 space-y-5">
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">⚙️ 设置</h1>
          <p className="text-sm text-ink-tertiary mt-1">
            管理界面外观、数据库连接与 LLM 提供方。
          </p>
        </div>

        {/* Appearance / Theme picker */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🎨</span>
            <h2 className="text-sm font-semibold text-ink-primary">界面外观</h2>
          </div>
          <div className="text-xs text-ink-tertiary mb-3">
            当前：<span className="text-ink-primary font-medium">
              {theme === 'system' ? `跟随系统（${resolved === 'light' ? '浅色' : resolved === 'dark-tech' ? '深色科技' : '深色霓虹'}）` : THEME_OPTIONS.find((t) => t.id === theme)?.label}
            </span>
          </div>

          <div className="grid grid-cols-3 gap-3 mb-4">
            {THEME_OPTIONS.map((t) => {
              const isActive = resolved === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTheme(t.id as ThemeId)}
                  className={`relative text-left rounded-xl border-2 p-3 transition-all duration-200 hover:scale-[1.02] ${
                    isActive
                      ? 'border-primary-500 shadow-glow-sm'
                      : 'border-edge-subtle hover:border-edge'
                  }`}
                  type="button"
                >
                  {isActive && (
                    <span
                      className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full text-white text-[10px] flex items-center justify-center shadow-soft"
                      style={{
                        backgroundImage: `linear-gradient(135deg, rgb(var(--c-primary-500)), rgb(var(--c-accent-500)))`,
                      }}
                    >
                      ✓
                    </span>
                  )}
                  <div
                    className="rounded-lg overflow-hidden border border-black/10 mb-2"
                    style={{ background: t.preview.bg }}
                  >
                    <div
                      className="h-12 flex items-center px-2 gap-1"
                      style={{ background: t.preview.surface, borderBottom: `1px solid ${t.preview.bg}` }}
                    >
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{ background: t.preview.primary }}
                      />
                      <div
                        className="w-2 h-2 rounded-full"
                        style={{ background: t.preview.accent }}
                      />
                      <div
                        className="ml-2 text-[8px] font-mono"
                        style={{ color: t.preview.text }}
                      >
                        {t.id}
                      </div>
                    </div>
                    <div className="h-10 p-1.5 flex gap-1">
                      <div
                        className="h-2 rounded"
                        style={{ background: t.preview.primary, width: '40%' }}
                      />
                      <div
                        className="h-2 rounded opacity-50"
                        style={{ background: t.preview.text, width: '30%' }}
                      />
                    </div>
                  </div>
                  <div className="text-xs font-medium text-ink-primary">{t.label}</div>
                  <div className="text-[10px] text-ink-tertiary mt-0.5">{t.desc}</div>
                </button>
              );
            })}
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-edge-subtle">
            <div>
              <div className="text-xs font-medium text-ink-primary">跟随系统</div>
              <div className="text-[11px] text-ink-tertiary mt-0.5">
                开启后将随 macOS / Windows 浅色 / 深色自动切换主题
              </div>
            </div>
            <button
              onClick={() => setTheme(theme === 'system' ? resolved : 'system')}
              className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${
                theme === 'system' ? 'bg-primary-500' : 'bg-surface-3'
              }`}
              type="button"
              aria-pressed={theme === 'system'}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-soft transition-transform duration-200 ${
                  theme === 'system' ? 'translate-x-5' : ''
                }`}
              />
            </button>
          </div>
        </div>

        {/* UI preferences */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🧠</span>
            <h2 className="text-sm font-semibold text-ink-primary">思考过程</h2>
          </div>
          <label className="flex items-start gap-3 text-sm text-ink-primary cursor-pointer group">
            <button
              onClick={async () => {
                const v = !showThinking;
                setShowThinking(v);
                try {
                  await api.setUiPref('show_thinking', v);
                } catch (err) {
                  console.error('Failed to persist show_thinking', err);
                }
              }}
              className={`relative mt-0.5 w-11 h-6 rounded-full transition-colors duration-200 shrink-0 ${
                showThinking ? 'bg-primary-500' : 'bg-surface-3'
              }`}
              type="button"
              aria-pressed={showThinking}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-soft transition-transform duration-200 ${
                  showThinking ? 'translate-x-5' : ''
                }`}
              />
            </button>
            <span className="flex-1">
              <span className="font-medium">默认显示 AI 思考过程</span>
              <span className="block text-xs text-ink-tertiary mt-0.5 leading-relaxed">
                关闭时，思考过程在生成完毕后保持隐藏（仅显示小"💭 查看思考过程"链接，需要时手动展开）。开启则默认展开。
              </span>
            </span>
          </label>
        </div>

        {/* Status card */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">📊</span>
            <h2 className="text-sm font-semibold text-ink-primary">系统状态</h2>
          </div>
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <span className="text-ink-tertiary text-xs uppercase tracking-wider">应用</span>
            <span className="text-ink-primary font-medium">
              {health?.app} <span className="text-ink-tertiary font-normal">v{health?.version}</span>
            </span>
            <span className="text-ink-tertiary text-xs uppercase tracking-wider">数据库</span>
            <span className="text-ink-primary font-mono text-xs">{health?.db_dialect}</span>
            <span className="text-ink-tertiary text-xs uppercase tracking-wider">当前 LLM</span>
            <span className="text-ink-primary">
              {llmInfo?.current_provider || '未配置'}
              {llmInfo?.current_model ? (
                <span className="text-ink-tertiary font-mono text-xs"> · {llmInfo.current_model}</span>
              ) : null}
            </span>
          </div>
        </div>

        {/* Database */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🗄️</span>
            <h2 className="text-sm font-semibold text-ink-primary">数据库连接</h2>
            <button
              onClick={() => setShowConn(true)}
              className="ml-auto btn-primary text-xs"
              type="button"
            >
              切换 / 新建
            </button>
          </div>
          <div className="text-xs text-ink-tertiary font-mono break-all bg-surface-2 px-2.5 py-1.5 rounded-md">
            {health?.db_url || '—'}
          </div>
        </div>

        {/* LLM */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">🤖</span>
            <h2 className="text-sm font-semibold text-ink-primary">LLM 提供方</h2>
          </div>

          <div className="space-y-3">
            <div>
              <label className="text-xs text-ink-tertiary mb-1 block">Provider</label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="input-base"
              >
                <option value="ollama">Ollama (本地)</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic Claude</option>
                <option value="custom">Custom / OpenAI-Compatible</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-ink-tertiary mb-1 block">
                模型 <span className="text-ink-muted">(可选，留空使用默认)</span>
              </label>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={
                  provider === 'ollama'
                    ? 'qwen2.5-coder:14b'
                    : provider === 'openai'
                    ? 'gpt-4o'
                    : provider === 'anthropic'
                    ? 'claude-3-5-sonnet-20241022'
                    : provider === 'custom'
                    ? 'minimax-m3'
                    : ''
                }
                className="input-base font-mono"
              />
            </div>

            {provider === 'ollama' && (
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">Ollama 地址</label>
                <input
                  value={ollamaUrl}
                  onChange={(e) => setOllamaUrl(e.target.value)}
                  className="input-base font-mono"
                />
              </div>
            )}

            {provider === 'custom' && (
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">
                  Base URL <span className="text-ink-muted">(例如 https://api.example.com/v1)</span>
                </label>
                <input
                  value={customUrl}
                  onChange={(e) => setCustomUrl(e.target.value)}
                  placeholder="https://api.example.com/v1"
                  className="input-base font-mono"
                />
                <p className="text-[11px] text-ink-tertiary mt-1.5 leading-relaxed">
                  任何 OpenAI 兼容的 HTTP 端点：vLLM / llama.cpp server / LiteLLM / OpenRouter / OneAPI / 自建网关等。
                </p>
              </div>
            )}

            {provider !== 'ollama' && (
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">API Key</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    provider === 'openai' ? 'sk-...' :
                    provider === 'anthropic' ? 'sk-ant-...' :
                    'Bearer Token (可选)'
                  }
                  className="input-base font-mono"
                />
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button
                onClick={switchLLM}
                disabled={busy}
                className="btn-primary"
                type="button"
              >
                {busy ? '切换中…' : '↻ 切换 LLM'}
              </button>
              <button
                onClick={testLLM}
                disabled={busy}
                className="btn-outline"
                type="button"
              >
                🔍 测试连通
              </button>
            </div>
            {msg && (
              <div
                className={`text-sm px-3 py-2 rounded-md animate-fade-in ${
                  msg.startsWith('✓')
                    ? 'bg-success/10 text-success border border-success/30'
                    : 'bg-danger/10 text-danger border border-danger/30'
                }`}
              >
                {msg}
              </div>
            )}
          </div>

          {llmInfo?.available && llmInfo.available.length > 0 && (
            <div className="mt-4 pt-3 border-t border-edge-subtle">
              <div className="text-[11px] font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
                可用状态
              </div>
              <ul className="space-y-1.5 text-xs">
                {llmInfo.available.map((p) => (
                  <li key={p.provider} className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        p.available ? 'bg-success animate-pulse-glow' : 'bg-danger'
                      }`}
                      style={{ color: p.available ? 'rgb(16 185 129)' : 'rgb(244 63 94)' }}
                    />
                    <span className="font-medium text-ink-primary">{p.provider}</span>
                    {p.models && (
                      <span className="text-ink-tertiary truncate">
                        ({p.models.length} 个模型: {p.models.slice(0, 3).join(', ')}
                        {p.models.length > 3 ? '…' : ''})
                      </span>
                    )}
                    {p.error && <span className="text-danger">— {p.error}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Persistence card */}
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-base">💾</span>
            <h2 className="text-sm font-semibold text-ink-primary">持久化配置</h2>
            <span className="ml-auto text-[11px] text-ink-tertiary font-mono">
              ~/.smart-bi/user_settings.json
            </span>
          </div>
          {!persisted?.has_persisted ? (
            <p className="text-xs text-ink-tertiary">
              尚未保存任何配置。切换 LLM 或连接数据库后会自动写入。
            </p>
          ) : (
            <div className="space-y-2 text-xs">
              {persisted.llm && (
                <div className="flex gap-2">
                  <span className="w-24 text-ink-tertiary shrink-0">LLM</span>
                  <span className="text-ink-primary font-mono break-all">
                    {persisted.llm.provider}
                    {persisted.llm.model ? ` · ${persisted.llm.model}` : ''}
                    {persisted.llm.ollama_url ? ` · ${persisted.llm.ollama_url}` : ''}
                    {persisted.llm.custom_url ? ` · ${persisted.llm.custom_url}` : ''}
                  </span>
                </div>
              )}
              {persisted.db && (
                <div className="flex gap-2">
                  <span className="w-24 text-ink-tertiary shrink-0">Database</span>
                  <span className="text-ink-primary font-mono break-all">
                    {String(persisted.db.db_type || '')}
                    {persisted.db.db_type === 'sqlite' && persisted.db.file_path
                      ? ` · ${String(persisted.db.file_path)}`
                      : persisted.db.host
                      ? ` · ${persisted.db.host}:${persisted.db.port ?? ''}/${persisted.db.database ?? ''}`
                      : ''}
                  </span>
                </div>
              )}
            </div>
          )}
          <div className="mt-3 pt-3 border-t border-edge-subtle">
            <button
              onClick={resetPersisted}
              disabled={busy}
              className="btn-danger text-xs"
              type="button"
            >
              🗑 清除持久化配置
            </button>
          </div>
        </div>

        <div className="text-[11px] text-ink-muted text-center py-4">
          Smart BI v{health?.version ?? '0.1.0'} · 桌面端
        </div>
      </div>

      {showConn && <ConnectionDialog onClose={() => setShowConn(false)} />}
    </div>
  );
}
