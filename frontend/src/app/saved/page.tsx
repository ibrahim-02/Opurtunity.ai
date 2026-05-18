"use client";

import Link from "next/link";
import { Bookmark } from "lucide-react";
import { useSavedJobs } from "@/lib/saved";
import { JobCard } from "@/components/JobCard";

export default function SavedPage() {
  const { items } = useSavedJobs();

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-900">Saved Jobs</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {items.length === 0
            ? "Save jobs from search results to view them here later."
            : `${items.length} job${items.length === 1 ? "" : "s"} saved`}
        </p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-300 bg-white p-12 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-zinc-100">
            <Bookmark className="h-5 w-5 text-zinc-500" />
          </div>
          <h2 className="mt-4 text-base font-medium text-zinc-900">No saved jobs yet</h2>
          <p className="mt-1 text-sm text-zinc-500">
            Bookmark interesting roles and they&apos;ll show up here.
          </p>
          <Link
            href="/"
            className="mt-5 inline-flex items-center rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
          >
            Find jobs
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
