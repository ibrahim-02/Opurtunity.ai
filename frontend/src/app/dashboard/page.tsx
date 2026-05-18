"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { ArrowRight, CheckCircle2, MapPin, Briefcase, Wrench, Pencil, Loader2, ChevronLeft, ChevronRight } from "lucide-react";
import {
  searchJobs,
  explainJobs,
  type SearchResponse,
  type FiltersUsed,
} from "@/lib/api";
import { JobCard } from "@/components/JobCard";
import { Filters, DEFAULT_FILTERS, filtersToApi, type FiltersState } from "@/components/Filters";
import { loadResumeResults, saveResumeResults, clearResumeResults } from "@/lib/resume-store";

const PAGE_SIZE = 20;
const MAX_PAGES = 5;

export default function DashboardPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto flex max-w-7xl items-center justify-center py-24 text-zinc-500">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
        </div>
      }
    >
      <DashboardInner />
    </Suspense>
  );
}

function DashboardInner() {
  const router = useRouter();
  const sp = useSearchParams();
  const initialQuery = sp.get("q") ?? "";
  const isResumeMode = sp.get("source") === "resume";
  const editFromHome = sp.get("edit") === "1";

  const [query, setQuery] = useState(initialQuery);
  const [filters, setFilters] = useState<FiltersState>(DEFAULT_FILTERS);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(!isResumeMode);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"match" | "recent">("match");
  const [page, setPage] = useState(1);
  const [highlightFilters, setHighlightFilters] = useState(editFromHome);
  const filtersRef = useRef<HTMLDivElement>(null);
  const resultsTopRef = useRef<HTMLDivElement>(null);

  // Load resume-mode results from sessionStorage
  useEffect(() => {
    if (!isResumeMode) return;
    const cached = loadResumeResults();
    if (cached) {
      setData(cached);
    } else {
      router.replace("/");
    }
  }, [isResumeMode, router]);

  // After results land, explain every job in batches of 20 concurrently.
  // Each batch resolves independently so cards fill in progressively.
  useEffect(() => {
    if (!data) return;
    const missing = data.results.filter((r) => !r.explanation).map((r) => r.id);
    if (missing.length === 0) return;

    const ctrl = new AbortController();
    const BATCH = 20;
    const query = data.query_used;

    for (let i = 0; i < missing.length; i += BATCH) {
      const batch = missing.slice(i, i + BATCH);
      explainJobs(query, batch, ctrl.signal)
        .then((res) => {
          setData((prev) => {
            if (!prev) return prev;
            const next = {
              ...prev,
              results: prev.results.map((r) => ({
                ...r,
                explanation: r.explanation ?? res.explanations[r.id] ?? null,
              })),
            };
            if (isResumeMode) saveResumeResults(next);
            return next;
          });
        })
        .catch((e) => {
          if ((e as Error).name !== "AbortError") console.warn("Explain batch failed:", e);
        });
    }

    return () => ctrl.abort();
  }, [data?.query_used, page, isResumeMode]);

  // Reset to page 1 whenever query or filters change.
  useEffect(() => {
    setPage(1);
  }, [query, filters]);

  // Fetch results whenever query, filters, or page changes.
  useEffect(() => {
    if (isResumeMode) return;
    const effectiveQuery = query.trim() || buildQueryFromFilters(filters);
    if (!effectiveQuery) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    searchJobs(
      { query: effectiveQuery, filters: filtersToApi(filters), page },
      ctrl.signal,
    )
      .then((res) => setData(res))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message || "Search failed");
      })
      .finally(() => { if (!ctrl.signal.aborted) setLoading(false); });
    return () => ctrl.abort();
  }, [query, filters, isResumeMode, page]);

  // Scroll to filters if user came via "Use Filters"
  useEffect(() => {
    if (editFromHome && filtersRef.current) {
      filtersRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      const t = window.setTimeout(() => setHighlightFilters(false), 1800);
      return () => window.clearTimeout(t);
    }
  }, [editFromHome]);

  const sortedResults = useMemo(() => {
    if (!data) return [];
    const arr = [...data.results];
    if (sortBy === "recent") {
      arr.sort(
        (a, b) =>
          (a.hours_since_posted ?? Number.MAX_SAFE_INTEGER) -
          (b.hours_since_posted ?? Number.MAX_SAFE_INTEGER),
      );
    } else {
      arr.sort((a, b) => b.vec_score - a.vec_score);
    }
    return arr;
  }, [data, sortBy]);

  // Reset to page 1 when sort changes
  useEffect(() => {
    setPage(1);
  }, [sortBy]);

  const totalPages = Math.min(Math.ceil((data?.total ?? 0) / PAGE_SIZE), MAX_PAGES);
  const pageResults = sortedResults;

  const goToPage = (p: number) => {
    setPage(p);
    resultsTopRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const focusFilters = () => {
    setHighlightFilters(true);
    filtersRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => setHighlightFilters(false), 1600);
  };

  if (!initialQuery && !isResumeMode && !editFromHome) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h1 className="text-2xl font-semibold text-zinc-900">No search yet</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Start by describing the role you want or uploading your resume.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
        >
          Start searching <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Top bar */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900">
            {loading
              ? "Searching…"
              : (data?.total ?? 0) > 0
                ? `${data!.total} matches found`
                : "Top matches for you"}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">
            {isResumeMode
              ? "Based on your resume"
              : query
                ? `For: "${query}"`
                : "Use the filters to find jobs"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as "match" | "recent")}
            className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          >
            <option value="match">Sort by: Best match</option>
            <option value="recent">Sort by: Most recent</option>
          </select>
          <Link
            href="/"
            onClick={() => clearResumeResults()}
            className="rounded-md border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50"
          >
            New Search
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        {/* Filters sidebar */}
        <div ref={filtersRef} className="lg:sticky lg:top-20 lg:self-start">
          <Filters value={filters} onApply={setFilters} highlight={highlightFilters} />
        </div>

        {/* Results column */}
        <div className="space-y-4">
          <div ref={resultsTopRef} />

          {data?.filters_used && !isResumeMode && (
            <UnderstoodBanner filtersUsed={data.filters_used} onEdit={focusFilters} />
          )}

          {loading && (
            <div className="flex items-center justify-center rounded-xl border border-zinc-200 bg-white p-10 text-sm text-zinc-500">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Fetching matching jobs…
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {!loading && !error && data !== null && sortedResults.length === 0 && (
            <div className="rounded-xl border border-zinc-200 bg-white p-10 text-center text-sm text-zinc-500">
              No matches found. Try widening your filters.
            </div>
          )}

          {pageResults.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}

          {!loading && totalPages > 1 && (
            <Pagination current={page} total={totalPages} onChange={goToPage} />
          )}
        </div>
      </div>
    </div>
  );
}

