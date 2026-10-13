import { specColor } from "../specs";
import type { Source } from "../types";
import ClauseTag from "./ClauseTag";

type Props = {
  sources: Source[];
  onOpenSource: (source: Source) => void;
};

const KIND_LABEL: Record<Source["kind"], string> = {
  text: "text",
  table: "table",
  table_description: "table",
  glossary: "glossary",
};

// How a passage was found. Small symbols keep the cards calm.
const FOUND_BY: Record<string, { label: string; title: string }> = {
  both: { label: "≈ #", title: "found by vector and keyword search" },
  vector: { label: "≈", title: "found by vector search" },
  keyword: { label: "#", title: "found by keyword search" },
};

// The passages the tools returned for one answer, in the order they came in
export default function SourcesPanel({ sources, onOpenSource }: Props) {
  if (sources.length === 0) {
    return (
      <div className="px-5 py-10 text-center">
        <div className="mx-auto mb-3 flex h-10 w-10 rotate-6 items-center justify-center rounded-lg border border-line bg-card font-display text-xl text-ink-faint">
          §
        </div>
        <p className="font-display text-sm italic text-ink-faint">
          Sources of an answer are listed here.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-2 p-3">
      {sources.map((source, index) => {
        const foundBy = source.found_by ? FOUND_BY[source.found_by] : null;
        return (
          <li key={index} className="rise" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}>
            <button
              onClick={() => onOpenSource(source)}
              className="group relative w-full overflow-hidden rounded-lg border border-line bg-card py-2.5 pl-4 pr-3 text-left transition hover:-translate-y-0.5 hover:shadow-[0_3px_0_0_var(--color-line)]"
            >
              <span
                className="absolute inset-y-0 left-0 w-1"
                style={{ backgroundColor: specColor(source.spec) }}
              />
              <div className="flex items-center gap-2">
                <ClauseTag spec={source.spec} release={source.release} clauseId={source.clause_id} />
                <span className="text-[10px] uppercase tracking-wider text-ink-faint">
                  {KIND_LABEL[source.kind]}
                  {source.full_table === false ? " · part" : ""}
                </span>
                <span className="ml-auto flex items-center gap-2">
                  {foundBy && (
                    <span title={foundBy.title} className="font-mono text-[11px] text-ink-faint">
                      {foundBy.label}
                    </span>
                  )}
                  {source.rerank_score !== undefined && <ScoreBar score={source.rerank_score} />}
                </span>
              </div>
              <div className="mt-1.5 text-sm font-medium leading-snug text-ink group-hover:text-signal">
                {source.title}
              </div>
              <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-soft">{source.content}</div>
              {source.tool !== "search_specs" && (
                <div className="mt-1 font-mono text-[10px] text-ink-faint">via {source.tool}</div>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// Rerank score (0..1) as five little bars, like signal strength
function ScoreBar({ score }: { score: number }) {
  const filled = Math.round(score * 5);
  return (
    <span title={`rerank score ${score.toFixed(2)}`} className="flex items-end gap-[2px]">
      {[1, 2, 3, 4, 5].map((level) => (
        <span
          key={level}
          className="w-[3px] rounded-[1px]"
          style={{
            height: `${3 + level * 2}px`,
            backgroundColor: level <= filled ? "var(--color-signal)" : "var(--color-line)",
          }}
        />
      ))}
    </span>
  );
}
