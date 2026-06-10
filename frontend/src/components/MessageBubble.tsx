import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage } from '../types';

interface Props {
  message: ChatMessage;
  /**
   * User preference: when true, completed messages render the thinking
   * block open by default. When false, the thinking block is NOT
   * rendered at all on completed messages — a small "查看思考过程"
   * link at the bottom lets the user open it on demand. The streaming
   * phase always shows the block regardless of this setting.
   */
  showThinking?: boolean;
}

const THINK_TAG_RE = /<think>[\s\S]*?<\/think>/gi;

function stripThinkTags(text: string): string {
  return text.replace(THINK_TAG_RE, '').trim();
}

function ThinkingBlock({
  content,
  forceOpen = false,
  defaultOpen = false,
}: {
  content: string;
  forceOpen?: boolean;
  defaultOpen?: boolean;
}) {
  const [userToggled, setUserToggled] = useState<boolean | null>(null);
  const open = forceOpen
    ? true
    : userToggled !== null
    ? userToggled
    : defaultOpen;
  if (!content) return null;
  const preview = content.split('\n')[0].slice(0, 60);
  return (
    <div className="mt-2 pt-2 border-t border-edge-subtle min-w-0 overflow-hidden animate-fade-in">
      <button
        onClick={() => setUserToggled(!open)}
        className="flex items-center gap-1.5 text-xs text-ink-tertiary hover:text-ink-primary w-full min-w-0 text-left transition-colors"
        type="button"
      >
        <span
          className={`inline-block transition-transform duration-200 shrink-0 ${
            open ? 'rotate-90' : ''
          }`}
        >
          ▶
        </span>
        <span className="shrink-0">💭 思考过程</span>
        {!open && (
          <span className="text-ink-muted truncate min-w-0 flex-1">
            — {preview}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-1.5 text-xs text-ink-secondary bg-surface-2 border border-edge-subtle rounded-md px-2.5 py-1.5 whitespace-pre-wrap break-words max-h-64 overflow-y-auto max-w-full">
          {content}
        </div>
      )}
    </div>
  );
}

export function MessageBubble({ message, showThinking = false }: Props) {
  const isUser = message.role === 'user';
  const [revealed, setRevealed] = useState(false);

  const displayContent = stripThinkTags(message.content || '');
  const thinking = message.thinking;
  const isStreaming = !!message.pending;
  const shouldRender = isStreaming || showThinking || revealed;

  return (
    <div className={`flex animate-fade-in ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] min-w-0 rounded-2xl px-3.5 py-2.5 text-sm overflow-hidden transition-all ${
          isUser
            ? 'text-ink-inverse shadow-soft'
            : message.error
            ? 'bg-danger/10 text-danger border border-danger/30'
            : 'card text-ink-primary'
        }`}
        style={
          isUser
            ? {
                backgroundImage: `linear-gradient(135deg, rgb(var(--c-primary-500)), rgb(var(--c-accent-500)))`,
              }
            : undefined
        }
      >
        {message.error ? (
          <div className="whitespace-pre-wrap break-words">⚠️ {message.error}</div>
        ) : isUser ? (
          <div className="whitespace-pre-wrap break-words leading-relaxed">
            {displayContent}
          </div>
        ) : (
          <div className="markdown-body break-words leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                pre: ({ children }) => (
                  <pre className="bg-surface-0 text-ink-primary border border-edge-subtle rounded-md px-3 py-2 my-2 text-xs overflow-x-auto font-mono">
                    {children}
                  </pre>
                ),
                code: ({ className, children, ...rest }) => {
                  const isBlock = /language-/.test(className || '');
                  if (isBlock) {
                    return <code className={className} {...rest}>{children}</code>;
                  }
                  return (
                    <code
                      className="bg-surface-2 text-ink-primary border border-edge-subtle rounded px-1 py-0.5 text-xs font-mono"
                      {...rest}
                    >
                      {children}
                    </code>
                  );
                },
                table: ({ children }) => (
                  <div className="my-2 overflow-x-auto">
                    <table className="border-collapse border border-edge text-xs">
                      {children}
                    </table>
                  </div>
                ),
                th: ({ children }) => (
                  <th className="border border-edge bg-surface-2 px-2 py-1 text-left font-semibold">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="border border-edge px-2 py-1">{children}</td>
                ),
                ul: ({ children }) => <ul className="list-disc pl-5 my-1 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-5 my-1 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                p: ({ children }) => <p className="my-1.5 leading-relaxed">{children}</p>,
                h1: ({ children }) => <h1 className="text-base font-semibold mt-2 mb-1">{children}</h1>,
                h2: ({ children }) => <h2 className="text-sm font-semibold mt-2 mb-1">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-semibold mt-1.5 mb-0.5">{children}</h3>,
                a: ({ children, href }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary-500 hover:underline"
                  >
                    {children}
                  </a>
                ),
                strong: ({ children }) => <strong className="font-semibold text-ink-primary">{children}</strong>,
                em: ({ children }) => <em className="italic">{children}</em>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-edge-strong pl-2 my-1 text-ink-secondary">
                    {children}
                  </blockquote>
                ),
              }}
            >
              {displayContent}
            </ReactMarkdown>
          </div>
        )}
        {thinking && shouldRender && (
          <ThinkingBlock
            content={thinking}
            forceOpen={isStreaming}
            defaultOpen={showThinking}
          />
        )}
        {thinking && !shouldRender && (
          <button
            onClick={() => setRevealed(true)}
            className="mt-1.5 text-[11px] text-ink-tertiary hover:text-primary-500 transition-colors"
            type="button"
          >
            💭 查看思考过程
          </button>
        )}
        {message.pending && !thinking && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-ink-tertiary">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" style={{ animationDelay: '0.15s' }} />
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" style={{ animationDelay: '0.3s' }} />
            <span>正在思考…</span>
          </div>
        )}
      </div>
    </div>
  );
}
