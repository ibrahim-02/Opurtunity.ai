export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SearchFilters = {
  min_years?: number | null;
  skills?: string[];
  location?: string | null;
  max_hours_old?: number | null;
  sources?: string[];
};

export type SearchRequest = {
  query?: string;
  resume_text?: string;
  filters?: SearchFilters;
  top_n?: number;
  candidates?: number;
  page?: number;
};

export type JobResult = {
  id: number;
  title: string;
  company: string | null;
  location: string | null;
  experience_years: number | null;
  skills: string[];
  link: string;
  source: string | null;
  hours_since_posted: number | null;
  vec_score: number;
  hybrid_score: number;
  skill_overlap: number;
  filter_score: number;
  exp_score: number;
  explanation: string | null;
};

export type FiltersUsed = {
  location: string | null;
  min_years: number | null;
  skills: string[];
  max_hours_old: number | null;
};

export type SearchResponse = {
  results: JobResult[];
  total: number;
  query_used: string;
  filters_used?: FiltersUsed | null;
};

export async function searchJobs(body: SearchRequest, signal?: AbortSignal): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ top_n: 20, candidates: 250, ...body }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Search failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

export async function matchResume(file: File, signal?: AbortSignal): Promise<SearchResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/match-resume`, {
    method: "POST",
    body: form,
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Resume match failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

export type ExplainResponse = {
  explanations: Record<number, string>;
};

export async function explainJobs(
  query: string,
  jobIds: number[],
  signal?: AbortSignal,
): Promise<ExplainResponse> {
  const res = await fetch(`${API_URL}/api/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, job_ids: jobIds }),
    signal,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Explain failed (${res.status}): ${text || res.statusText}`);
  }
  return res.json();
}

export function matchPercent(j: Pick<JobResult, "hybrid_score">): number {
  return Math.max(0, Math.min(100, Math.round(j.hybrid_score * 100)));
}

export function postedLabel(hours: number | null): string {
  if (hours == null) return "Recently posted";
  if (hours < 1) return "Just posted";
  if (hours < 24) return `Posted ${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Posted 1 day ago";
  if (days < 30) return `Posted ${days} days ago`;
  return "Posted 30+ days ago";
}
