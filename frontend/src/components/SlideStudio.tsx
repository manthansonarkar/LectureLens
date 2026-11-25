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
    if (r === "progressive_step") return "Build Step";
    if (r === "erased_step") return "Erased Step";
    if (r === "ai_filtered") return "Filtered Out";
    if (r === "duplicate") return "Duplicate";
    if (r === "global_repeat") return "Revisited";
    if (r === "low_content") return "Blank Frame";
    if (r === "manual_excluded") return "Excluded";
    if (r === "manual_added") return "Added";
    return "Kept";
  };

  return (
    <section className="space-y-4">
      {/* Frosted Studio Toolbar */}
      <div
        className={`rounded-[24px] p-4 transition-all ${
          dark ? "glass-dark" : "glass-light"
        }`}
      >
        <div className="flex flex-col gap-3.5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <div
              className={`inline-flex rounded-full p-1 ${
                dark ? "bg-white/10" : "bg-black/[0.06]"
              }`}
            >
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
                  className={`rounded-full px-3 py-1 text-xs font-semibold transition-all ${
                    filterTab === tab
                      ? dark
                        ? "bg-white/20 text-white shadow-sm"
                        : "bg-white text-slate-900 shadow-sm"
                      : dark
                        ? "text-neutral-400 hover:text-white"
                        : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="relative flex-1 sm:w-64 sm:flex-none">
              <Search
                className={`pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 ${
                  dark ? "text-neutral-500" : "text-slate-400"
                }`}
              />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search slide text or notes..."
                className={`w-full rounded-full border py-1.5 pl-8 pr-3 text-xs outline-none ${
                  dark
                    ? "border-white/15 bg-black/30 text-white placeholder-neutral-500 focus:border-[#0A84FF]"
                    : "border-black/10 bg-white/75 text-slate-800 placeholder-slate-400 focus:border-[#007AFF]"
                }`}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div
              className={`flex items-center gap-2 rounded-full px-3 py-1.5 ${
                dark ? "glass-dark-subtle" : "glass-light-subtle"
              }`}
            >
              <Filter className="h-3.5 w-3.5 text-[#007AFF]" />
              <span className="text-[11px] font-semibold">Max Sim</span>
              <input
                type="range"
                min={15}
                max={92}
                value={Math.round(config.max_similarity * 100)}
                onChange={(e) =>
                  onConfigChange({ ...config, max_similarity: Number(e.target.value) / 100 })
                }
                className="ios-slider w-20 bg-black/15"
              />
              <span className="w-8 font-mono text-xs font-semibold text-[#007AFF]">
                {Math.round(config.max_similarity * 100)}%
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={onRefilter}
                className="inline-flex items-center gap-1 rounded-full bg-[#007AFF]/12 px-2.5 py-0.5 text-[11px] font-semibold text-[#007AFF] transition-colors hover:bg-[#007AFF] hover:text-white disabled:opacity-45"
              >
                <RefreshCw className={`h-3 w-3 ${busy ? "animate-spin" : ""}`} />
                Apply
              </button>
            </div>

            <form onSubmit={handleAddTimestamp} className="flex items-center gap-1.5">
              <input
                type="text"
                value={manualTs}
                onChange={(e) => setManualTs(e.target.value)}
                placeholder="mm:ss"
                className={`w-18 rounded-full border px-3 py-1.5 font-mono text-xs outline-none ${
                  dark
                    ? "border-white/15 bg-black/30 text-white placeholder-neutral-500"
                    : "border-black/10 bg-white/80 text-slate-800"
                }`}
              />
              <button
                type="submit"
                disabled={busy || !manualTs.trim()}
                title="Capture frame at timestamp"
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-45 ${
                  dark
                    ? "bg-white/10 text-white hover:bg-white/15"
                    : "bg-white/80 text-slate-800 ring-1 ring-black/10 hover:bg-white"
                }`}
              >
                <Plus className="h-3.5 w-3.5" />
                Add
              </button>
            </form>

            <button
              type="button"
              onClick={onOpenExport}
              disabled={keptSlides.length === 0}
              className="inline-flex items-center gap-2 rounded-full bg-[#007AFF] px-4 py-2 text-xs font-semibold text-white shadow-md shadow-[#007AFF]/25 transition-all hover:bg-[#0070EB] disabled:opacity-45"
            >
              <Download className="h-3.5 w-3.5" />
              Export PDF / DOCX
            </button>
          </div>
        </div>

        {job.lecture_summary && (
          <div
            className={`mt-4 rounded-2xl p-3.5 text-xs leading-relaxed ${
              dark ? "glass-dark-subtle text-neutral-200" : "glass-light-subtle text-slate-800"
            }`}
          >
            <div className="mb-1 font-semibold text-[#007AFF]">Lecture Overview</div>
            <p className="whitespace-pre-line">{job.lecture_summary}</p>
          </div>
        )}
      </div>

      {/* Slides Gallery */}
      {visibleSlides.length === 0 ? (
        <div
          className={`rounded-[24px] p-12 text-center text-sm ${
            dark ? "glass-dark text-neutral-400" : "glass-light text-slate-500"
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
                className={`group flex flex-col overflow-hidden rounded-[22px] transition-all ${
                  slide.kept
                    ? dark
                      ? "glass-dark hover:ring-1 hover:ring-[#0A84FF]/60"
                      : "glass-light hover:shadow-lg"
                    : dark
                      ? "glass-dark-subtle opacity-70"
                      : "glass-light-subtle opacity-75"
                }`}
              >
                <div
                  onClick={() => setLightboxId(slide.id)}
                  className="relative aspect-video cursor-zoom-in overflow-hidden bg-neutral-950"
                >
                  <img
                    src={slide.thumb_url}
                    alt={`Slide ${slide.index || slide.timestamp_label}`}
                    loading="lazy"
                    className="h-full w-full object-contain transition-transform duration-300 group-hover:scale-[1.015]"
                  />

                  <div className="absolute left-2.5 top-2.5 flex items-center gap-1.5">
                    <span
                      className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold backdrop-blur-md ${
                        slide.kept
                          ? "bg-[#007AFF] text-white shadow-sm"
                          : "bg-black/65 text-neutral-200"
                      }`}
                    >
                      {slide.kept ? `#${String(slide.index).padStart(2, "0")}` : reasonLabel(slide.filter_reason)}
                    </span>
                    <span className="rounded-full bg-black/55 px-2.5 py-0.5 font-mono text-[11px] font-medium text-white backdrop-blur-md">
                      {slide.timestamp_label}
                    </span>
                  </div>

                  {slide.similarity_to_prev > 0 && (
                    <span
                      title="Visual overlap compared to previous kept slide"
                      className={`absolute bottom-2 right-2 rounded-full px-2.5 py-0.5 font-mono text-[11px] font-semibold backdrop-blur-md ${
                        simPct <= 30
                          ? "bg-emerald-500/85 text-white"
                          : "bg-black/60 text-neutral-100"
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
                        <p className="truncate text-xs font-semibold text-[#007AFF]">
                          {slide.chapter_title}
                        </p>
                      ) : (
                        <p className={`text-xs ${dark ? "text-neutral-400" : "text-slate-500"}`}>
                          {slide.width}&times;{slide.height} &bull;{" "}
                          {Math.round(slide.end_time - slide.start_time)}s
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      {slide.youtube_jump_url && (
                        <a
                          href={slide.youtube_jump_url}
                          target="_blank"
                          rel="noreferrer"
                          title="Jump to YouTube timestamp"
                          className={`rounded-full p-1.5 transition-colors ${
                            dark
                              ? "bg-white/10 text-neutral-200 hover:bg-white/20"
                              : "bg-black/[0.05] text-slate-600 hover:bg-black/10"
                          }`}
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => onToggleSlide(slide)}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold transition-colors ${
                          slide.kept
                            ? dark
                              ? "bg-white/10 text-neutral-200 hover:bg-rose-500/20 hover:text-rose-300"
                              : "bg-black/[0.05] text-slate-700 hover:bg-rose-50 hover:text-rose-600"
                            : "bg-[#34C759] text-white hover:bg-[#2DB84E]"
                        }`}
                      >
                        {slide.kept ? (
                          <>
                            <EyeOff className="h-3.5 w-3.5" />
                            Hide
                          </>
                        ) : (
                          <>
                            <Eye className="h-3.5 w-3.5" />
                            Keep
                          </>
                        )}
                      </button>
                    </div>
                  </div>

                  {(slide.ocr_text || slide.transcript_text) && (
                    <div
                      className={`max-h-24 overflow-y-auto rounded-xl p-2.5 text-[11px] leading-relaxed ${
                        dark ? "bg-black/30 text-neutral-300" : "bg-black/[0.035] text-slate-700"
                      }`}
                    >
                      {slide.ocr_text && (
                        <p className="mb-1 flex items-start gap-1">
                          <FileText className="mt-0.5 h-3 w-3 shrink-0 text-[#007AFF]" />
                          <span className="line-clamp-3 font-mono">{slide.ocr_text}</span>
                        </p>
                      )}
                      {slide.transcript_text && (
                        <p className={`line-clamp-2 ${dark ? "text-neutral-400" : "text-slate-500"}`}>
                          {slide.transcript_text}
                        </p>
                      )}
                    </div>
                  )}

                  {slide.kept && (
                    <div className="mt-auto flex items-center gap-1.5 pt-1">
                      <StickyNote
                        className={`h-3.5 w-3.5 shrink-0 ${
                          dark ? "text-neutral-500" : "text-slate-400"
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
                        placeholder="Add personal note..."
                        className={`w-full rounded-full border px-3 py-1 text-xs outline-none ${
                          dark
                            ? "border-white/10 bg-black/25 text-white placeholder-neutral-500 focus:border-[#0A84FF]"
                            : "border-black/10 bg-white/70 text-slate-800 placeholder-slate-400 focus:border-[#007AFF]"
                        }`}
                      />
                      {noteDirty && (
                        <button
                          type="button"
                          onClick={() => onSaveNotes(slide.id, draftNote)}
                          className="rounded-full bg-[#007AFF] p-1 text-white"
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

      {/* Frosted Lightbox Modal */}
      {activeSlide && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-3 backdrop-blur-xl sm:p-6"
          onClick={() => setLightboxId(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className={`flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-[26px] ${
              dark ? "glass-dark text-white" : "glass-light text-slate-900"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-black/10 px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <span className="rounded-full bg-[#007AFF] px-3 py-0.5 font-mono text-xs font-semibold text-white">
                  {activeSlide.kept ? `Slide #${activeSlide.index}` : reasonLabel(activeSlide.filter_reason)}
                </span>
                <span className="font-mono text-xs font-semibold">{activeSlide.timestamp_label}</span>
                {activeSlide.similarity_to_prev > 0 && (
                  <span
                    className={`rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold ${
                      dark ? "bg-[#34C759]/20 text-emerald-300" : "bg-[#34C759]/15 text-emerald-700"
                    }`}
                  >
                    {Math.round(activeSlide.similarity_to_prev * 100)}% similar to previous
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {prevKeptSlide && (
                  <button
                    type="button"
                    onClick={() => setComparePrev((v) => !v)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                      comparePrev
                        ? "bg-[#007AFF] text-white"
                        : dark
                          ? "bg-white/10 text-neutral-200 hover:bg-white/15"
                          : "bg-black/[0.06] text-slate-700 hover:bg-black/10"
                    }`}
                  >
                    <Columns2 className="h-3.5 w-3.5" />
                    Compare
                  </button>
                )}
                <button
                  type="button"
                  disabled={lightboxIndex <= 0}
                  onClick={() => setLightboxId(visibleSlides[lightboxIndex - 1].id)}
                  className={`rounded-full p-1.5 disabled:opacity-35 ${
                    dark ? "bg-white/10 text-white" : "bg-black/[0.06] text-slate-800"
                  }`}
                >
                  <ArrowLeft className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  disabled={lightboxIndex + 1 >= visibleSlides.length}
                  onClick={() => setLightboxId(visibleSlides[lightboxIndex + 1].id)}
                  className={`rounded-full p-1.5 disabled:opacity-35 ${
                    dark ? "bg-white/10 text-white" : "bg-black/[0.06] text-slate-800"
                  }`}
                >
                  <ArrowRight className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setLightboxId(null)}
                  className={`rounded-full p-1.5 ${
                    dark ? "bg-white/10 text-white hover:bg-rose-500" : "bg-black/[0.06] text-slate-800 hover:bg-rose-500 hover:text-white"
                  }`}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              <div className={`grid gap-4 ${comparePrev && prevKeptSlide ? "md:grid-cols-2" : "grid-cols-1"}`}>
                {comparePrev && prevKeptSlide && (
                  <div>
                    <p className={`mb-1.5 font-mono text-xs font-semibold ${dark ? "text-neutral-400" : "text-slate-500"}`}>
                      Previous: Slide #{prevKeptSlide.index} ({prevKeptSlide.timestamp_label})
                    </p>
                    <img
                      src={prevKeptSlide.image_url}
                      alt="Previous slide"
                      className="max-h-[60vh] w-full rounded-2xl border border-black/10 bg-black object-contain"
                    />
                  </div>
                )}
                <div>
                  {comparePrev && (
                    <p className="mb-1.5 font-mono text-xs font-semibold text-[#007AFF]">
                      Current: Slide #{activeSlide.index} ({activeSlide.timestamp_label})
                    </p>
                  )}
                  <img
                    src={activeSlide.image_url}
                    alt={`Slide ${activeSlide.index}`}
                    className="max-h-[62vh] w-full rounded-2xl border border-black/10 bg-black object-contain"
                  />
                </div>
              </div>

              {(activeSlide.ocr_text || activeSlide.transcript_text) && (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  {activeSlide.ocr_text && (
                    <div
                      className={`rounded-2xl p-3.5 text-xs ${
                        dark ? "glass-dark-subtle" : "glass-light-subtle"
                      }`}
                    >
                      <h4 className="mb-1.5 font-semibold text-[#007AFF]">Extracted Slide Text</h4>
                      <pre className="whitespace-pre-wrap font-mono leading-relaxed">
                        {activeSlide.ocr_text}
                      </pre>
                    </div>
                  )}
                  {activeSlide.transcript_text && (
                    <div
                      className={`rounded-2xl p-3.5 text-xs ${
                        dark ? "glass-dark-subtle" : "glass-light-subtle"
                      }`}
                    >
                      <h4 className="mb-1.5 font-semibold text-[#34C759]">Spoken Captions</h4>
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
