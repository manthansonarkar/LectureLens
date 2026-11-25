import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Layers,
  ScanEye,
  SlidersHorizontal,
  BookOpenCheck,
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
  icon: typeof BookOpenCheck;
}[] = [
  {
    id: "smart",
    title: "Smart Lecture Notes",
    badge: "Default",
    desc: "Waits for finished slides and board writing before capturing, while hiding moving webcams.",
    icon: BookOpenCheck,
  },
  {
    id: "strict_overlap",
    title: "20–30% Similarity",
    badge: "Strict / Scroll",
    desc: "Keeps only frames with ≤30% overlap — ideal for scrolling PDFs, documents, and minimal duplicates.",
    icon: Layers,
  },
  {
    id: "detailed",
    title: "Step-by-Step",
    badge: "Detailed",
    desc: "Captures incremental bullet reveals, animations, and smaller visual additions.",
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
      className={`rounded-[24px] p-5 transition-all ${
        dark ? "glass-dark" : "glass-light"
      }`}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-[#007AFF]" />
          <h3 className="text-sm font-semibold tracking-tight">Capture Preferences</h3>
        </div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium transition-colors ${
            dark
              ? "bg-white/10 text-neutral-200 hover:bg-white/15"
              : "bg-black/[0.05] text-slate-700 hover:bg-black/[0.09]"
          }`}
        >
          {showAdvanced ? "Hide Options" : "More Options"}
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
              className={`flex flex-col rounded-2xl p-3.5 text-left transition-all ${
                active
                  ? dark
                    ? "bg-[#0A84FF]/20 ring-2 ring-[#0A84FF]"
                    : "bg-[#007AFF]/[0.09] ring-2 ring-[#007AFF] shadow-sm"
                  : dark
                    ? "glass-dark-subtle hover:bg-white/10"
                    : "glass-light-subtle hover:bg-white/80"
              }`}
            >
              <div className="flex w-full items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Icon
                    className={`h-4 w-4 ${
                      active ? "text-[#007AFF]" : dark ? "text-neutral-400" : "text-slate-500"
                    }`}
                  />
                  <span className="text-sm font-semibold">{p.title}</span>
                </div>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${
                    active
                      ? "bg-[#007AFF] text-white"
                      : dark
                        ? "bg-white/10 text-neutral-300"
                        : "bg-black/[0.06] text-slate-600"
                  }`}
                >
                  {p.badge}
                </span>
              </div>
              <p className={`mt-1.5 text-xs leading-relaxed ${dark ? "text-neutral-400" : "text-slate-600"}`}>
                {p.desc}
              </p>
            </button>
          );
        })}
      </div>

      {/* Tactile Glass Sliders */}
      <div className="mt-4 grid grid-cols-1 gap-3.5 md:grid-cols-2">
        <div className={`rounded-2xl p-3.5 ${dark ? "glass-dark-subtle" : "glass-light-subtle"}`}>
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">Max Similarity Between Slides</label>
            <span
              className={`rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold ${
                dark ? "bg-[#0A84FF]/20 text-[#60A5FA]" : "bg-[#007AFF]/10 text-[#007AFF]"
              }`}
            >
              {simPct}%
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
            style={{
              background: `linear-gradient(to right, #007AFF 0%, #007AFF ${((simPct - 15) / 77) * 100}%, ${dark ? "rgba(255,255,255,0.16)" : "rgba(15,23,42,0.12)"} ${((simPct - 15) / 77) * 100}%)`,
            }}
            className="ios-slider mt-3 w-full"
          />
          <div className={`mt-1.5 flex justify-between text-[11px] ${dark ? "text-neutral-500" : "text-slate-500"}`}>
            <span>15% Distinct</span>
            <span>30% Overlap</span>
            <span>72% Balanced</span>
            <span>92%</span>
          </div>
        </div>

        <div className={`rounded-2xl p-3.5 ${dark ? "glass-dark-subtle" : "glass-light-subtle"}`}>
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">Scrolling Page Overlap</label>
            <span
              className={`rounded-full px-2.5 py-0.5 font-mono text-xs font-semibold ${
                dark ? "bg-emerald-500/20 text-emerald-300" : "bg-emerald-500/10 text-emerald-700"
              }`}
            >
              {scrollPct}%
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
            style={{
              background: `linear-gradient(to right, #34C759 0%, #34C759 ${((scrollPct - 10) / 65) * 100}%, ${dark ? "rgba(255,255,255,0.16)" : "rgba(15,23,42,0.12)"} ${((scrollPct - 10) / 65) * 100}%)`,
            }}
            className="ios-slider mt-3 w-full"
          />
          <div className={`mt-1.5 flex justify-between text-[11px] ${dark ? "text-neutral-500" : "text-slate-500"}`}>
            <span>10%</span>
            <span>25–30% Recommended</span>
            <span>75%</span>
          </div>
        </div>
      </div>

      {/* Clean Toggle Pills */}
      <div className="mt-4 flex flex-wrap gap-2">
        {(
          [
            ["ignore_webcam", "Ignore Webcam"],
            ["collapse_progressive", "Completed Pages Only"],
            ["auto_crop_borders", "Crop Black Bars"],
            ["global_dedup", "Skip Repeat Slides"],
            ["enable_ocr", "Text Search (OCR)"],
            ["enable_transcript", "Match Captions"],
            ["ollama_vision_filter", "Offline Vision Check"],
            ["cleanup_video", "Auto-Clear Video"],
          ] as const
        ).map(([key, label]) => {
          const active = config[key];
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange({ ...config, [key]: !active })}
              className={`inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium transition-all ${
                active
                  ? dark
                    ? "bg-[#0A84FF]/20 text-white ring-1 ring-[#0A84FF]/70"
                    : "bg-[#007AFF]/10 text-[#007AFF] ring-1 ring-[#007AFF]/35"
                  : dark
                    ? "bg-white/[0.06] text-neutral-400 hover:bg-white/10"
                    : "bg-black/[0.04] text-slate-600 hover:bg-black/[0.07]"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  active ? "bg-[#007AFF]" : dark ? "bg-neutral-600" : "bg-slate-300"
                }`}
              />
              {label}
            </button>
          );
        })}
      </div>

      {/* Expandable More Options */}
      {showAdvanced && (
        <div
          className={`mt-4 grid grid-cols-1 gap-4 rounded-2xl p-4 md:grid-cols-3 ${
            dark ? "glass-dark-subtle" : "glass-light-subtle"
          }`}
        >
          <div>
            <label className="mb-1.5 block text-xs font-semibold">Video Quality</label>
            <select
              value={config.video_quality}
              onChange={(e) =>
                onChange({
                  ...config,
                  video_quality: e.target.value as ExtractionConfig["video_quality"],
                })
              }
              className={`w-full rounded-xl border px-3 py-2 text-xs font-medium outline-none ${
                dark
                  ? "border-white/15 bg-black/40 text-white"
                  : "border-black/10 bg-white/80 text-slate-800"
              }`}
            >
              <option value="1080p">1080p HD (Recommended)</option>
              <option value="720p">720p Fast</option>
              <option value="best">Highest Available</option>
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-semibold">
              Optional Summary Model
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
                      : "";
                onChange({ ...config, ai_notes_provider: prov, ai_model: defaultModel });
              }}
              className={`w-full rounded-xl border px-3 py-2 text-xs font-medium outline-none ${
                dark
                  ? "border-white/15 bg-black/40 text-white"
                  : "border-black/10 bg-white/80 text-slate-800"
              }`}
            >
              <option value="off">Off (Fastest — OCR + Captions Only)</option>
              <option value="ollama">
                Local Ollama {health?.ollama_models?.length ? `(${health.ollama_models[0]})` : ""}
              </option>
              <option value="openai">Custom OpenAI-Compatible API</option>
            </select>
          </div>

          {config.ai_notes_provider !== "off" ? (
            <div className="space-y-2">
              <label className="block text-xs font-semibold">
                Model &amp; {config.ai_notes_provider === "ollama" ? "Name" : "API Key"}
              </label>
              <input
                type="text"
                value={config.ai_model}
                onChange={(e) => onChange({ ...config, ai_model: e.target.value })}
                placeholder="Model name"
                className={`w-full rounded-xl border px-3 py-1.5 text-xs outline-none ${
                  dark
                    ? "border-white/15 bg-black/40 text-white"
                    : "border-black/10 bg-white/80 text-slate-800"
                }`}
              />
              {config.ai_notes_provider !== "ollama" && (
                <input
                  type="password"
                  value={config.ai_api_key}
                  onChange={(e) => onChange({ ...config, ai_api_key: e.target.value })}
                  placeholder="API key (in memory only)"
                  className={`w-full rounded-xl border px-3 py-1.5 text-xs outline-none ${
                    dark
                      ? "border-white/15 bg-black/40 text-white"
                      : "border-black/10 bg-white/80 text-slate-800"
                  }`}
                />
              )}
            </div>
          ) : (
            <div>
              <label className="mb-1.5 block text-xs font-semibold">
                Scan Rate (0 = Auto)
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
                className={`w-full rounded-xl border px-3 py-2 text-xs outline-none ${
                  dark
                    ? "border-white/15 bg-black/40 text-white"
                    : "border-black/10 bg-white/80 text-slate-800"
                }`}
              />
            </div>
          )}
        </div>
      )}
    </section>
  );
}
