import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import type { ExtractionJob } from "../types";

interface PipelineConsoleProps {
  dark: boolean;
  job: ExtractionJob;
}

const STAGES: { key: ExtractionJob["status"]; label: string }[] = [
  { key: "inspecting", label: "Inspect" },
  { key: "downloading", label: "Stream" },
  { key: "scanning", label: "Visual Scan" },
  { key: "segmenting", label: "Segment & Mask" },
  { key: "capturing", label: "HD Capture" },
  { key: "enriching", label: "OCR & Notes" },
];

export function PipelineConsole({ dark, job }: PipelineConsoleProps) {
  const pct = Math.round(job.progress * 100);
  const currentIdx = STAGES.findIndex((s) => s.key === job.status);
  const isDone = job.status === "completed";
  const isFail = job.status === "failed";

  return (
    <section
      className={`rounded-2xl border p-5 transition-colors ${
        dark ? "border-slate-800 bg-slate-900/80" : "border-slate-200 bg-white shadow-sm"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          {isDone ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
          ) : isFail ? (
            <ShieldAlert className="h-5 w-5 text-rose-400" />
          ) : (
            <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
          )}
          <div>
            <p className="text-sm font-bold">{job.message}</p>
            {job.error && <p className="mt-0.5 text-xs text-rose-400">{job.error}</p>}
          </div>
        </div>

        <span className="font-mono text-sm font-bold text-indigo-400">{pct}%</span>
      </div>

      <div
        className={`mt-3 h-2 w-full overflow-hidden rounded-full ${
          dark ? "bg-slate-800" : "bg-slate-200"
        }`}
      >
        <div
          style={{ width: `${pct}%` }}
          className={`h-full rounded-full transition-all duration-300 ${
            isFail
              ? "bg-rose-500"
              : isDone
                ? "bg-gradient-to-r from-emerald-500 to-cyan-500"
                : "bg-gradient-to-r from-indigo-500 via-violet-500 to-cyan-500"
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
              className={`rounded-lg border px-2.5 py-1.5 text-center text-[11px] font-semibold transition-all ${
                active
                  ? "border-indigo-500 bg-indigo-500/15 text-indigo-400"
                  : passed
                    ? dark
                      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                      : "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : dark
                      ? "border-slate-800 bg-slate-950/60 text-slate-500"
                      : "border-slate-200 bg-slate-50 text-slate-400"
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
            ["Slides Kept", String(job.stats.slides_kept), "text-emerald-400"],
            ["Duplicates Dropped", String(job.stats.duplicates_filtered), "text-amber-400"],
            ["Builds Collapsed", String(job.stats.progressive_merged), "text-cyan-400"],
            ["Frames Scanned", String(job.stats.frames_scanned), "text-indigo-400"],
            ["Total Time", `${job.stats.elapsed_seconds.toFixed(1)}s`, "text-violet-400"],
          ].map(([label, val, colorClass]) => (
            <div
              key={label}
              className={`rounded-xl border px-3 py-2 ${
                dark ? "border-slate-800 bg-slate-950/70" : "border-slate-200 bg-slate-50"
              }`}
            >
              <div className={`font-mono text-base font-bold ${colorClass}`}>{val}</div>
              <div className={`text-[11px] ${dark ? "text-slate-400" : "text-slate-500"}`}>{label}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
