import { Cpu, Moon, Sparkles, Sun, Terminal } from "lucide-react";
import type { HealthStatus } from "../types";

interface HeaderProps {
  dark: boolean;
  onToggleTheme: () => void;
  health: HealthStatus | null;
}

export function Header({ dark, onToggleTheme, health }: HeaderProps) {
  return (
    <header
      className={`sticky top-0 z-30 border-b backdrop-blur-xl transition-colors ${
        dark
          ? "border-slate-800/80 bg-slate-950/85 text-slate-100"
          : "border-slate-200/80 bg-white/85 text-slate-900"
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-violet-500 to-cyan-500 shadow-lg shadow-indigo-500/25">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-bold tracking-tight">LectureLens</h1>
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                  dark
                    ? "bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/30"
                    : "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200"
                }`}
              >
                v{health?.version || "1.0"}
              </span>
            </div>
            <p className={`text-xs ${dark ? "text-slate-400" : "text-slate-500"}`}>
              YouTube Lectures &rarr; Accurate Slide &amp; Page Notes (PDF / DOCX)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          {health && (
            <div className="hidden items-center gap-2 md:flex">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                  health.ffmpeg
                    ? dark
                      ? "bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/25"
                      : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                    : "bg-rose-500/15 text-rose-400"
                }`}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                FFmpeg {health.ffmpeg ? "Ready" : "Missing"}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                  health.ocr_available
                    ? dark
                      ? "bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-500/25"
                      : "bg-cyan-50 text-cyan-700 ring-1 ring-cyan-200"
                    : dark
                      ? "bg-slate-800 text-slate-400"
                      : "bg-slate-100 text-slate-500"
                }`}
              >
                <Terminal className="h-3 w-3" />
                OCR {health.ocr_available ? "Active" : "Optional"}
              </span>
              {health.ollama_models.length > 0 && (
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
                    dark
                      ? "bg-violet-500/15 text-violet-300 ring-1 ring-violet-500/30"
                      : "bg-violet-50 text-violet-700 ring-1 ring-violet-200"
                  }`}
                >
                  <Cpu className="h-3 w-3" />
                  Ollama ({health.ollama_models[0]})
                </span>
              )}
            </div>
          )}

          <button
            type="button"
            onClick={onToggleTheme}
            title={dark ? "Switch to Daylight Paper Theme" : "Switch to Dark Studio Theme"}
            className={`flex h-9 w-9 items-center justify-center rounded-lg border transition-all ${
              dark
                ? "border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700 hover:text-white"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:text-slate-900"
            }`}
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </header>
  );
}
