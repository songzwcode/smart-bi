import Editor, { OnMount } from '@monaco-editor/react';
import type * as monacoTypes from 'monaco-editor';
import { useStore } from '../store/useStore';
import { api } from '../api/client';
import { useTheme } from '../theme/ThemeProvider';
import { useState } from 'react';

interface Props {
  value: string;
  onChange: (v: string) => void;
  language?: string;
  height?: number | string;
  onExecute?: () => Promise<void>;
  onFormat?: () => Promise<void>;
  onExport?: () => Promise<void>;
}

export function SqlEditor({
  value,
  onChange,
  language = 'sql',
  height = '100%',
  onExecute,
  onFormat,
  onExport,
}: Props) {
  const schema = useStore((s) => s.schema);
  const { resolved } = useTheme();
  const isDark = resolved !== 'light';
  const [violations, setViolations] = useState<Array<{ rule: string; line: number; description: string }>>([]);

  const handleMount: OnMount = (editor, monaco) => {
    monaco.languages.registerCompletionItemProvider('sql', {
      provideCompletionItems: (model: monacoTypes.editor.ITextModel, position: monacoTypes.Position) => {
        const word = model.getWordUntilPosition(position);
        const range: monacoTypes.IRange = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };
        const suggestions: monacoTypes.languages.CompletionItem[] = [];
        if (schema) {
          for (const t of schema.tables) {
            suggestions.push({
              label: t.name,
              kind: monaco.languages.CompletionItemKind.Class,
              insertText: t.name,
              range,
              detail: `table (${t.row_count} rows)`,
            });
            for (const c of t.columns) {
              suggestions.push({
                label: `${t.name}.${c.name}`,
                kind: monaco.languages.CompletionItemKind.Field,
                insertText: `${t.name}.${c.name}`,
                range,
                detail: c.type,
              });
            }
          }
        }
        return { suggestions };
      },
    });
  };

  async function lint() {
    if (!value.trim()) {
      setViolations([]);
      return;
    }
    try {
      const r = await api.lintSQL(value);
      setViolations(r.violations || []);
    } catch (e) {
      console.error(e);
    }
  }

  const ToolbarBtn = ({
    onClick,
    children,
  }: { onClick?: () => void; children: React.ReactNode }) => (
    <button
      onClick={onClick}
      className="px-2.5 py-1 rounded-md text-xs text-ink-secondary hover:text-ink-primary hover:bg-surface-2 transition-colors"
      type="button"
    >
      {children}
    </button>
  );

  return (
    <div className="flex flex-col h-full bg-surface-0">
      <div className="flex items-center gap-1 px-2 py-1.5 border-b border-edge-subtle bg-surface-1 text-xs">
        <span className="font-mono font-semibold text-ink-primary text-[10px] uppercase tracking-wider px-1.5">
          SQL
        </span>
        <span className="w-px h-3.5 bg-edge-subtle" />
        <ToolbarBtn onClick={onFormat}>✨ 格式化</ToolbarBtn>
        <ToolbarBtn onClick={onExecute}>▶ 执行预览</ToolbarBtn>
        <ToolbarBtn onClick={onExport}>⬇ 导出 .sql</ToolbarBtn>
        <ToolbarBtn onClick={lint}>🔍 检查</ToolbarBtn>
        <span className="ml-auto text-ink-tertiary font-mono">{value.length} chars</span>
      </div>
      <div className="flex-1 min-h-0">
        <Editor
          height={height}
          defaultLanguage={language}
          language={language}
          value={value}
          onChange={(v) => onChange(v ?? '')}
          onMount={handleMount}
          theme={isDark ? 'vs-dark' : 'vs'}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            tabSize: 2,
            wordWrap: 'on',
            automaticLayout: true,
            scrollBeyondLastLine: false,
          }}
        />
      </div>
      {violations.length > 0 && (
        <div className="border-t border-warning/30 bg-warning/10 max-h-32 overflow-y-auto text-xs">
          {violations.map((v, i) => (
            <div key={i} className="px-3 py-1 text-warning border-b border-warning/10 last:border-b-0">
              <span className="font-mono mr-2 text-warning/80">L{v.line}</span>
              <span className="font-semibold mr-1">{v.rule}</span>
              {v.description}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
