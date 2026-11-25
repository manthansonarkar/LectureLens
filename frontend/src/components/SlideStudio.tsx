import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Columns2,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  Filter,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  StickyNote,
  X,
} from "lucide-react";
import type { ExtractionConfig, ExtractionJob, SlideItem } from "../types";

interface SlideStudioProps {
  dark: boolean;
  job: ExtractionJob;
  config: ExtractionConfig;
  onConfigChange: (cfg: ExtractionConfig) => void;
  onRefilter: () => Promise<void>;
  onToggleSlide: (slide: SlideItem) => Promise<void>;
  onSaveNotes: (slideId: string, notes: string) => Promise<void>;
  onAddManualTimestamp: (seconds: number) => Promise<void>;
  onOpenExport: () => void;
  busy: boolean;
}

function parseTimestampInput(raw: string): number | null {
  const s = raw.trim();
  if (!s) return null;
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  const parts = s.split(":").map((x) => Number(x));
  if (parts.some((n) => Number.isNaN(n) || n < 0)) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

export function SlideStudio({
  dark,
  job,
  config,
  onConfigChange,
  onRefilter,
  onToggleSlide,
  onSaveNotes,
  onAddManualTimestamp,
  onOpenExport,
  busy,
}: SlideStudioProps) {
  const [filterTab, setFilterTab] = useState<"kept" | "filtered" | "all">("kept");
  const [query, setQuery] = useState("");
  const [manualTs, setManualTs] = useState("");
  const [lightboxId, setLightboxId] = useState<string | null>(null);
  const [comparePrev, setComparePrev] = useState(false);
  const [noteDrafts, setNoteDrafts] = useState<Record<string, string>>({});

  const keptSlides = useMemo(() => job.slides.filter((s) => s.kept), [job.slides]);
  const filteredSlides = useMemo(() => job.slides.filter((s) => !s.kept), [job.slides]);

  const visibleSlides = useMemo(() => {
    const base =
      filterTab === "kept"
        ? keptSlides
        : filterTab === "filtered"
          ? filteredSlides
          : job.slides;
    const q = query.trim().toLowerCase();
    if (!q) return base;
    return base.filter(
      (s) =>
        s.ocr_text.toLowerCase().includes(q) ||
        s.transcript_text.toLowerCase().includes(q) ||
        s.user_notes.toLowerCase().includes(q) ||
        (s.chapter_title || "").toLowerCase().includes(q) ||
        s.timestamp_label.includes(q)
    );
  }, [filterTab, keptSlides, filteredSlides, job.slides, query]);

  const lightboxIndex = useMemo(
    () => (lightboxId ? visibleSlides.findIndex((s) => s.id === lightboxId) : -1),
    [lightboxId, visibleSlides]
  );
  const activeSlide = lightboxIndex >= 0 ? visibleSlides[lightboxIndex] : null;
  const prevKeptSlide = useMemo(() => {
    if (!activeSlide) return null;
    const idx = keptSlides.findIndex((s) => s.id === activeSlide.id);
    return idx > 0 ? keptSlides[idx - 1] : null;
  }, [activeSlide, keptSlides]);

  useEffect(() => {
    if (!activeSlide) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightboxId(null);
      if (e.key === "ArrowRight" && lightboxIndex + 1 < visibleSlides.length) {
        setLightboxId(visibleSlides[lightboxIndex + 1].id);
      }
      if (e.key === "ArrowLeft" && lightboxIndex > 0) {
        setLightboxId(visibleSlides[lightboxIndex - 1].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeSlide, lightboxIndex, visibleSlides]);

  const handleAddTimestamp = async (e: React.FormEvent) => {
    e.preventDefault();
    const secs = parseTimestampInput(manualTs);
    if (secs === null) return;
    await onAddManualTimestamp(secs);
    setManualTs("");
  };

  const reasonLabel = (r: string) => {
    if (r === "progressive_step") return "Progressive Step";
    if (r === "erased_step") return "Erased Board Step";
    if (r === "ai_filtered") return "AI Vision Filtered";
    if (r === "duplicate") return "Duplicate / Overlap";
    if (r === "global_repeat") return "Revisited Slide";
    if (r === "low_content") return "Blank / Empty";
    if (r === "manual_excluded") return "Excluded";
    if (r === "manual_added") return "Manual Capture";
    return "Kept";
  };

  return (
    <section className="space-y-4">
      {/* Studio Toolbar */}
      <div
        className={`rounded-2xl border p-4 transition-colors ${
          dark ? "border-slate-800 bg-slate-900/80" : "border-slate-200 bg-white shadow-sm"
        }`}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            {(
              [
                ["kept", `Kept (${keptSlides.length})`],
                ["filtered", `Filtered (${filteredSlides.length})`],
                ["all", `All (${job.slides.length})`],
              ] as const
            ).map(([tab, label]) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilterTab(tab)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                  filterTab === tab
                    ? "bg-indigo-600 text-white shadow-sm"
                    : dark
                      ? "bg-slate-800 text-slate-300 hover:bg-slate-700"
                      : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {label}
              </button>
            ))}

            <div className="relative ml-0 flex-1 sm:ml-2 sm:w-64 sm:flex-none">
              <Search
                className={`pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${
                  dark ? "text-slate-500" : "text-slate-400"
                }`}
              />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search OCR text, notes, topics..."
                className={`w-full rounded-lg border py-1.5 pl-8 pr-3 text-xs outline-none ${
                  dark
                    ? "border-slate-700 bg-slate-950 text-slate-200 placeholder-slate-500 focus:border-indigo-500"
                    : "border-slate-300 bg-slate-50 text-slate-800 placeholder-slate-400 focus:border-indigo-500"
                }`}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Instant Re-Filter Sensitivity */}
            <div
              className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 ${
                dark ? "border-slate-800 bg-slate-950/70" : "border-slate-200 bg-slate-50"
              }`}
            >
              <Filter className="h-3.5 w-3.5 text-indigo-400" />
              <span className="text-[11px] font-semibold">Max Sim:</span>
              <input
                type="range"
                min={15}
                max={92}
                value={Math.round(config.max_similarity * 100)}
                onChange={(e) =>
                  onConfigChange({ ...config, max_similarity: Number(e.target.value) / 100 })
                }
                className="w-20 accent-indigo-500"
              />
              <span className="w-9 font-mono text-xs font-bold text-indigo-400">
                {Math.round(config.max_similarity * 100)}%
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={onRefilter}
                className="inline-flex items-center gap-1 rounded-md bg-indigo-600/20 px-2 py-1 text-[11px] font-bold text-indigo-400 transition-colors hover:bg-indigo-600 hover:text-white disabled:opacity-50"
              >
                <RefreshCw className={`h-3 w-3 ${busy ? "animate-spin" : ""}`} />
                Re-Filter
              </button>
            </div>

            {/* Capture Manual Timestamp */}
            <form onSubmit={handleAddTimestamp} className="flex items-center gap-1.5">
              <input
                type="text"
                value={manualTs}
                onChange={(e) => setManualTs(e.target.value)}
                placeholder="mm:ss"
                className={`w-20 rounded-lg border px-2.5 py-1.5 font-mono text-xs outline-none ${
                  dark
                    ? "border-slate-700 bg-slate-950 text-slate-200 placeholder-slate-500"
                    : "border-slate-300 bg-slate-50 text-slate-800"
                }`}
              />
              <button
                type="submit"
                disabled={busy || !manualTs.trim()}
                title="Capture frame at exact timestamp"
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
                  dark
                    ? "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
                }`}
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </form>

            {/* Primary Export CTA */}
            <button
              type="button"
              onClick={onOpenExport}
              disabled={keptSlides.length === 0}
              className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-600 px-4 py-2 text-xs font-bold text-white shadow-lg shadow-emerald-600/20 transition-all hover:from-emerald-400 hover:to-cyan-500 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              Export PDF / DOCX
            </button>
          </div>
        </div>

        {job.lecture_summary && (
          <div
            className={`mt-4 rounded-xl border p-3.5 text-xs leading-relaxed ${
              dark
                ? "border-indigo-500/30 bg-indigo-500/10 text-indigo-100"
                : "border-indigo-200 bg-indigo-50/70 text-slate-800"
            }`}
          >
            <div className="mb-1 flex items-center gap-1.5 font-bold text-indigo-400">
              <Sparkles className="h-3.5 w-3.5" />
              AI Executive Lecture Summary
            </div>
            <p className="whitespace-pre-line">{job.lecture_summary}</p>
          </div>
        )}
      </div>

      {/* Slides Grid */}
      {visibleSlides.length === 0 ? (
        <div
          className={`rounded-2xl border p-12 text-center ${
            dark ? "border-slate-800 bg-slate-900/50 text-slate-400" : "border-slate-200 bg-white text-slate-500"
          }`}
        >
          No slides match the current filter.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleSlides.map((slide) => {
            const simPct = Math.round(slide.similarity_to_prev * 100);
            const draftNote = noteDrafts[slide.id] ?? slide.user_notes;
            const noteDirty = draftNote !== slide.user_notes;

            return (
              <article
                key={slide.id}
                className={`group flex flex-col overflow-hidden rounded-2xl border transition-all ${
                  slide.kept
                    ? dark
                      ? "border-slate-800 bg-slate-900/85 hover:border-indigo-500/50"
                      : "border-slate-200 bg-white shadow-sm hover:border-indigo-300"
                    : dark
                      ? "border-slate-800/60 bg-slate-950/60 opacity-75"
                      : "border-slate-200/80 bg-slate-50 opacity-80"
                }`}
              >
                <div
                  onClick={() => setLightboxId(slide.id)}
                  className="relative aspect-video cursor-zoom-in overflow-hidden bg-black"
                >
                  <img
                    src={slide.thumb_url}
                    alt={`Slide ${slide.index || slide.timestamp_label}`}
                    loading="lazy"
                    className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.02]"
                  />

                  <div className="absolute left-2.5 top-2.5 flex items-center gap-1.5">
                    <span
                      className={`rounded-md px-2 py-0.5 font-mono text-xs font-bold shadow ${
                        slide.kept
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-800/90 text-slate-300"
                      }`}
                    >
                      {slide.kept ? `#${String(slide.index).padStart(2, "0")}` : reasonLabel(slide.filter_reason)}
                    </span>
                    <span className="rounded-md bg-black/75 px-2 py-0.5 font-mono text-xs font-semibold text-white">
                      {slide.timestamp_label}
                    </span>
                  </div>

                  {slide.similarity_to_prev > 0 && (
                    <span
                      title="Visual similarity compared to previous kept screenshot"
                      className={`absolute bottom-2 right-2 rounded-md px-2 py-0.5 font-mono text-[11px] font-semibold backdrop-blur-md ${
                        simPct <= 30
                          ? "bg-emerald-950/80 text-emerald-300 ring-1 ring-emerald-500/40"
                          : "bg-black/75 text-slate-200"
                      }`}
                    >
                      {simPct}% sim
                    </span>
                  )}
                </div>

                <div className="flex flex-1 flex-col gap-2.5 p-3.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      {slide.chapter_title ? (
                        <p className="truncate text-xs font-semibold text-indigo-400">
                          {slide.chapter_title}
                        </p>
                      ) : (
                        <p className={`text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
                          {slide.width}&times;{slide.height} &bull;{" "}
                          {Math.round(slide.end_time - slide.start_time)}s on screen
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      {slide.youtube_jump_url && (
                        <a
                          href={slide.youtube_jump_url}
                          target="_blank"
                          rel="noreferrer"
                          title="Open exact second on YouTube"
                          className={`rounded-lg p-1.5 transition-colors ${
                            dark
                              ? "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          }`}
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onToggleSlide(slide)}
                        className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                          slide.kept
                            ? dark
                              ? "bg-slate-800 text-slate-300 hover:bg-rose-500/20 hover:text-rose-300"
                              : "bg-slate-100 text-slate-700 hover:bg-rose-50 hover:text-rose-600"
                            : "bg-emerald-600 text-white hover:bg-emerald-500"
                        }`}
                      >
                        {slide.kept ? (
                          <>
                            <EyeOff className="h-3.5 w-3.5" />
                            Exclude
                          </>
                        ) : (
                          <>
                            <Eye className="h-3.5 w-3.5" />
                            Restore
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {(slide.ocr_text || slide.transcript_text) && (
                    <div
                      className={`max-h-24 overflow-y-auto rounded-lg p-2.5 text-[11px] leading-relaxed ${
                        dark ? "bg-slate-950/70 text-slate-300" : "bg-slate-50 text-slate-700"
                      }`}
                    >
                      {slide.ocr_text && (
                        <p className="mb-1 flex items-start gap-1">
                          <FileText className="mt-0.5 h-3 w-3 shrink-0 text-cyan-400" />
                          <span className="line-clamp-3 font-mono">{slide.ocr_text}</span>
                        </p>
                      )}
                      {slide.transcript_text && (
                        <p className={`line-clamp-2 ${dark ? "text-slate-400" : "text-slate-500"}`}>
                          {slide.transcript_text}
                        </p>
                      )}
                    </div>
                  )}

                  {slide.kept && (
                    <div className="mt-auto flex items-center gap-1.5 pt-1">
                      <StickyNote
                        className={`h-3.5 w-3.5 shrink-0 ${
                          dark ? "text-slate-500" : "text-slate-400"
                        }`}
                      />
                      <input
                        type="text"
                        value={draftNote}
                        onChange={(e) =>
                          setNoteDrafts((prev) => ({ ...prev, [slide.id]: e.target.value }))
                        }
                        onBlur={() => {
                          if (noteDirty) onSaveNotes(slide.id, draftNote);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && noteDirty) {
                            onSaveNotes(slide.id, draftNote);
                          }
                        }}
                        placeholder="Add study note..."
                        className={`w-full rounded-md border px-2 py-1 text-xs outline-none ${
                          dark
                            ? "border-slate-800 bg-slate-950/80 text-slate-200 placeholder-slate-600 focus:border-indigo-500"
                            : "border-slate-200 bg-slate-50 text-slate-800 placeholder-slate-400 focus:border-indigo-500"
                        }`}
                      />
                      {noteDirty && (
                        <button
                          type="button"
                          onClick={() => onSaveNotes(slide.id, draftNote)}
                          className="rounded-md bg-indigo-600 p-1 text-white hover:bg-indigo-500"
                        >
                          <Check className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Lightbox Inspector Modal */}
      {activeSlide && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm sm:p-6"
          onClick={() => setLightboxId(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className={`flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-2xl border ${
              dark ? "border-slate-700 bg-slate-900 text-slate-100" : "border-slate-300 bg-white text-slate-900"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-700/40 px-4 py-3">
              <div className="flex items-center gap-2.5">
                <span className="rounded-md bg-indigo-600 px-2.5 py-0.5 font-mono text-xs font-bold text-white">
                  {activeSlide.kept ? `Slide #${activeSlide.index}` : reasonLabel(activeSlide.filter_reason)}
                </span>
                <span className="font-mono text-xs font-semibold">{activeSlide.timestamp_label}</span>
                {activeSlide.similarity_to_prev > 0 && (
                  <span className="rounded bg-emerald-500/15 px-2 py-0.5 font-mono text-xs font-semibold text-emerald-400">
                    {Math.round(activeSlide.similarity_to_prev * 100)}% similar to previous
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {prevKeptSlide && (
                  <button
                    type="button"
                    onClick={() => setComparePrev((v) => !v)}
                    className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold ${
                      comparePrev
                        ? "bg-indigo-600 text-white"
                        : dark
                          ? "bg-slate-800 text-slate-300 hover:bg-slate-700"
                          : "bg-slate-100 text-slate-700"
                    }`}
                  >
                    <Columns2 className="h-3.5 w-3.5" />
                    Compare vs Prev
                  </button>
                )}
                <button
                  type="button"
                  disabled={lightboxIndex <= 0}
                  onClick={() => setLightboxId(visibleSlides[lightboxIndex - 1].id)}
                  className="rounded-lg bg-slate-800 p-1.5 text-slate-200 disabled:opacity-40"
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  disabled={lightboxIndex + 1 >= visibleSlides.length}
                  onClick={() => setLightboxId(visibleSlides[lightboxIndex + 1].id)}
                  className="rounded-lg bg-slate-800 p-1.5 text-slate-200 disabled:opacity-40"
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setLightboxId(null)}
                  className="rounded-lg bg-slate-800 p-1.5 text-slate-200 hover:bg-rose-600"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              <div className={`grid gap-4 ${comparePrev && prevKeptSlide ? "md:grid-cols-2" : "grid-cols-1"}`}>
                {comparePrev && prevKeptSlide && (
                  <div>
                    <p className="mb-1.5 font-mono text-xs font-semibold text-slate-400">
                      Previous: Slide #{prevKeptSlide.index} ({prevKeptSlide.timestamp_label})
                    </p>
                    <img
                      src={prevKeptSlide.image_url}
                      alt="Previous slide"
                      className="max-h-[60vh] w-full rounded-xl border border-slate-700/60 bg-black object-contain"
                    />
                  </div>
                )}
                <div>
                  {comparePrev && (
                    <p className="mb-1.5 font-mono text-xs font-semibold text-indigo-400">
                      Current: Slide #{activeSlide.index} ({activeSlide.timestamp_label})
                    </p>
                  )}
                  <img
                    src={activeSlide.image_url}
                    alt={`Slide ${activeSlide.index}`}
                    className="max-h-[62vh] w-full rounded-xl border border-slate-700/60 bg-black object-contain"
                  />
                </div>
              </div>

              {(activeSlide.ocr_text || activeSlide.transcript_text) && (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  {activeSlide.ocr_text && (
                    <div
                      className={`rounded-xl border p-3 text-xs ${
                        dark ? "border-slate-800 bg-slate-950" : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <h4 className="mb-1.5 font-bold text-cyan-400">Slide Text (OCR)</h4>
                      <pre className="whitespace-pre-wrap font-mono leading-relaxed">
                        {activeSlide.ocr_text}
                      </pre>
                    </div>
                  )}
                  {activeSlide.transcript_text && (
                    <div
                      className={`rounded-xl border p-3 text-xs ${
                        dark ? "border-slate-800 bg-slate-950" : "border-slate-200 bg-slate-50"
                      }`}
                    >
                      <h4 className="mb-1.5 font-bold text-emerald-400">Lecturer Explanation</h4>
                      <p className="leading-relaxed">{activeSlide.transcript_text}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
