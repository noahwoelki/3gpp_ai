import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../types";
import ClauseTag from "./ClauseTag";

// "[38.300 Rel-18 §15.4.2.3]" as written by the agents
const CITATION = /\[(\d{2}\.\d{3}(?:-\d+)?) (Rel-\d+) §([^\]\s,;]+)\]/g;

export function findSource(sources: Source[], spec: string, release: string, clauseId: string) {
  return sources.find(
    (s) => s.spec === spec && s.release === release && s.clause_id === clauseId,
  );
}

type Props = {
  text: string;
  sources: Source[];
  onOpenSource: (source: Source) => void;
};

// Renders the answer as Markdown. Citations become clause tags: clickable if the cited
// clause is among the sources the tools returned for this answer, crossed out if not
// (the model cited something it did not retrieve).
export default function Answer({ text, sources, onOpenSource }: Props) {
  const linked = text.replace(
    CITATION,
    (_, spec, release, clause) => `[${spec} ${release} §${clause}](#cite/${spec}/${release}/${clause})`,
  );

  return (
    <div
      className="prose prose-sm max-w-none text-ink
        prose-headings:font-display prose-headings:font-semibold prose-headings:text-ink
        prose-strong:text-ink prose-p:leading-relaxed
        prose-table:my-3 prose-table:text-xs prose-thead:border-line prose-tr:border-line
        prose-th:bg-paper-deep prose-th:px-2 prose-th:py-1.5 prose-td:px-2 prose-td:py-1
        prose-code:font-mono prose-code:text-[0.85em] prose-code:before:content-none prose-code:after:content-none"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (!href?.startsWith("#cite/")) {
              return (
                <a href={href} target="_blank" rel="noreferrer" className="text-signal">
                  {children}
                </a>
              );
            }
            const [spec, release, clauseId] = href.slice("#cite/".length).split("/");
            const source = findSource(sources, spec, release, clauseId);
            return (
              <ClauseTag
                spec={spec}
                release={release}
                clauseId={clauseId}
                invalid={!source}
                onClick={source ? () => onOpenSource(source) : undefined}
              />
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border border-line bg-card">
              <table className="my-0">{children}</table>
            </div>
          ),
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}
