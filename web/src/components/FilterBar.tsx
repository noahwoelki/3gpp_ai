import { specColor, specName } from "../specs";
import type { Filters } from "../types";

type Props = {
  available: Record<string, string[]>; // spec -> releases in the corpus
  filters: Filters;
  onChange: (filters: Filters) => void;
};

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export default function FilterBar({ available, filters, onChange }: Props) {
  const specs = Object.keys(available).sort();
  const releases = [...new Set(Object.values(available).flat())].sort();

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {specs.map((spec) => {
          const active = filters.specs.includes(spec);
          const color = specColor(spec);
          return (
            <button
              key={spec}
              title={specName(spec)}
              onClick={() => onChange({ ...filters, specs: toggle(filters.specs, spec) })}
              style={
                active
                  ? { backgroundColor: color, borderColor: color }
                  : { borderColor: "var(--color-line)" }
              }
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] transition hover:-translate-y-px ${
                active ? "text-white shadow-sm" : "bg-card text-ink-soft hover:text-ink"
              }`}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: active ? "white" : color }}
              />
              {spec}
            </button>
          );
        })}
      </div>

      <div className="flex items-center rounded-full border border-line bg-card p-0.5">
        {releases.map((release) => {
          const active = filters.releases.includes(release);
          return (
            <button
              key={release}
              onClick={() => onChange({ ...filters, releases: toggle(filters.releases, release) })}
              className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] transition ${
                active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
              }`}
            >
              {release}
            </button>
          );
        })}
      </div>

      <span className="font-display text-xs italic text-ink-faint">
        {filters.specs.length === 0 && filters.releases.length === 0
          ? "all specs, latest release"
          : filters.releases.length === 0
            ? "latest release"
            : ""}
      </span>
    </div>
  );
}
