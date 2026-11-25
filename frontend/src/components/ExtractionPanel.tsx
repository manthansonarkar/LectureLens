import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Layers,
  ScanEye,
  SlidersHorizontal,
  Sparkles,
  Wand2,
} from "lucide-react";
import { PRESET_CONFIGS, type ExtractionConfig, type ExtractionPreset, type HealthStatus } from "../types";

interface ExtractionPanelProps {
  dark: boolean;
  config: ExtractionConfig;
  onChange: (cfg: ExtractionConfig) => void;
  health: HealthStatus | null;
}

const PRESET_CARDS: {
  id: ExtractionPreset;
  title: string;
  badge: string;
  desc: string;
  icon: typeof Sparkles;
}[] = [
  {
    id: "smart",
    title: "Smart Lecture Notes",
    badge: "Recommended",
    desc: "Captures finished slides & handwritten pages, collapses progressive reveals, ignores webcam motion.",
    icon: Sparkles,
  },
  {
    id: "strict_overlap",
    title: "Max 20–30% Similarity",
    badge: "Strict / Scroll",
    desc: "Enforces ≤30% overlap between consecutive captures — ideal for scrolling PDFs, docs, and strict dedup.",
    icon: Layers,
  },
  {
    id: "detailed",
    title: "Step-by-Step Animations",
    badge: "High Detail",
    desc: "Keeps incremental bullet reveals, build animations, and smaller visual updates (≥14% change).",
    icon: ScanEye,
  },
];

