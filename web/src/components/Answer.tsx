import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../types";

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

// Renders the answer as Markdown. Citations become chips: blue if the cited clause is
// among the sources the tools returned for this answer, red if not (the model cited
// something it did not retrieve).
export default function Answer({ text, sources, onOpenSource }: Props) {
  const linked = text.replace(
    CITATION,
    (_, spec, release, clause) => `[${spec} ${release} §${clause}](#cite/${spec}/${release}/${clause})`,
  );

  return (
    <div className="prose prose-sm max-w-none prose-table:text-xs prose-td:py-1 prose-th:py-1">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (!href?.startsWith("#cite/")) {
              return (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              );
            }
            const [spec, release, clauseId] = href.slice("#cite/".length).split("/");
            const source = findSource(sources, spec, release, clauseId);
            if (!source) {
              return (
                <span
                  className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-700 no-underline"
                  title="This clause is not among the retrieved sources"
                >
                  {children}
                </span>
              );
            }
            return (
              <button
                onClick={() => onOpenSource(source)}
                className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-800 hover:bg-blue-200"
              >
                {children}
              </button>
            );
          },
        }}
      >
        {linked}
      </ReactMarkdown>
    </div>
  );
}
