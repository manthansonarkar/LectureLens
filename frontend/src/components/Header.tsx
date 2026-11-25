import { Aperture, CheckCircle2, Moon, Sun } from "lucide-react";
import type { HealthStatus } from "../types";

interface HeaderProps {
  dark: boolean;
  onToggleTheme: () => void;
  health: HealthStatus | null;
}

export function Header({ dark, onToggleTheme, health }: HeaderProps) {
  return (
    <header
      className={`sticky top-0 z-30 border-b backdrop-blur-2xl backdrop-saturate-180 transition-colors ${
        dark
          ? "border-white/10 bg-neutral-950/65 text-white"
          : "border-white/70 bg-white/65 text-slate-900"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-2xl shadow-sm transition-transform ${
              dark
                ? "bg-white/10 text-white ring-1 ring-white/20"
                : "bg-gradient-to-b from-[#0A84FF] to-[#007AFF] text-white shadow-blue-500/25"
            }`}
          >
            <Aperture className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[17px] font-semibold tracking-tight">LectureLens</h1>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                  dark
                    ? "bg-white/10 text-neutral-300"
                    : "bg-black/5 text-slate-600"
                }`}
              >
                v{health?.version || "1.0"}
              </span>
            </div>
            <p className={`text-xs ${dark ? "text-neutral-400" : "text-slate-500"}`}>
              Lecture Slide &amp; Notes Capture
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {health && (
            <div className="hidden items-center gap-1.5 md:flex">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                  health.ffmpeg
                    ? dark
                      ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/25"
                      : "bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/20"
                    : "bg-rose-500/15 text-rose-500"
                }`}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                FFmpeg
              </span>
              {health.ocr_available && (
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                    dark
                      ? "bg-white/10 text-neutral-200 ring-1 ring-white/15"
                      : "bg-black/[0.04] text-slate-700 ring-1 ring-black/[0.06]"
                  }`}
                >
                  OCR Ready
                </span>
              )}
              {health.ollama_models.length > 0 && (
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                    dark
                      ? "bg-white/10 text-neutral-300 ring-1 ring-white/15"
                      : "bg-black/[0.04] text-slate-600 ring-1 ring-black/[0.06]"
                  }`}
                >
                  Local Ollama
                </span>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={onToggleTheme}
            title={dark ? "Switch to Daylight Glass" : "Switch to Dark Glass"}
            className={`flex h-9 w-9 items-center justify-center rounded-full transition-all ${
              dark
                ? "bg-white/10 text-neutral-200 ring-1 ring-white/15 hover:bg-white/15"
                : "bg-white/80 text-slate-700 ring-1 ring-black/10 shadow-sm hover:bg-white"
            }`}
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </header>
  );
}
