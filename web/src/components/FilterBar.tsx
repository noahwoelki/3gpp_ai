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

  const chip = (active: boolean) =>
    `rounded-full border px-3 py-1 text-xs transition ${
      active
        ? "border-blue-600 bg-blue-600 text-white"
        : "border-slate-300 bg-white text-slate-700 hover:border-blue-400"
    }`;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-slate-500">Specs</span>
        {specs.map((spec) => (
          <button
            key={spec}
            className={chip(filters.specs.includes(spec))}
            onClick={() => onChange({ ...filters, specs: toggle(filters.specs, spec) })}
          >
            {spec}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <span className="text-slate-500">Releases</span>
        {releases.map((release) => (
          <button
            key={release}
            className={chip(filters.releases.includes(release))}
            onClick={() => onChange({ ...filters, releases: toggle(filters.releases, release) })}
          >
            {release}
          </button>
        ))}
      </div>
      <span className="text-xs text-slate-400">
        {filters.specs.length ? "" : "all specs, "}
        {filters.releases.length ? "" : "latest release of each spec"}
      </span>
    </div>
  );
}
