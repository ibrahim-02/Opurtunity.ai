// Module-level singleton: holds the File object across client-side navigations.
// Files can't be serialized into URLs or sessionStorage, so this in-memory
// reference bridges the landing page → /analyzing → /dashboard flow.

let pendingResume: File | null = null;

export function setPendingResume(file: File | null) {
  pendingResume = file;
}

export function takePendingResume(): File | null {
  const f = pendingResume;
  pendingResume = null;
  return f;
}

export function hasPendingResume(): boolean {
  return pendingResume !== null;
}

// Results cache for resume-mode dashboard (keyed by sessionStorage).
import type { SearchResponse } from "./api";

const RESULTS_KEY = "jobmatch:last-resume-results";

export function saveResumeResults(data: SearchResponse) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(RESULTS_KEY, JSON.stringify(data));
}

export function loadResumeResults(): SearchResponse | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(RESULTS_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SearchResponse;
  } catch {
    return null;
  }
}

export function clearResumeResults() {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(RESULTS_KEY);
}
