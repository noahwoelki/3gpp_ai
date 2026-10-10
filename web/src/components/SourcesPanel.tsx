import type { Source } from "../types";

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

const FOUND_BY_STYLE: Record<string, string> = {
  both: "bg-emerald-100 text-emerald-800",
  vector: "bg-violet-100 text-violet-800",
  keyword: "bg-amber-100 text-amber-800",
};

// The passages the tools returned for one answer, in the order they came in
export default function SourcesPanel({ sources, onOpenSource }: Props) {
  if (sources.length === 0) {
    return <p className="p-4 text-sm text-slate-400">Sources of the selected answer show up here.</p>;
  }
  return (
    <ul className="divide-y divide-slate-100">
      {sources.map((source, index) => (
        <li key={index}>
          <button
            onClick={() => onOpenSource(source)}
            className="w-full px-4 py-3 text-left hover:bg-slate-50"
          >
            <div className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-blue-800">{source.citation}</span>
              <span className="rounded bg-slate-100 px-1.5 text-slate-600">
                {KIND_LABEL[source.kind]}
                {source.full_table === false ? " (part)" : ""}
              </span>
              {source.found_by && (
                <span className={`rounded px-1.5 ${FOUND_BY_STYLE[source.found_by]}`}>
                  {source.found_by}
                </span>
              )}
              {source.rerank_score !== undefined && (
                <span className="ml-auto text-slate-400">{source.rerank_score.toFixed(2)}</span>
              )}
            </div>
            <div className="mt-1 text-sm font-medium text-slate-800">{source.title}</div>
            <div className="mt-1 line-clamp-2 text-xs text-slate-500">{source.content}</div>
            {source.tool !== "search_specs" && (
              <div className="mt-1 text-[11px] text-slate-400">via {source.tool}</div>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
