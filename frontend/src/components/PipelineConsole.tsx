import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import type { ExtractionJob } from "../types";

interface PipelineConsoleProps {
  dark: boolean;
  job: ExtractionJob;
}

const STAGES: { key: ExtractionJob["status"]; label: string }[] = [
  { key: "inspecting", label: "Inspect" },
  { key: "downloading", label: "Stream" },
  { key: "scanning", label: "Scan" },
  { key: "segmenting", label: "Filter" },
  { key: "capturing", label: "Capture" },
  { key: "enriching", label: "Notes" },
];

export function PipelineConsole({ dark, job }: PipelineConsoleProps) {
  const pct = Math.round(job.progress * 100);
  const currentIdx = STAGES.findIndex((s) => s.key === job.status);
  const isDone = job.status === "completed";
  const isFail = job.status === "failed";

  return (
    <section
      className={`rounded-[24px] p-5 transition-all ${
        dark ? "glass-dark" : "glass-light"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          {isDone ? (
            <CheckCircle2 className="h-5 w-5 text-[#34C759]" />
          ) : isFail ? (
            <ShieldAlert className="h-5 w-5 text-rose-500" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-[#007AFF]" />
          )}
          <div>
            <p className="text-sm font-semibold">{job.message}</p>
            {job.error && <p className="mt-0.5 text-xs text-rose-500">{job.error}</p>}
          </div>
        </div>

        <span className="font-mono text-sm font-semibold text-[#007AFF]">{pct}%</span>
      </div>

      <div
        className={`mt-3 h-1.5 w-full overflow-hidden rounded-full ${
          dark ? "bg-white/10" : "bg-black/[0.07]"
        }`}
      >
        <div
          style={{ width: `${pct}%` }}
          className={`h-full rounded-full transition-all duration-300 ${
            isFail ? "bg-rose-500" : isDone ? "bg-[#34C759]" : "bg-[#007AFF]"
          }`}
        />
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
        {STAGES.map((st, idx) => {
          const passed = isDone || (currentIdx >= 0 && idx < currentIdx);
          const active = !isDone && !isFail && idx === currentIdx;
          return (
            <div
              key={st.key}
              className={`rounded-full px-2.5 py-1 text-center text-[11px] font-semibold transition-all ${
                active
                  ? "bg-[#007AFF]/15 text-[#007AFF] ring-1 ring-[#007AFF]/40"
                  : passed
                    ? dark
                      ? "bg-[#34C759]/15 text-emerald-300"
                      : "bg-[#34C759]/12 text-emerald-700"
                    : dark
                      ? "bg-white/[0.05] text-neutral-500"
                      : "bg-black/[0.04] text-slate-400"
              }`}
            >
              {st.label}
            </div>
          );
        })}
      </div>

      {isDone && (
        <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-5">
          {[
            ["Slides Kept", String(job.stats.slides_kept), dark ? "text-emerald-300" : "text-emerald-700"],
            ["Duplicates Skipped", String(job.stats.duplicates_filtered), dark ? "text-neutral-200" : "text-slate-800"],
            ["Steps Collapsed", String(job.stats.progressive_merged), dark ? "text-[#60A5FA]" : "text-[#007AFF]"],
            ["Frames Scanned", String(job.stats.frames_scanned), dark ? "text-neutral-300" : "text-slate-700"],
            ["Total Time", `${job.stats.elapsed_seconds.toFixed(1)}s`, dark ? "text-neutral-200" : "text-slate-800"],
          ].map(([label, val, colorClass]) => (
            <div
              key={label}
              className={`rounded-2xl px-3.5 py-2.5 ${
                dark ? "glass-dark-subtle" : "glass-light-subtle"
              }`}
            >
              <div className={`font-mono text-base font-semibold ${colorClass}`}>{val}</div>
              <div className={`text-[11px] ${dark ? "text-neutral-400" : "text-slate-500"}`}>{label}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
