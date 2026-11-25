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
    label: "MIT OCW: Intro to Algorithms",
    url: "https://www.youtube.com/watch?v=ZA-tUyM_y7s",
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

  const cardBg = dark
    ? "border-slate-800 bg-slate-900/80 shadow-2xl shadow-black/40"
    : "border-slate-200 bg-white shadow-xl shadow-slate-200/60";

  return (
    <section className={`rounded-2xl border p-5 sm:p-7 backdrop-blur-xl transition-all ${cardBg}`}>
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight sm:text-2xl">
            Capture Every Slide &amp; Page Automatically
          </h2>
          <p className={`mt-1 text-sm ${dark ? "text-slate-400" : "text-slate-600"}`}>
            Ignores webcam motion &amp; blurry fades, collapses progressive board writing into finished pages, and exports crisp PDF &amp; Word notes.
          </p>
        </div>

        <div
          className={`inline-flex self-start rounded-xl p-1 ${
            dark ? "bg-slate-950 ring-1 ring-slate-800" : "bg-slate-100 ring-1 ring-slate-200"
          }`}
        >
          <button
            type="button"
            onClick={() => setSourceTab("youtube")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              sourceTab === "youtube"
                ? "bg-indigo-600 text-white shadow-sm"
                : dark
                  ? "text-slate-400 hover:text-slate-200"
                  : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Link2 className="h-3.5 w-3.5" />
            YouTube Link
          </button>
          <button
            type="button"
            onClick={() => setSourceTab("upload")}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              sourceTab === "upload"
                ? "bg-indigo-600 text-white shadow-sm"
                : dark
                  ? "text-slate-400 hover:text-slate-200"
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
            className="flex flex-col gap-3 sm:flex-row"
          >
            <div className="relative flex-1">
              <Link2
                className={`pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 ${
                  dark ? "text-slate-500" : "text-slate-400"
                }`}
              />
              <input
                type="url"
                required
                value={url}
                onChange={(e) => onUrlChange(e.target.value)}
                placeholder="Paste YouTube lecture URL (e.g. https://www.youtube.com/watch?v=...)"
                className={`w-full rounded-xl border py-3 pl-10 pr-4 text-sm outline-none transition-all ${
                  dark
                    ? "border-slate-700 bg-slate-950 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/25"
                    : "border-slate-300 bg-slate-50 text-slate-900 placeholder-slate-400 focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/20"
                }`}
              />
            </div>

            <div className="flex gap-2">
              <button
                type="button"
                disabled={!url.trim() || inspecting || extracting}
                onClick={() => onInspect()}
                className={`inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                  dark
                    ? "border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
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
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/25 transition-all hover:from-indigo-500 hover:to-violet-500 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
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

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className={`text-xs font-medium ${dark ? "text-slate-500" : "text-slate-500"}`}>
              Try sample lecture:
            </span>
            {SAMPLE_LECTURES.map((sample) => (
              <button
                key={sample.url}
                type="button"
                onClick={() => {
                  onUrlChange(sample.url);
                  onInspect(sample.url);
                }}
                className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                  dark
                    ? "bg-slate-800/80 text-slate-300 hover:bg-indigo-500/20 hover:text-indigo-300"
                    : "bg-slate-100 text-slate-600 hover:bg-indigo-50 hover:text-indigo-700"
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
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-all ${
            dragOver
              ? "border-indigo-500 bg-indigo-500/10"
              : dark
                ? "border-slate-700 bg-slate-950/50 hover:border-indigo-500/60"
                : "border-slate-300 bg-slate-50 hover:border-indigo-400"
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
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-500/15 text-indigo-400">
            <Film className="h-6 w-6" />
          </div>
          <p className="text-sm font-semibold">Drop a recorded lecture video here or click to browse</p>
          <p className={`mt-1 text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
            Supports MP4, MKV, WebM, MOV — processed 100% locally on your machine
          </p>
        </div>
      )}
    </section>
  );
}
