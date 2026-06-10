import { useState } from 'react';
import { api } from '../api/client';
import { useStore } from '../store/useStore';
import type { ConnectionConfigFE } from '../types';

interface Props {
  onClose: () => void;
}

export function ConnectionDialog({ onClose }: Props) {
  const setSchema = useStore((s) => s.setSchema);
  const setHealth = useStore((s) => s.setHealth);
  const [dbType, setDbType] = useState<ConnectionConfigFE['db_type']>('sqlite');
  const [filePath, setFilePath] = useState('examples/sample.db');
  const [host, setHost] = useState('127.0.0.1');
  const [port, setPort] = useState<number>(3306);
  const [user, setUser] = useState('root');
  const [password, setPassword] = useState('');
  const [database, setDatabase] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  async function test() {
    setBusy(true);
    setMsg('');
    try {
      const cfg = collect();
      const r = await api.testConnection(cfg, true);
      setMsg(r.ok ? `✓ OK (${r.dialect})` : `✗ ${r.error}`);
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    setBusy(true);
    setMsg('');
    try {
      const cfg = collect();
      const r = await api.connect(cfg, true);
      if (r.ok) {
        const [s, h] = await Promise.all([api.getSchema(true), api.health()]);
        setSchema(s);
        setHealth(h);
        onClose();
      } else {
        setMsg(`✗ failed`);
      }
    } catch (e) {
      setMsg(`✗ ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  }

  function collect(): ConnectionConfigFE {
    if (dbType === 'sqlite') {
      return { db_type: 'sqlite', file_path: filePath };
    }
    return { db_type: dbType, host, port, user, password, database };
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      {/* Backdrop with blur */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div className="relative card rounded-3xl shadow-elevated w-[480px] max-w-full p-5 animate-slide-up">
        <div className="flex items-center mb-4">
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm"
              style={{
                backgroundImage: `linear-gradient(135deg, rgb(var(--c-primary-500)), rgb(var(--c-accent-500)))`,
              }}
            >
              🔌
            </div>
            <h2 className="text-base font-semibold text-ink-primary">连接数据库</h2>
          </div>
          <button
            onClick={onClose}
            className="ml-auto btn-ghost w-7 h-7 p-0 text-base"
            aria-label="关闭"
            type="button"
          >
            ✕
          </button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-ink-tertiary mb-1 block">数据库类型</label>
            <select
              value={dbType}
              onChange={(e) => setDbType(e.target.value as ConnectionConfigFE['db_type'])}
              className="input-base"
            >
              <option value="sqlite">SQLite</option>
              <option value="mysql">MySQL</option>
              <option value="postgres">PostgreSQL</option>
            </select>
          </div>

          {dbType === 'sqlite' ? (
            <div>
              <label className="text-xs text-ink-tertiary mb-1 block">文件路径</label>
              <input
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="examples/sample.db 或 /abs/path/to.db"
                className="input-base font-mono"
              />
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">Host</label>
                <input
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  className="input-base"
                />
              </div>
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">Port</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(parseInt(e.target.value || '0'))}
                  className="input-base"
                />
              </div>
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">User</label>
                <input
                  value={user}
                  onChange={(e) => setUser(e.target.value)}
                  className="input-base"
                />
              </div>
              <div>
                <label className="text-xs text-ink-tertiary mb-1 block">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-base"
                />
              </div>
              <div className="col-span-2">
                <label className="text-xs text-ink-tertiary mb-1 block">Database</label>
                <input
                  value={database}
                  onChange={(e) => setDatabase(e.target.value)}
                  className="input-base"
                />
              </div>
            </div>
          )}

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

          <div className="flex justify-end gap-2 pt-3 border-t border-edge-subtle">
            <button onClick={onClose} className="btn-ghost" type="button">
              取消
            </button>
            <button onClick={test} disabled={busy} className="btn-outline" type="button">
              测试
            </button>
            <button onClick={connect} disabled={busy} className="btn-primary" type="button">
              {busy ? '连接中…' : '连接'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
