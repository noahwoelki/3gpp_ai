import { useEffect, useState } from "react";
import { fetchClause, fetchTable } from "../api";
import type { Block, Clause, Source, Table } from "../types";

type Props = { source: Source; onClose: () => void };

// Shows the full clause or table behind a source, with the retrieved part highlighted
export default function SourceViewer({ source, onClose }: Props) {
  const isTable = source.table_id !== null && source.kind !== "text";
  const [mode, setMode] = useState<"table" | "clause">(isTable ? "table" : "clause");
  const [clause, setClause] = useState<Clause | null>(null);
  const [table, setTable] = useState<Table | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    if (source.kind === "glossary") return;
    if (mode === "table" && source.table_id) {
      fetchTable(source.spec, source.release, source.table_id).then(setTable, (e) => setError(String(e)));
    } else {
      fetchClause(source.spec, source.release, source.clause_id).then(setClause, (e) =>
        setError(String(e)),
      );
    }
  }, [source, mode]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 p-6" onClick={onClose}>
      <div
        className="flex max-h-full w-full max-w-4xl flex-col rounded-lg bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-4 border-b border-slate-200 px-5 py-3">
          <div>
            <div className="text-sm font-semibold text-blue-800">{source.citation}</div>
            <div className="text-base font-medium text-slate-900">{source.title}</div>
            {clause && mode === "clause" && (
              <div className="text-xs text-slate-500">{clause.path.join(" > ")}</div>
            )}
          </div>
          <div className="ml-auto flex gap-2">
            {isTable && (
              <button
                className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50"
                onClick={() => setMode(mode === "table" ? "clause" : "table")}
              >
                {mode === "table" ? "Show whole clause" : "Show table"}
              </button>
            )}
            <button className="rounded px-2 py-1 text-slate-500 hover:bg-slate-100" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>
        <div className="overflow-auto px-5 py-4 text-sm">
          {error && <p className="text-red-600">{error}</p>}
          {source.kind === "glossary" && <p>{source.content}</p>}
          {mode === "table" && table && (
            <>
              <p className="mb-2 text-xs font-medium text-slate-600">{table.caption}</p>
              <TableView
                rows={table.rows}
                headerRows={table.header_rows}
                highlight={[source.row_start ?? null, source.row_end ?? null]}
              />
            </>
          )}
          {mode === "clause" && clause && (
            <ClauseView
              blocks={clause.blocks}
              highlight={isTable ? [null, null] : [source.block_start ?? null, source.block_end ?? null]}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function inRange(index: number, [start, end]: [number | null, number | null]) {
  return start !== null && end !== null && index >= start && index <= end;
}

function TableView({
  rows,
  headerRows,
  highlight,
}: {
  rows: string[][];
  headerRows: number;
  highlight: [number | null, number | null];
}) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead>
        {rows.slice(0, headerRows).map((row, i) => (
          <tr key={i} className="bg-slate-100">
            {row.map((cell, j) => (
              <th key={j} className="border border-slate-200 px-2 py-1 text-left font-medium">
                {cell}
              </th>
            ))}
          </tr>
        ))}
      </thead>
      <tbody>
        {rows.slice(headerRows).map((row, i) => {
          const index = i + headerRows; // row ranges count from the top of the table
          const marked = inRange(index, highlight);
          const fullWidth = new Set(row).size === 1; // NOTE or title row spanning the table
          return (
            <tr key={index} className={marked ? "bg-yellow-100" : ""}>
              {fullWidth ? (
                <td colSpan={row.length} className="border border-slate-200 px-2 py-1 text-slate-600">
                  {row[0]}
                </td>
              ) : (
                row.map((cell, j) => (
                  <td key={j} className="border border-slate-200 px-2 py-1 align-top">
                    {cell}
                  </td>
                ))
              )}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

// 3GPP paragraph styles: B1..B5 are list levels, NO/NW are notes, TH/TF captions
function paragraphStyle(style: string) {
  const level = style.match(/^B(\d)$/);
  if (level) return { paddingLeft: `${Number(level[1]) * 1.25}rem` };
  return {};
}

function ClauseView({ blocks, highlight }: { blocks: Block[]; highlight: [number | null, number | null] }) {
  if (blocks.length === 0) {
    return <p className="text-slate-400">This clause has no text of its own, see its subclauses.</p>;
  }
  return (
    <div className="space-y-2">
      {blocks.map((block, index) => {
        const marked = inRange(index, highlight) ? "rounded bg-yellow-100 px-1" : "";
        if (block.type === "table") {
          return (
            <div key={index} className={`my-3 overflow-x-auto ${marked}`}>
              <TableView rows={block.rows} headerRows={block.header_rows} highlight={[null, null]} />
            </div>
          );
        }
        if (block.style === "NO" || block.style === "NW") {
          return (
            <p key={index} className={`border-l-2 border-slate-300 pl-3 text-xs text-slate-600 ${marked}`}>
              {block.text}
            </p>
          );
        }
        if (block.style === "TH" || block.style === "TF") {
          return (
            <p key={index} className={`text-center text-xs font-medium text-slate-600 ${marked}`}>
              {block.text}
            </p>
          );
        }
        return (
          <p key={index} style={paragraphStyle(block.style)} className={marked}>
            {block.text}
          </p>
        );
      })}
    </div>
  );
}