export function ExtractionPanel({ dark, config, onChange, health }: ExtractionPanelProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  const selectPreset = (preset: ExtractionPreset) => {
    onChange({
      ...config,
      ...PRESET_CONFIGS[preset],
      preset,
    });
  };

  const simPct = Math.round(config.max_similarity * 100);
  const scrollPct = Math.round(config.scroll_max_overlap * 100);

  return (
    <section
      className={`rounded-2xl border p-5 transition-colors ${
        dark ? "border-slate-800 bg-slate-900/75" : "border-slate-200 bg-white shadow-sm"
      }`}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-indigo-400" />
          <h3 className="text-sm font-bold uppercase tracking-wider">Extraction Intelligence</h3>
        </div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
            dark
              ? "bg-slate-800 text-slate-300 hover:bg-slate-700"
              : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`}
        >
          {showAdvanced ? "Hide Fine Tuning" : "Fine Tuning & AI Options"}
          {showAdvanced ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* 3 Preset Mode Cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {PRESET_CARDS.map((p) => {
          const Icon = p.icon;
          const active = config.preset === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => selectPreset(p.id)}
              className={`group flex flex-col rounded-xl border p-3.5 text-left transition-all ${
                active
                  ? dark
                    ? "border-indigo-500 bg-indigo-500/15 ring-1 ring-indigo-500/40"
                    : "border-indigo-600 bg-indigo-50/70 ring-1 ring-indigo-600/25"
                  : dark
                    ? "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                    : "border-slate-200 bg-slate-50/60 hover:border-slate-300"
              }`}
            >
              <div className="flex w-full items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Icon
                    className={`h-4 w-4 ${
                      active ? "text-indigo-400" : dark ? "text-slate-400" : "text-slate-500"
                    }`}
                  />
                  <span className="text-sm font-bold">{p.title}</span>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    active
                      ? "bg-indigo-600 text-white"
                      : dark
                        ? "bg-slate-800 text-slate-400"
                        : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {p.badge}
                </span>
              </div>
              <p className={`mt-1.5 text-xs leading-relaxed ${dark ? "text-slate-400" : "text-slate-600"}`}>
                {p.desc}
              </p>
            </button>
          );
        })}
      </div>

      {/* Core Similarity Sliders */}
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div
          className={`rounded-xl border p-3.5 ${
            dark ? "border-slate-800 bg-slate-950/50" : "border-slate-200 bg-slate-50/70"
          }`}
        >
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">
              Max Allowed Similarity Between Slides
            </label>
            <span className="rounded-md bg-indigo-600/15 px-2 py-0.5 font-mono text-xs font-bold text-indigo-400">
              {simPct}% max overlap
            </span>
          </div>
          <input
            type="range"
            min={15}
            max={92}
            step={1}
            value={simPct}
            onChange={(e) =>
              onChange({ ...config, max_similarity: Number(e.target.value) / 100 })
            }
            className="mt-2.5 w-full accent-indigo-500"
          />
          <div className={`mt-1 flex justify-between text-[11px] ${dark ? "text-slate-500" : "text-slate-500"}`}>
            <span>15% (Ultra Distinct)</span>
            <span>30% (20–30% Overlap)</span>
            <span>72% (Slide Dedup)</span>
            <span>92%</span>
          </div>
        </div>

        <div
          className={`rounded-xl border p-3.5 ${
            dark ? "border-slate-800 bg-slate-950/50" : "border-slate-200 bg-slate-50/70"
          }`}
        >
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">
              Scrolling Notes Max Overlap
            </label>
            <span className="rounded-md bg-cyan-500/15 px-2 py-0.5 font-mono text-xs font-bold text-cyan-400">
              {scrollPct}% scroll overlap
            </span>
          </div>
          <input
            type="range"
            min={10}
            max={75}
            step={1}
            value={scrollPct}
            onChange={(e) =>
              onChange({ ...config, scroll_max_overlap: Number(e.target.value) / 100 })
            }
            className="mt-2.5 w-full accent-cyan-500"
          />
          <div className={`mt-1 flex justify-between text-[11px] ${dark ? "text-slate-500" : "text-slate-500"}`}>
            <span>10% (Minimal)</span>
            <span>25–30% (Recommended)</span>
            <span>75% (Frequent)</span>
          </div>
        </div>
      </div>

      {/* Quick Feature Pills */}
      <div className="mt-4 flex flex-wrap gap-2">
        {(
          [
            ["ignore_webcam", "Auto-Mask Webcam"],
            ["collapse_progressive", "Keep Completed Board/Builds"],
            ["auto_crop_borders", "Auto-Crop Black Bars"],
            ["global_dedup", "Global Repeat Dedup"],
            ["enable_ocr", "OCR Searchable Text"],
            ["enable_transcript", "Align Spoken Transcript"],
            ["ollama_vision_filter", "Offline Ollama Vision Filter"],
            ["cleanup_video", "Auto-Delete Video Cache"],
          ] as const
        ).map(([key, label]) => {
          const active = config[key];
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ ...config, [key]: !active })}
              className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all ${
                active
                  ? dark
                    ? "border-indigo-500/50 bg-indigo-500/15 text-indigo-200"
                    : "border-indigo-300 bg-indigo-50 text-indigo-700"
                  : dark
                    ? "border-slate-800 bg-slate-950 text-slate-400 hover:border-slate-700"
                    : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  active ? "bg-indigo-400" : dark ? "bg-slate-700" : "bg-slate-300"
                }`}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Expandable Advanced & AI Notes Section */}
      {showAdvanced && (
        <div
          className={`mt-4 grid grid-cols-1 gap-4 rounded-xl border p-4 md:grid-cols-3 ${
            dark ? "border-slate-800 bg-slate-950/60" : "border-slate-200 bg-slate-50"
          }`}
        >
          <div>
            <label className="mb-1.5 block text-xs font-semibold">Stream Resolution</label>
            <select
              value={config.video_quality}
              onChange={(e) =>
                onChange({
                  ...config,
                  video_quality: e.target.value as ExtractionConfig["video_quality"],
                })
              }
              className={`w-full rounded-lg border px-3 py-2 text-xs font-medium outline-none ${
                dark
                  ? "border-slate-700 bg-slate-900 text-slate-200"
                  : "border-slate-300 bg-white text-slate-800"
              }`}
            >
              <option value="1080p">1080p Full HD (Recommended)</option>
              <option value="720p">720p Fast Download</option>
              <option value="best">Best Available (up to 4K)</option>
            </select>
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold">
              <Wand2 className="h-3.5 w-3.5 text-violet-400" />
              AI Study Notes Polish (Optional)
            </label>
            <select
              value={config.ai_notes_provider}
              onChange={(e) => {
                const prov = e.target.value as ExtractionConfig["ai_notes_provider"];
                const defaultModel =
                  prov === "ollama"
                    ? health?.ollama_models?.[0] || "gemma3:4b"
                    : prov === "openai"
                      ? "gpt-4o-mini"
                      : prov === "gemini"
                        ? "gemini-2.5-flash"
                        : "";
                onChange({ ...config, ai_notes_provider: prov, ai_model: defaultModel });
              }}
              className={`w-full rounded-lg border px-3 py-2 text-xs font-medium outline-none ${
                dark
                  ? "border-slate-700 bg-slate-900 text-slate-200"
                  : "border-slate-300 bg-white text-slate-800"
              }`}
            >
              <option value="off">Off (Fastest — OCR + Spoken Transcript)</option>
              <option value="ollama">
                Local Ollama AI {health?.ollama_models?.length ? `(${health.ollama_models[0]})` : ""}
              </option>
              <option value="gemini">Google Gemini API</option>
              <option value="openai">OpenAI API</option>
            </select>
          </div>

          {config.ai_notes_provider !== "off" ? (
            <div className="space-y-2">
              <label className="block text-xs font-semibold">
                Model &amp; {config.ai_notes_provider === "ollama" ? "Tag" : "API Key"}
              </label>
              <input
                type="text"
                value={config.ai_model}
                onChange={(e) => onChange({ ...config, ai_model: e.target.value })}
                placeholder="Model name"
                className={`w-full rounded-lg border px-3 py-1.5 text-xs outline-none ${
                  dark
                    ? "border-slate-700 bg-slate-900 text-slate-200"
                    : "border-slate-300 bg-white text-slate-800"
                }`}
              />
              {config.ai_notes_provider !== "ollama" && (
                <input
                  type="password"
                  value={config.ai_api_key}
                  onChange={(e) => onChange({ ...config, ai_api_key: e.target.value })}
                  placeholder="Paste API key (kept in memory only)"
                  className={`w-full rounded-lg border px-3 py-1.5 text-xs outline-none ${
                    dark
                      ? "border-slate-700 bg-slate-900 text-slate-200"
                      : "border-slate-300 bg-white text-slate-800"
                  }`}
                />
              )}
            </div>
          ) : (
            <div>
              <label className="mb-1.5 block text-xs font-semibold">
                Scan Frame Rate (0 = Auto Adaptive)
              </label>
              <input
                type="number"
                min={0}
                max={4}
                step={0.5}
                value={config.sample_fps}
                onChange={(e) =>
                  onChange({ ...config, sample_fps: Math.max(0, Number(e.target.value)) })
                }
                className={`w-full rounded-lg border px-3 py-2 text-xs outline-none ${
                  dark
                    ? "border-slate-700 bg-slate-900 text-slate-200"
                    : "border-slate-300 bg-white text-slate-800"
                }`}
              />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
