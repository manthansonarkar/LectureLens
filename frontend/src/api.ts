import type {
  ExportRequest,
  ExtractionConfig,
  ExtractionJob,
  HealthStatus,
  ProgressEventPayload,
  VideoMetadata,
} from "./types";

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) msg = String(body.detail);
    } catch {
      // ignore non-json error bodies
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function getHealth(): Promise<HealthStatus> {
  return jsonFetch<HealthStatus>("/api/health");
}

export async function inspectUrl(url: string): Promise<VideoMetadata> {
  return jsonFetch<VideoMetadata>("/api/inspect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function startExtraction(
  url: string,
  config: ExtractionConfig
): Promise<{ job_id: string }> {
  return jsonFetch<{ job_id: string }>("/api/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, config }),
  });
}

export async function uploadVideo(
  file: File,
  config: ExtractionConfig
): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("config_json", JSON.stringify(config));
  return jsonFetch<{ job_id: string }>("/api/upload", {
    method: "POST",
    body: form,
  });
}

export async function getJob(jobId: string): Promise<ExtractionJob> {
  return jsonFetch<ExtractionJob>(`/api/jobs/${jobId}`);
}

export function subscribeJobEvents(
  jobId: string,
  onProgress: (payload: ProgressEventPayload) => void,
  onError: () => void
): () => void {
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.addEventListener("progress", (ev) => {
    try {
      const data = JSON.parse((ev as MessageEvent).data) as ProgressEventPayload;
      onProgress(data);
    } catch {
      // ignore malformed event
    }
  });
  es.onerror = () => {
    es.close();
    onError();
  };
  return () => es.close();
}

export async function refilterJob(
  jobId: string,
  config: ExtractionConfig
): Promise<ExtractionJob> {
  return jsonFetch<ExtractionJob>(`/api/jobs/${jobId}/refilter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
}

export async function updateSlide(
  jobId: string,
  slideId: string,
  patch: {
    kept?: boolean;
    user_notes?: string;
    ocr_text?: string;
    transcript_text?: string;
  }
): Promise<ExtractionJob> {
  return jsonFetch<ExtractionJob>(`/api/jobs/${jobId}/slides/${slideId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function addManualFrame(
  jobId: string,
  timestamp: number
): Promise<ExtractionJob> {
  return jsonFetch<ExtractionJob>(`/api/jobs/${jobId}/add-frame`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ timestamp }),
  });
}

export async function downloadExport(jobId: string, req: ExportRequest): Promise<void> {
  const res = await fetch(`/api/jobs/${jobId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let msg = `Export failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) msg = String(body.detail);
    } catch {
      // ignore
    }
    throw new Error(msg);
  }
  const blob = await res.blob();
  const disp = res.headers.get("content-disposition") || "";
  const match = disp.match(/filename="?([^"]+)"?/i);
  const filename = match ? match[1] : `lecturelens_notes.${req.format}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hrs > 0) {
    return `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}
