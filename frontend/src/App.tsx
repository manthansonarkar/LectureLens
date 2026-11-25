import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, X } from "lucide-react";
import {
  addManualFrame,
  getHealth,
  getJob,
  inspectUrl,
  refilterJob,
  startExtraction,
  subscribeJobEvents,
  updateSlide,
  uploadVideo,
} from "./api";
import { ExportDialog } from "./components/ExportDialog";
import { ExtractionPanel } from "./components/ExtractionPanel";
import { Header } from "./components/Header";
import { HeroInput } from "./components/HeroInput";
import { PipelineConsole } from "./components/PipelineConsole";
import { SlideStudio } from "./components/SlideStudio";
import { VideoPreviewCard } from "./components/VideoPreviewCard";
import {
  DEFAULT_CONFIG,
  type ExtractionConfig,
  type ExtractionJob,
  type HealthStatus,
  type SlideItem,
  type VideoMetadata,
} from "./types";

export default function App() {
  // Default to crisp Daylight Frosted Glass (iPhone Liquid Glass style), with Dark Glass toggle
  const [dark, setDark] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [url, setUrl] = useState("");
  const [config, setConfig] = useState<ExtractionConfig>(DEFAULT_CONFIG);
  const [previewMeta, setPreviewMeta] = useState<VideoMetadata | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [studioBusy, setStudioBusy] = useState(false);
  const [job, setJob] = useState<ExtractionJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null));

    const params = new URLSearchParams(window.location.search);
    const existingJobId = params.get("job");
    if (existingJobId) {
      getJob(existingJobId)
        .then((loaded) => {
          setJob(loaded);
          setConfig(loaded.config);
          if (loaded.metadata) {
            setPreviewMeta(loaded.metadata);
            if (!loaded.metadata.is_local_file) {
              setUrl(loaded.metadata.source_url);
            }
          }
        })
        .catch(() => {
          // ignore stale job id in URL
        });
    }

    return () => {
      unsubRef.current?.();
    };
  }, []);

  const attachJobStream = useCallback(
    (jobId: string) => {
      unsubRef.current?.();
      window.history.replaceState(null, "", `?job=${encodeURIComponent(jobId)}`);

      const pollOnce = async () => {
        try {
          const latest = await getJob(jobId);
          setJob(latest);
          if (latest.metadata) setPreviewMeta(latest.metadata);
          if (latest.status === "completed" || latest.status === "failed") {
            setExtracting(false);
            if (latest.error) setError(latest.error);
            return true;
          }
        } catch {
          // ignore transient poll errors
        }
        return false;
      };

      const unsub = subscribeJobEvents(
        jobId,
        (ev) => {
          setJob((prev) =>
            prev && prev.job_id === jobId
              ? {
                  ...prev,
                  status: ev.status,
                  progress: ev.progress,
                  message: ev.message,
                  error: ev.error,
                  stats: ev.stats,
                }
              : {
                  job_id: jobId,
                  status: ev.status,
                  progress: ev.progress,
                  message: ev.message,
                  error: ev.error,
                  config,
                  metadata: previewMeta,
                  slides: [],
                  stats: ev.stats,
                  lecture_summary: "",
                }
          );
          if (ev.status === "completed" || ev.status === "failed") {
            void pollOnce();
          }
        },
        () => {
          const timer = window.setInterval(async () => {
            const done = await pollOnce();
            if (done) window.clearInterval(timer);
          }, 1200);
        }
      );
      unsubRef.current = unsub;
    },
    [config, previewMeta]
  );

  const handleInspect = async (urlOverride?: string) => {
    const target = (urlOverride ?? url).trim();
    if (!target) return;
    setError(null);
    setInspecting(true);
    try {
      const meta = await inspectUrl(target);
      setPreviewMeta(meta);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to inspect YouTube link");
    } finally {
      setInspecting(false);
    }
  };

  const handleExtract = async () => {
    const target = url.trim();
    if (!target) return;
    setError(null);
    setExtracting(true);
    setJob(null);
    try {
      const { job_id } = await startExtraction(target, config);
      attachJobStream(job_id);
    } catch (err) {
      setExtracting(false);
      setError(err instanceof Error ? err.message : "Could not start extraction");
    }
  };

  const handleUploadFile = async (file: File) => {
    setError(null);
    setPreviewMeta(null);
    setExtracting(true);
    setJob(null);
    try {
      const { job_id } = await uploadVideo(file, config);
      attachJobStream(job_id);
    } catch (err) {
      setExtracting(false);
      setError(err instanceof Error ? err.message : "Failed to upload video");
    }
  };

  const handleRefilter = async () => {
    if (!job) return;
    setStudioBusy(true);
    setError(null);
    try {
      const updated = await refilterJob(job.job_id, config);
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Re-filter failed");
    } finally {
      setStudioBusy(false);
    }
  };

  const handleToggleSlide = async (slide: SlideItem) => {
    if (!job) return;
    setStudioBusy(true);
    try {
      const updated = await updateSlide(job.job_id, slide.id, { kept: !slide.kept });
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update slide");
    } finally {
      setStudioBusy(false);
    }
  };

  const handleSaveNotes = async (slideId: string, notes: string) => {
    if (!job) return;
    try {
      const updated = await updateSlide(job.job_id, slideId, { user_notes: notes });
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save note");
    }
  };

  const handleAddManualTimestamp = async (seconds: number) => {
    if (!job) return;
    setStudioBusy(true);
    try {
      const updated = await addManualFrame(job.job_id, seconds);
      setJob(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not capture frame");
    } finally {
      setStudioBusy(false);
    }
  };

  const activeMeta = job?.metadata || previewMeta;

  return (
    <div
      className={`relative min-h-screen overflow-x-hidden transition-colors duration-300 ${
        dark ? "bg-[#0B0C10] text-white" : "bg-[#ECF1F8] text-slate-900"
      }`}
    >
      {/* Subtle Ambient Apple-style Wallpaper Gradient Depth Behind Frosted Glass */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div
          className={`absolute -left-32 -top-28 h-[34rem] w-[34rem] rounded-full blur-[110px] transition-opacity ${
            dark ? "bg-sky-500/18 opacity-75" : "bg-sky-300/45 opacity-90"
          }`}
        />
        <div
          className={`absolute -right-24 top-16 h-[30rem] w-[30rem] rounded-full blur-[110px] transition-opacity ${
            dark ? "bg-blue-600/15 opacity-70" : "bg-blue-200/55 opacity-95"
          }`}
        />
        <div
          className={`absolute bottom-0 left-1/3 h-[28rem] w-[36rem] rounded-full blur-[120px] transition-opacity ${
            dark ? "bg-teal-500/12 opacity-60" : "bg-emerald-200/40 opacity-85"
          }`}
        />
      </div>

      <div className="relative z-10">
        <Header dark={dark} onToggleTheme={() => setDark((d) => !d)} health={health} />

        <main className="mx-auto max-w-6xl space-y-5 px-4 py-6 sm:px-6 lg:py-8">
          {error && (
            <div
              className={`flex items-center justify-between gap-3 rounded-2xl border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-sm backdrop-blur-xl ${
                dark ? "text-rose-300" : "text-rose-700"
              }`}
            >
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
              <button type="button" onClick={() => setError(null)}>
                <X className="h-4 w-4" />
              </button>
            </div>
          )}

          <HeroInput
            dark={dark}
            url={url}
            onUrlChange={setUrl}
            onInspect={handleInspect}
            onExtract={handleExtract}
            onUploadFile={handleUploadFile}
            inspecting={inspecting}
            extracting={extracting}
          />

          {activeMeta && (
            <VideoPreviewCard
              dark={dark}
              metadata={activeMeta}
              excludeRegion={config.exclude_region}
              onExcludeRegionChange={(region) => setConfig({ ...config, exclude_region: region })}
            />
          )}

          <ExtractionPanel
            dark={dark}
            config={config}
            onChange={setConfig}
            health={health}
          />

          {job && <PipelineConsole dark={dark} job={job} />}

          {job && job.status === "completed" && (
            <SlideStudio
              dark={dark}
              job={job}
              config={config}
              onConfigChange={setConfig}
              onRefilter={handleRefilter}
              onToggleSlide={handleToggleSlide}
              onSaveNotes={handleSaveNotes}
              onAddManualTimestamp={handleAddManualTimestamp}
              onOpenExport={() => setExportOpen(true)}
              busy={studioBusy}
            />
          )}
        </main>

        {job && activeMeta && (
          <ExportDialog
            dark={dark}
            open={exportOpen}
            onClose={() => setExportOpen(false)}
            jobId={job.job_id}
            defaultTitle={activeMeta.title}
            slidesCount={job.slides.filter((s) => s.kept).length}
          />
        )}
      </div>
    </div>
  );
}
