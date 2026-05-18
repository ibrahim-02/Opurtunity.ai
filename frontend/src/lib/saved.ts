"use client";

import { useEffect, useState, useCallback } from "react";
import type { JobResult } from "./api";

const KEY = "jobmatch:saved";

export type SavedJob = JobResult & { saved_at: number };

function read(): SavedJob[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SavedJob[]) : [];
  } catch {
    return [];
  }
}

function write(items: SavedJob[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("jobmatch:saved-changed"));
}

export function useSavedJobs() {
  const [items, setItems] = useState<SavedJob[]>([]);

  useEffect(() => {
    setItems(read());
    const onChange = () => setItems(read());
    window.addEventListener("jobmatch:saved-changed", onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener("jobmatch:saved-changed", onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);

  const ids = new Set(items.map((j) => j.id));

  const toggle = useCallback((job: JobResult) => {
    const list = read();
    const idx = list.findIndex((j) => j.id === job.id);
    if (idx >= 0) {
      list.splice(idx, 1);
    } else {
      list.unshift({ ...job, saved_at: Date.now() });
    }
    write(list);
  }, []);

  const remove = useCallback((id: number) => {
    const list = read().filter((j) => j.id !== id);
    write(list);
  }, []);

  const isSaved = useCallback((id: number) => ids.has(id), [ids]);

  return { items, toggle, remove, isSaved };
}
