import { useRef, useState } from "react";
import { Captions, Clock, Crop, Eraser, ListVideo, User } from "lucide-react";
import { formatDuration } from "../api";
import type { VideoMetadata } from "../types";

interface VideoPreviewCardProps {
  dark: boolean;
  metadata: VideoMetadata;
  excludeRegion: number[] | null;
  onExcludeRegionChange: (region: number[] | null) => void;
}

export function VideoPreviewCard({
  dark,
  metadata,
  excludeRegion,
  onExcludeRegionChange,
}: VideoPreviewCardProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [draftBox, setDraftBox] = useState<number[] | null>(null);

  const toNorm = (clientX: number, clientY: number) => {
    const el = boxRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    return { x, y };
  };

  const activeBox = draftBox || excludeRegion;

  return (
    <div
      className={`rounded-2xl border p-4 sm:p-5 transition-colors ${
        dark ? "border-slate-800 bg-slate-900/75" : "border-slate-200 bg-white shadow-sm"
      }`}
    >
      <div className="flex flex-col gap-5 lg:flex-row">
        {metadata.thumbnail_url && (
          <div className="w-full shrink-0 lg:w-80">
            <div
              ref={boxRef}
              onMouseDown={(e) => {
                const pt = toNorm(e.clientX, e.clientY);
                setDragStart(pt);
                setDraftBox([pt.x, pt.y, pt.x, pt.y]);
              }}
              onMouseMove={(e) => {
                if (!dragStart) return;
                const pt = toNorm(e.clientX, e.clientY);
                setDraftBox([
                  Math.min(dragStart.x, pt.x),
                  Math.min(dragStart.y, pt.y),
                  Math.max(dragStart.x, pt.x),
                  Math.max(dragStart.y, pt.y),
                ]);
              }}
              onMouseUp={() => {
                if (draftBox) {
                  const w = Math.abs(draftBox[2] - draftBox[0]);
                  const h = Math.abs(draftBox[3] - draftBox[1]);
                  if (w >= 0.04 && h >= 0.04) {
                    onExcludeRegionChange(draftBox.map((n) => Number(n.toFixed(3))));
                  }
                }
                setDragStart(null);
                setDraftBox(null);
              }}
              className="relative aspect-video cursor-crosshair select-none overflow-hidden rounded-xl border border-slate-700/50 bg-black"
            >
              <img
                src={metadata.thumbnail_url}
                alt={metadata.title}
                draggable={false}
                className="h-full w-full object-cover"
              />
              {activeBox && (
                <div
                  style={{
                    left: `${activeBox[0] * 100}%`,
                    top: `${activeBox[1] * 100}%`,
                    width: `${(activeBox[2] - activeBox[0]) * 100}%`,
                    height: `${(activeBox[3] - activeBox[1]) * 100}%`,
                  }}
                  className="pointer-events-none absolute border-2 border-dashed border-rose-400 bg-rose-500/25"
                >
                  <span className="absolute left-1 top-1 rounded bg-rose-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    Ignored Zone
                  </span>
                </div>
              )}
              <div className="pointer-events-none absolute bottom-2 right-2 rounded-md bg-black/75 px-2 py-0.5 font-mono text-xs font-semibold text-white">
                {formatDuration(metadata.duration)}
              </div>
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px]">
              <span className={`inline-flex items-center gap-1 ${dark ? "text-slate-400" : "text-slate-500"}`}>
                <Crop className="h-3 w-3" />
                Drag on preview to manually mask a webcam/chat region
              </span>
              {excludeRegion && (
                <button
                  type="button"
                  onClick={() => onExcludeRegionChange(null)}
                  className="inline-flex items-center gap-1 font-semibold text-rose-400 hover:text-rose-300"
                >
                  <Eraser className="h-3 w-3" />
                  Clear
                </button>
              )}
            </div>
          </div>
        )}

        <div className="flex-1 space-y-3">
          <div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${
                  dark ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-700"
                }`}
              >
                <User className="h-3 w-3" />
                {metadata.channel}
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${
                  dark ? "bg-slate-800 text-slate-300" : "bg-slate-100 text-slate-700"
                }`}
              >
                <Clock className="h-3 w-3" />
                {formatDuration(metadata.duration)}
              </span>
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 font-medium ${
                  metadata.has_transcript
                    ? dark
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-emerald-50 text-emerald-700"
                    : dark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-100 text-slate-500"
                }`}
              >
                <Captions className="h-3 w-3" />
                {metadata.has_transcript
                  ? `Captions Ready (${metadata.transcript_language})`
                  : "No Captions Found"}
              </span>
            </div>

            <h3 className="mt-2.5 text-lg font-bold leading-snug">{metadata.title}</h3>
          </div>

          {metadata.chapters.length > 0 && (
            <div>
              <p
                className={`mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider ${
                  dark ? "text-slate-400" : "text-slate-500"
                }`}
              >
                <ListVideo className="h-3.5 w-3.5" />
                {metadata.chapters.length} Chapters Detected
              </p>
              <div className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto pr-1">
                {metadata.chapters.map((ch, idx) => (
                  <span
                    key={`${ch.start_time}-${idx}`}
                    className={`inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium ${
                      dark
                        ? "border-slate-800 bg-slate-950/80 text-slate-300"
                        : "border-slate-200 bg-slate-50 text-slate-700"
                    }`}
                  >
                    <span className="font-mono text-indigo-400">{formatDuration(ch.start_time)}</span>
                    <span className="truncate max-w-[180px]">{ch.title}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
