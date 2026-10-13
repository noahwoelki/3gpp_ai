import { specColor } from "../specs";

type Props = {
  spec: string;
  release: string;
  clauseId: string;
  size?: "sm" | "md";
  invalid?: boolean; // cited, but not among the retrieved sources
  onClick?: () => void;
};

// A clause reference as a small tag: colored dot for the spec, then "38.300 · R18 · §15.4.2.3"
export default function ClauseTag({ spec, release, clauseId, size = "sm", invalid, onClick }: Props) {
  const color = specColor(spec);
  const text = size === "sm" ? "text-[11px]" : "text-xs";
  const releaseShort = release.replace("Rel-", "R");

  if (invalid) {
    return (
      <span
        title="Cited, but this clause was not among the retrieved sources"
        className={`inline-flex items-center gap-1 rounded-md border border-dashed border-red-400 bg-red-50 px-1.5 py-px align-baseline font-mono ${text} text-red-700 line-through decoration-red-300`}
      >
        {spec} · {releaseShort} · §{clauseId}
      </span>
    );
  }

  const Tag = onClick ? "button" : "span";
  return (
    <Tag
      onClick={onClick}
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 12%, var(--color-card))`,
        borderColor: `color-mix(in srgb, ${color} 35%, transparent)`,
      }}
      className={`inline-flex items-center gap-1.5 rounded-md border px-1.5 py-px align-baseline font-mono ${text} text-ink transition ${
        onClick ? "cursor-pointer hover:-translate-y-px hover:shadow-[0_2px_0_0_var(--color-line)]" : ""
      }`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-ink-soft">
        {spec} · {releaseShort}
      </span>
      <span className="font-medium">§{clauseId}</span>
    </Tag>
  );
}
