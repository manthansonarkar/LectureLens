import { useRef, useState } from "react";
import { Film, Link2, Loader2, Play, Search, Upload } from "lucide-react";

interface HeroInputProps {
  dark: boolean;
  url: string;
  onUrlChange: (url: string) => void;
  onInspect: (urlOverride?: string) => void;
  onExtract: () => void;
  onUploadFile: (file: File) => void;
  inspecting: boolean;
  extracting: boolean;
}

const SAMPLE_LECTURES = [
  {
    label: "3Blue1Brown: Neural Networks (18m)",
    url: "https://www.youtube.com/watch?v=aircAruvnKk",
  },
  {
    label: "Reservoir Geomechanics (8m)",
    url: "https://www.youtube.com/watch?v=-1YVWlYPR1c",
  },
];

export function HeroInput({
  dark,
  url,
  onUrlChange,
  onInspect,
  onExtract,
  onUploadFile,
  inspecting,
  extracting,
}: HeroInputProps) {
  const [sourceTab, setSourceTab] = useState<"youtube" | "upload">("youtube");
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <section
      className={`rounded-[26px] p-5 sm:p-7 transition-all ${
        dark ? "glass-dark" : "glass-light"
      }`}
    >
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
            Capture Every Lecture Slide &amp; Page
          </h2>
          <p className={`mt-1 text-sm ${dark ? "text-neutral-400" : "text-slate-600"}`}>
            Paste a YouTube lecture or drop a video file to save clean, deduplicated screenshots as PDF or Word notes.
          </p>
        </div>

        {/* iOS Segmented Control */}
        <div
          className={`inline-flex self-start rounded-full p-1 ${
            dark ? "bg-white/10 ring-1 ring-white/10" : "bg-black/[0.06]"
          }`}
        >
          <button
            type="button"
            onClick={() => setSourceTab("youtube")}
            className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
              sourceTab === "youtube"
                ? dark
                  ? "bg-white/20 text-white shadow-sm"
                  : "bg-white text-slate-900 shadow-sm"
                : dark
                  ? "text-neutral-400 hover:text-white"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Link2 className="h-3.5 w-3.5" />
            YouTube Link
          </button>
          <button
            type="button"
            onClick={() => setSourceTab("upload")}
            className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all ${
              sourceTab === "upload"
                ? dark
                  ? "bg-white/20 text-white shadow-sm"
                  : "bg-white text-slate-900 shadow-sm"
                : dark
                  ? "text-neutral-400 hover:text-white"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Upload className="h-3.5 w-3.5" />
            Local Video
          </button>
        </div>
      </div>

      {sourceTab === "youtube" ? (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onExtract();
            }}
            className="flex flex-col gap-2.5 sm:flex-row"
          >
            <div className="relative flex-1">
              <Link2
                className={`pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 ${
                  dark ? "text-neutral-500" : "text-slate-400"
                }`}
              />
              <input
                type="url"
                required
                value={url}
                onChange={(e) => onUrlChange(e.target.value)}
                placeholder="Paste YouTube URL (e.g. https://www.youtube.com/watch?v=...)"
                className={`w-full rounded-2xl border py-3 pl-11 pr-4 text-sm outline-none transition-all ${
                  dark
                    ? "border-white/15 bg-black/30 text-white placeholder-neutral-500 focus:border-[#0A84FF] focus:ring-4 focus:ring-[#0A84FF]/20"
                    : "border-black/10 bg-white/75 text-slate-900 placeholder-slate-400 shadow-inner focus:border-[#007AFF] focus:bg-white focus:ring-4 focus:ring-[#007AFF]/15"
                }`}
              />
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                disabled={!url.trim() || inspecting || extracting}
                onClick={() => onInspect()}
                className={`inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-45 ${
                  dark
                    ? "bg-white/10 text-white ring-1 ring-white/15 hover:bg-white/15"
                    : "bg-white/80 text-slate-800 ring-1 ring-black/10 shadow-sm hover:bg-white"
                }`}
              >
                {inspecting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                Preview
              </button>

              <button
                type="submit"
                disabled={!url.trim() || extracting}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-2xl bg-[#007AFF] px-5 py-3 text-sm font-semibold text-white shadow-md shadow-[#007AFF]/25 transition-all hover:bg-[#0070EB] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-45 sm:flex-none"
              >
                {extracting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Extracting...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 fill-current" />
                    Extract Slides
                  </>
                )}
              </button>
            </div>
          </form>

          <div className="mt-3.5 flex flex-wrap items-center gap-2">
            <span className={`text-xs font-medium ${dark ? "text-neutral-500" : "text-slate-500"}`}>
              Sample lectures:
            </span>
            {SAMPLE_LECTURES.map((sample) => (
              <button
                key={sample.url}
                type="button"
                onClick={() => {
                  onUrlChange(sample.url);
                  onInspect(sample.url);
                }}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  dark
                    ? "bg-white/[0.08] text-neutral-300 hover:bg-white/15"
                    : "bg-black/[0.04] text-slate-700 hover:bg-[#007AFF]/10 hover:text-[#007AFF]"
                }`}
              >
                {sample.label}
              </button>
            ))}
          </div>
        </>
      ) : (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) onUploadFile(f);
          }}
          onClick={() => fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-all ${
            dragOver
              ? "border-[#007AFF] bg-[#007AFF]/10"
              : dark
                ? "border-white/15 bg-black/20 hover:border-white/30"
                : "border-black/15 bg-white/45 hover:border-[#007AFF]/50"
          }`}
        >
          <input
            ref={fileRef}
            type="file"
            accept="video/*,.mp4,.mkv,.webm,.mov"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUploadFile(f);
            }}
          />
          <div
            className={`mb-3 flex h-12 w-12 items-center justify-center rounded-2xl ${
              dark ? "bg-white/10 text-[#0A84FF]" : "bg-[#007AFF]/10 text-[#007AFF]"
            }`}
          >
            <Film className="h-6 w-6" />
          </div>
          <p className="text-sm font-semibold">Drop a recorded lecture video or click to browse</p>
          <p className={`mt-1 text-xs ${dark ? "text-neutral-400" : "text-slate-500"}`}>
            MP4, MKV, WebM, or MOV — processed directly on your computer
          </p>
        </div>
      )}
    </section>
  );
}
