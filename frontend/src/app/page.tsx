"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Upload, SlidersHorizontal } from "lucide-react";
import { QuickChips } from "@/components/QuickChips";
import { SourceBadges } from "@/components/SourceBadges";
import { setPendingResume } from "@/lib/resume-store";

export default function LandingPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const submit = () => {
    const q = query.trim();
    if (!q) return;
    router.push(`/dashboard?q=${encodeURIComponent(q)}`);
  };

  const onFileChosen = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPendingResume(file);
    router.push("/analyzing");
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-20">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight text-zinc-900 sm:text-5xl">
          Find jobs that <span className="text-brand">actually</span>
          <br />
          match your profile
        </h1>
        <p className="mt-4 text-lg text-zinc-600">
          AI-powered matching. Real-time data. Better results.
        </p>
      </div>

      <div className="mt-10 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm">
        <div className="relative flex items-end gap-2">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={2}
            placeholder="Describe the job you want or upload your resume…"
            className="flex-1 resize-none rounded-xl border-0 bg-transparent p-4 text-sm placeholder:text-zinc-400 focus:outline-none"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!query.trim()}
            aria-label="Search"
            className="m-2 grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand text-white transition-opacity hover:bg-brand-hover disabled:opacity-40"
          >
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="mt-5 flex justify-center gap-3">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50"
        >
          <Upload className="h-4 w-4" />
          Upload Resume
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={onFileChosen}
        />
        <button
          type="button"
          onClick={() => router.push("/dashboard?edit=1")}
          className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 hover:border-zinc-300 hover:bg-zinc-50"
        >
          <SlidersHorizontal className="h-4 w-4" />
          Use Filters
        </button>
      </div>

      <div className="mt-10">
        <QuickChips onPick={setQuery} />
      </div>

      <div className="mt-10">
        <SourceBadges />
      </div>
    </div>
  );
}
