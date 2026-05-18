"use client";

const SUGGESTIONS = [
  "Data engineer with Python & Airflow",
  "ML engineer internships US",
  "Backend engineer Java 2+ years",
  "Entry-level data analyst remote",
  "DevOps engineer AWS",
  "Product manager fintech",
];

export function QuickChips({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="space-y-3">
      <div className="text-center text-sm text-zinc-500">Try searching for</div>
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="rounded-full border border-zinc-200 bg-white px-4 py-1.5 text-sm text-zinc-700 transition-colors hover:border-brand hover:bg-brand-soft hover:text-brand"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
