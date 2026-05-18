const sources = ["LinkedIn", "Greenhouse", "Indeed", "Wellfound", "Lever"];

export function SourceBadges() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-zinc-500">
      <span>Jobs from</span>
      {sources.map((s) => (
        <span
          key={s}
          className="rounded-md bg-white px-3 py-1 text-zinc-700 ring-1 ring-zinc-200"
        >
          {s}
        </span>
      ))}
      <span className="text-zinc-400">and more</span>
    </div>
  );
}
