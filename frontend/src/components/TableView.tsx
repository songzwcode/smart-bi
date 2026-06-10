interface Props {
  columns: string[];
  rows: Array<Array<unknown>>;
  total?: number;
  truncated?: boolean;
}

export function TableView({ columns, rows, total, truncated }: Props) {
  if (!columns.length) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-ink-tertiary text-sm gap-2 animate-fade-in">
        <div className="text-3xl opacity-50">📭</div>
        <div>无数据</div>
      </div>
    );
  }

  // Heuristic: a column is treated as numeric if every non-null value parses
  // as a finite number. This drives the right-align treatment below.
  const isNumericColumn = (idx: number): boolean => {
    for (const r of rows) {
      const v = r[idx];
      if (v === null || v === undefined || v === '') continue;
      const n = typeof v === 'number' ? v : Number(v);
      if (!Number.isFinite(n)) return false;
    }
    return true;
  };

  return (
    <div className="h-full overflow-auto bg-surface-0">
      <table className="min-w-full text-sm border-separate border-spacing-0">
        <thead className="sticky top-0 z-10">
          <tr>
            {columns.map((c) => {
              const numeric = isNumericColumn(columns.indexOf(c));
              return (
                <th
                  key={c}
                  className={`px-3 py-2 font-medium text-ink-secondary text-xs uppercase tracking-wider whitespace-nowrap border-b border-edge bg-surface-1 ${
                    numeric ? 'text-right' : 'text-left'
                  }`}
                >
                  {c}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={i}
              className="group hover:bg-surface-2/60 transition-colors duration-150"
            >
              {r.map((cell, j) => {
                const numeric = isNumericColumn(j);
                return (
                  <td
                    key={j}
                    className={`relative px-3 py-1.5 border-b border-edge-subtle text-ink-primary ${
                      numeric ? 'text-right tabular-nums font-mono' : ''
                    }`}
                  >
                    {/* Left-edge accent bar on hover */}
                    <span
                      aria-hidden
                      className="absolute left-0 top-0 bottom-0 w-[2px] bg-primary-500 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
                    />
                    {cell === null || cell === undefined || cell === '' ? (
                      <span className="text-ink-muted">—</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <div className="text-xs text-warning px-3 py-1.5 bg-warning/10 border-t border-warning/30 animate-fade-in">
          仅显示前 {rows.length} 行（总计 {total ?? rows.length} 行）
        </div>
      )}
    </div>
  );
}
