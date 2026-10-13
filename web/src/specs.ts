// Each spec has its own color, so clause tags and sources are easy to tell apart.
// The values match the --color-spec-* variables in index.css.
const SPEC_COLORS: Record<string, string> = {
  "38.300": "var(--color-spec-38300)",
  "38.321": "var(--color-spec-38321)",
  "38.101-1": "var(--color-spec-381011)",
  "21.905": "var(--color-spec-21905)",
};

export function specColor(spec: string): string {
  return SPEC_COLORS[spec] ?? "var(--color-ink-soft)";
}

const SPEC_NAMES: Record<string, string> = {
  "38.300": "NR overall description",
  "38.321": "MAC protocol",
  "38.101-1": "UE radio, FR1",
  "21.905": "Vocabulary",
};

export function specName(spec: string): string {
  return SPEC_NAMES[spec] ?? "";
}
