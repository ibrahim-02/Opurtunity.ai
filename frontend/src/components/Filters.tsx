"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export type FiltersState = {
  location: string;
  remote: boolean;
  experience: string; // "any" | "0" | "2" | "3" | "5" | "8"
  skills: string[];
  recency: string; // "any" | "24" | "72" | "168" | "720"
  sources: string[];
};

export const DEFAULT_FILTERS: FiltersState = {
  location: "",
  remote: false,
  experience: "any",
  skills: [],
  recency: "any",
  sources: ["linkedin", "greenhouse", "indeed", "lever", "wellfound"],
};

const SOURCE_OPTIONS = [
  { id: "linkedin", label: "LinkedIn" },
  { id: "greenhouse", label: "Greenhouse" },
  { id: "indeed", label: "Indeed" },
  { id: "lever", label: "Lever" },
  { id: "wellfound", label: "Wellfound" },
];

const EXPERIENCE_OPTIONS = [
  { id: "any", label: "Any experience" },
  { id: "0", label: "Entry level" },
  { id: "2", label: "2+ years" },
  { id: "3", label: "3+ years" },
  { id: "5", label: "5+ years" },
  { id: "8", label: "8+ years" },
];

const RECENCY_OPTIONS = [
  { id: "any", label: "Any time" },
  { id: "24", label: "Past 24 hours" },
  { id: "72", label: "Past 3 days" },
  { id: "168", label: "Past 7 days" },
  { id: "720", label: "Past 30 days" },
];

type Props = {
  value: FiltersState;
  onApply: (next: FiltersState) => void;
  highlight?: boolean;
};

export function Filters({ value, onApply, highlight = false }: Props) {
  const [draft, setDraft] = useState<FiltersState>(value);
  const [skillInput, setSkillInput] = useState("");

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const addSkill = () => {
    const s = skillInput.trim();
    if (!s) return;
    if (!draft.skills.includes(s)) {
      setDraft({ ...draft, skills: [...draft.skills, s] });
    }
    setSkillInput("");
  };

  const removeSkill = (s: string) => setDraft({ ...draft, skills: draft.skills.filter((x) => x !== s) });

  const toggleSource = (id: string) => {
    setDraft({
      ...draft,
      sources: draft.sources.includes(id)
        ? draft.sources.filter((s) => s !== id)
        : [...draft.sources, id],
    });
  };

  const reset = () => setDraft(DEFAULT_FILTERS);

  return (
    <aside
      className={cn(
        "rounded-xl border bg-white p-5 transition-all",
        highlight ? "border-brand shadow-md ring-2 ring-brand-ring/40" : "border-zinc-200",
      )}
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-zinc-900">Filters</h2>
        <button
          type="button"
          onClick={reset}
          className="text-sm font-medium text-brand hover:text-brand-hover"
        >
          Clear all
        </button>
      </div>

      <div className="space-y-5">
        <Field label="Location">
          <input
            type="text"
            value={draft.location}
            onChange={(e) => setDraft({ ...draft, location: e.target.value })}
            placeholder="e.g. New York, Remote, United States"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-zinc-700">
          <input
            type="checkbox"
            checked={draft.remote}
            onChange={(e) => setDraft({ ...draft, remote: e.target.checked })}
            className="h-4 w-4 rounded border-zinc-300 text-brand focus:ring-brand"
          />
          Include remote jobs
        </label>

        <Field label="Experience">
          <select
            value={draft.experience}
            onChange={(e) => setDraft({ ...draft, experience: e.target.value })}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          >
            {EXPERIENCE_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Skills">
          <input
            type="text"
            value={skillInput}
            onChange={(e) => setSkillInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSkill();
              }
            }}
            onBlur={addSkill}
            placeholder="Add skill, press Enter"
            className="w-full rounded-md border border-zinc-300 px-3 py-2 text-sm"
          />
          {draft.skills.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {draft.skills.map((s) => (
                <span
                  key={s}
                  className="inline-flex items-center gap-1 rounded-md bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand"
                >
                  {s}
                  <button
                    type="button"
                    onClick={() => removeSkill(s)}
                    aria-label={`Remove ${s}`}
                    className="text-brand/70 hover:text-brand"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
        </Field>

        <Field label="Recency">
          <select
            value={draft.recency}
            onChange={(e) => setDraft({ ...draft, recency: e.target.value })}
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm"
          >
            {RECENCY_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Sources">
          <div className="space-y-1.5">
            {SOURCE_OPTIONS.map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm text-zinc-700">
                <input
                  type="checkbox"
                  checked={draft.sources.includes(s.id)}
                  onChange={() => toggleSource(s.id)}
                  className="h-4 w-4 rounded border-zinc-300 text-brand focus:ring-brand"
                />
                {s.label}
              </label>
            ))}
          </div>
        </Field>

        <button
          type="button"
          onClick={() => onApply(draft)}
          className="w-full rounded-md bg-brand py-2.5 text-sm font-medium text-white hover:bg-brand-hover"
        >
          Update Results
        </button>
      </div>
    </aside>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-zinc-700">{label}</label>
      {children}
    </div>
  );
}

export function filtersToApi(f: FiltersState) {
  const min_years = f.experience === "any" ? null : Number(f.experience);
  const max_hours_old = f.recency === "any" ? null : Number(f.recency);
  const location = f.remote && !f.location.trim() ? null : f.location.trim() || null;
  // Only send sources when it's a subset (empty array = all sources = no filter needed)
  const allSources = SOURCE_OPTIONS.map((s) => s.id);
  const sources = f.sources.length === allSources.length ? [] : f.sources;
  return {
    min_years,
    skills: f.skills,
    location,
    max_hours_old,
    sources,
  };
}
