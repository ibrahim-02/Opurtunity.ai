"use client";

import { Bookmark, BookmarkCheck, ExternalLink, MapPin, Clock, Building2 } from "lucide-react";
import { JobResult, matchPercent, postedLabel } from "@/lib/api";
import { useSavedJobs } from "@/lib/saved";
import { MatchCircle } from "./MatchCircle";
import { cn } from "@/lib/cn";

const SOURCE_LABEL: Record<string, string> = {
  linkedin: "LinkedIn",
  greenhouse: "Greenhouse",
  indeed: "Indeed",
  lever: "Lever",
  wellfound: "Wellfound",
};

export function JobCard({ job }: { job: JobResult }) {
  const { isSaved, toggle } = useSavedJobs();
  const saved = isSaved(job.id);
  const percent = matchPercent(job);
  const source = job.source ? SOURCE_LABEL[job.source] ?? job.source : null;

  return (
    <article className="rounded-xl border border-zinc-200 bg-white p-5 transition-shadow hover:shadow-sm">
      <div className="flex gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-lg bg-zinc-100 text-zinc-500">
          <Building2 className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-base font-semibold text-zinc-900">{job.title}</h3>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-zinc-600">
                {job.company && <span className="font-medium text-zinc-700">{job.company}</span>}
                {job.location && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3.5 w-3.5" />
                    {job.location}
                  </span>
                )}
                {job.experience_years != null && (
                  <span className="text-zinc-500">{job.experience_years}+ years</span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {postedLabel(job.hours_since_posted)}
                </span>
                {source && (
                  <span>
                    via <span className="font-medium text-zinc-600">{source}</span>
                  </span>
                )}
              </div>
            </div>
            <MatchCircle percent={percent} size={64} />
          </div>

          {job.explanation && (
            <div className="mt-3 rounded-lg bg-zinc-50 p-3">
              <div className="text-xs font-medium text-zinc-500">Why it matches</div>
              <p className="mt-1 text-sm leading-relaxed text-zinc-700">{job.explanation}</p>
            </div>
          )}

          {job.skills.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.skills.slice(0, 6).map((s) => (
                <span
                  key={s}
                  className="rounded-md bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand"
                >
                  {s}
                </span>
              ))}
              {job.skills.length > 6 && (
                <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
                  +{job.skills.length - 6} more
                </span>
              )}
            </div>
          )}

          <div className="mt-4 flex items-center gap-2">
            <a
              href={job.link}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
            >
              Apply
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
            <button
              type="button"
              onClick={() => toggle(job)}
              aria-label={saved ? "Remove from saved" : "Save job"}
              className={cn(
                "inline-flex items-center justify-center rounded-md border p-2 transition-colors",
                saved
                  ? "border-brand bg-brand-soft text-brand"
                  : "border-zinc-300 text-zinc-500 hover:border-zinc-400 hover:bg-zinc-50",
              )}
            >
              {saved ? <BookmarkCheck className="h-4 w-4" /> : <Bookmark className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
