"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Check, Loader2, Upload } from "lucide-react";
import { matchResume } from "@/lib/api";
import { takePendingResume, saveResumeResults } from "@/lib/resume-store";
import { cn } from "@/lib/cn";

const STEPS = [
  { id: "extract", label: "Extracting text" },
  { id: "skills", label: "Identifying skills\nand experience" },
  { id: "match", label: "Matching jobs" },
];

type StepStatus = "pending" | "active" | "done";

export default function AnalyzingPage() {
  const router = useRouter();
  const ranRef = useRef(false);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [noFile, setNoFile] = useState(false);

  useEffect(() => {
    // ranRef prevents double-invoke in React Strict Mode so we don't
    // call takePendingResume() twice (it's a destructive read).
    if (ranRef.current) return;
    ranRef.current = true;

    const file = takePendingResume();
    if (!file) {
      setNoFile(true);
      return;
    }

    // Advance step indicator every 2.5 s (pure cosmetic).
    const timer = window.setInterval(
      () => setStep((s) => (s < STEPS.length - 1 ? s + 1 : s)),
      2500,
    );

    // Fire the request — no AbortController so strict-mode cleanup can't
    // cancel it. Navigation happens as soon as the response lands.
    matchResume(file)
      .then((data) => {
        clearInterval(timer);
        saveResumeResults(data);
        router.replace("/dashboard?source=resume");
      })
      .catch((e: Error) => {
        clearInterval(timer);
        setError(e.message || "Failed to analyze resume.");
      });
  }, [router]);

  if (noFile) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-zinc-100">
          <Upload className="h-5 w-5 text-zinc-500" />
        </div>
        <h1 className="mt-4 text-xl font-semibold text-zinc-900">No resume to analyze</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Upload a PDF or DOCX from the home page and we&apos;ll match it to jobs.
        </p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
        >
          <Upload className="h-4 w-4" /> Upload Resume
        </Link>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <div className="font-medium">Couldn&apos;t analyze that file</div>
          <p className="mt-1">{error}</p>
          <Link
            href="/"
            className="mt-3 inline-block rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700"
          >
            Try again
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-20">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-zinc-900">Analyzing your resume…</h1>
        <p className="mt-2 text-sm text-zinc-500">This usually takes 5–10 seconds</p>
      </div>

      <div className="mt-12 flex items-start justify-between gap-4">
        {STEPS.map((s, i) => {
          const status: StepStatus = step > i ? "done" : step === i ? "active" : "pending";
          return (
            <div key={s.id} className="flex flex-1 flex-col items-center">
              <StepDot status={status} />
              <div className="mt-3 whitespace-pre-line text-center text-xs text-zinc-600">
                {s.label}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-10 text-center text-sm text-zinc-500">
        <Loader2 className="mx-auto h-4 w-4 animate-spin" />
        <div className="mt-2">Finding the best matches for you…</div>
      </div>
    </div>
  );
}

function StepDot({ status }: { status: StepStatus }) {
  return (
    <div
      className={cn(
        "grid h-8 w-8 place-items-center rounded-full border-2 transition-colors",
        status === "done" && "border-brand bg-brand text-white",
        status === "active" && "border-brand bg-white text-brand",
        status === "pending" && "border-zinc-300 bg-white text-zinc-400",
      )}
    >
      {status === "done" ? (
        <Check className="h-4 w-4" />
      ) : status === "active" ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : null}
    </div>
  );
}