function Pagination({
  current,
  total,
  onChange,
}: {
  current: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const pages = Array.from({ length: total }, (_, i) => i + 1);

  return (
    <div className="flex items-center justify-center gap-1 pt-4">
      <button
        type="button"
        onClick={() => onChange(current - 1)}
        disabled={current === 1}
        className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {pages.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onChange(p)}
          className={`h-9 w-9 rounded-md border text-sm font-medium transition-colors ${
            p === current
              ? "border-brand bg-brand text-white"
              : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50"
          }`}
        >
          {p}
        </button>
      ))}

      <button
        type="button"
        onClick={() => onChange(current + 1)}
        disabled={current === total}
        className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-200 bg-white text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}

function buildQueryFromFilters(f: FiltersState): string {
  const parts: string[] = [];
  if (f.skills.length > 0) parts.push(f.skills.join(", "));
  parts.push("jobs");
  if (f.experience !== "any") parts.push(`${f.experience}+ years`);
  if (f.location.trim()) parts.push(`in ${f.location.trim()}`);
  if (f.remote) parts.push("remote");
  return parts.join(" ");
}

function UnderstoodBanner({
  filtersUsed,
  onEdit,
}: {
  filtersUsed: FiltersUsed;
  onEdit: () => void;
}) {
  const items: { icon: React.ReactNode; label: string; value: string }[] = [];
  if (filtersUsed.min_years != null)
    items.push({
      icon: <Briefcase className="h-3.5 w-3.5" />,
      label: "Experience",
      value: `${filtersUsed.min_years}+ years`,
    });
  if (filtersUsed.skills && filtersUsed.skills.length > 0)
    items.push({
      icon: <Wrench className="h-3.5 w-3.5" />,
      label: "Top Skills",
      value: filtersUsed.skills.slice(0, 4).join(", "),
    });
  if (filtersUsed.location)
    items.push({
      icon: <MapPin className="h-3.5 w-3.5" />,
      label: "Location",
      value: filtersUsed.location,
    });

  if (items.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-brand-ring/40 bg-brand-soft px-4 py-3 text-sm">
      <div className="flex items-center gap-1.5 font-medium text-brand">
        <CheckCircle2 className="h-4 w-4" />
        We understood your profile as:
      </div>
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-1.5 text-zinc-700">
          {it.icon}
          <span className="text-zinc-500">{it.label}:</span>
          <span className="font-medium">{it.value}</span>
        </div>
      ))}
      <button
        type="button"
        onClick={onEdit}
        className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-hover"
      >
        <Pencil className="h-3 w-3" /> Edit
      </button>
    </div>
  );
}
