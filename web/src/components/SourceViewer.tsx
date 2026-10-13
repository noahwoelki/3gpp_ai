import { useEffect, useRef, useState } from "react";
import { fetchClause, fetchTable } from "../api";
import { specColor, specName } from "../specs";
import type { Block, Clause, Source, Table } from "../types";
import ClauseTag from "./ClauseTag";

type Props = { source: Source; onClose: () => void };
type Range = [number | null, number | null];

// Shows the full clause or table behind a source, with the retrieved part marked
export default function SourceViewer({ source, onClose }: Props) {
  const isTable = source.table_id !== null && source.kind !== "text";
  const [mode, setMode] = useState<"table" | "clause">(isTable ? "table" : "clause");
  const [clause, setClause] = useState<Clause | null>(null);
  const [table, setTable] = useState<Table | null>(null);
  const [error, setError] = useState<string | null>(null);
  const body = useRef<HTMLDivElement>(null);

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

  // Jump to the marked part once the content is there
  useEffect(() => {
    body.current?.querySelector("[data-marked]")?.scrollIntoView({ block: "center" });
  }, [clause, table, mode]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const color = specColor(source.spec);

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-ink/30 p-6 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="pop relative flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-line bg-card shadow-[0_24px_60px_-20px_rgba(29,27,22,0.45)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="h-1.5 w-full" style={{ backgroundColor: color }} />
        <div className="flex items-start gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <ClauseTag spec={source.spec} release={source.release} clauseId={source.clause_id} size="md" />
              <span className="text-xs text-ink-faint">{specName(source.spec)}</span>
            </div>
            <h3 className="mt-2 font-display text-xl font-semibold leading-tight text-ink">{source.title}</h3>
            {clause && mode === "clause" && clause.path.length > 0 && (
              <div className="mt-1 text-xs text-ink-faint">{clause.path.join("  ›  ")}</div>
            )}
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {isTable && (
              <button
                className="rounded-full border border-line px-3 py-1 text-xs text-ink-soft transition hover:border-ink hover:text-ink"
                onClick={() => setMode(mode === "table" ? "clause" : "table")}
              >
                {mode === "table" ? "Whole clause" : "Just the table"}
              </button>
            )}
            <button
              aria-label="Close"
              className="flex h-8 w-8 items-center justify-center rounded-full text-ink-faint transition hover:rotate-90 hover:bg-paper hover:text-ink"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        </div>

        <div ref={body} className="overflow-auto px-6 py-5 text-sm leading-relaxed">
          {error && <p className="text-red-600">{error}</p>}
          {source.kind === "glossary" && <p className="text-base">{source.content}</p>}
          {mode === "table" && table && (
            <>
              <p className="mb-3 font-display text-sm italic text-ink-soft">{table.caption}</p>
              <TableView
                rows={table.rows}
                headerRows={table.header_rows}
                marked={[source.row_start ?? null, source.row_end ?? null]}
              />
            </>
          )}
          {mode === "clause" && clause && (
            <ClauseView
              blocks={clause.blocks}
              marked={isTable ? [null, null] : [source.block_start ?? null, source.block_end ?? null]}
            />
          )}
          {!error && source.kind !== "glossary" && !(mode === "table" ? table : clause) && (
            <div className="flex items-center gap-2 text-ink-faint">
              <span className="signal-bars">
                <span />
                <span />
                <span />
                <span />
              </span>
              Loading...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function inRange(index: number, [start, end]: Range) {
  return start !== null && end !== null && index >= start && index <= end;
}

function TableView({ rows, headerRows, marked }: { rows: string[][]; headerRows: number; marked: Range }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse text-xs">
        <thead>
          {rows.slice(0, headerRows).map((row, i) => (
            <tr key={i} className="bg-paper-deep">
              {row.map((cell, j) => (
                <th key={j} className="border border-line px-2 py-1.5 text-left font-semibold text-ink">
                  {cell}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {rows.slice(headerRows).map((row, i) => {
            const index = i + headerRows; // row ranges count from the top of the table
            const isMarked = inRange(index, marked);
            const fullWidth = new Set(row).size === 1; // NOTE or title row spanning the table
            return (
              <tr
                key={index}
                data-marked={isMarked || undefined}
                className={isMarked ? "bg-marker/60" : "even:bg-paper/50"}
              >
                {fullWidth ? (
                  <td colSpan={row.length} className="border border-line px-2 py-1.5 text-ink-soft">
                    {row[0]}
                  </td>
                ) : (
                  row.map((cell, j) => (
                    <td key={j} className="border border-line px-2 py-1 align-top">
                      {cell}
                    </td>
                  ))
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// 3GPP paragraph styles: B1..B5 are list levels, NO/NW are notes, TH/TF captions
function listIndent(style: string) {
  const level = style.match(/^B(\d)$/);
  return level ? { paddingLeft: `${Number(level[1]) * 1.25}rem` } : {};
}

function ClauseView({ blocks, marked }: { blocks: Block[]; marked: Range }) {
  if (blocks.length === 0) {
    return (
      <p className="font-display italic text-ink-faint">
        No text in this clause itself, only in its subclauses.
      </p>
    );
  }
  return (
    <div className="space-y-2.5">
      {blocks.map((block, index) => {
        const isMarked = inRange(index, marked);
        const markedProps = isMarked ? { "data-marked": true } : {};
        if (block.type === "table") {
          return (
            <div key={index} {...markedProps} className={`my-4 ${isMarked ? "rounded-lg ring-4 ring-marker/70" : ""}`}>
              <TableView rows={block.rows} headerRows={block.header_rows} marked={[null, null]} />
            </div>
          );
        }
        const text = isMarked ? <span className="marker">{block.text}</span> : block.text;
        if (block.style === "NO" || block.style === "NW") {
          return (
            <p key={index} {...markedProps} className="rounded-r-md border-l-2 border-signal/60 bg-paper/60 py-1 pl-3 text-xs text-ink-soft">
              {text}
            </p>
          );
        }
        if (block.style === "TH" || block.style === "TF") {
          return (
            <p key={index} {...markedProps} className="pt-2 text-center font-display text-xs italic text-ink-soft">
              {text}
            </p>
          );
        }
        return (
          <p key={index} {...markedProps} style={listIndent(block.style)}>
            {text}
          </p>
        );
      })}
    </div>
  );
}
