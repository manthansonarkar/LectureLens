export type ExtractionPreset = "smart" | "strict_overlap" | "detailed";
export type ExportFormat = "pdf" | "docx" | "markdown_zip" | "images_zip";
export type PdfLayout = "study_full" | "cornell_notes" | "handout_2x1" | "grid_2x2";
export type AIProvider = "off" | "ollama" | "openai" | "gemini";

export interface ExtractionConfig {
  preset: ExtractionPreset;
  max_similarity: number;
  scroll_max_overlap: number;
  collapse_progressive: boolean;
  global_dedup: boolean;
  ignore_webcam: boolean;
  auto_crop_borders: boolean;
  skip_blank_or_facecam: boolean;
  enable_ocr: boolean;
  enable_transcript: boolean;
  ollama_vision_filter: boolean;
  vision_model: string;
  cleanup_video: boolean;
  ai_notes_provider: AIProvider;
  ai_model: string;
  ai_api_key: string;
  video_quality: "720p" | "1080p" | "best";
  sample_fps: number;
  min_stable_seconds: number;
  exclude_region: number[] | null;
}

export interface Chapter {
  title: string;
  start_time: number;
  end_time: number;
}

export interface VideoMetadata {
  video_id: string;
  source_url: string;
  title: string;
  channel: string;
  duration: number;
  thumbnail_url: string;
  chapters: Chapter[];
  has_transcript: boolean;
  transcript_language: string;
  is_local_file: boolean;
}

export interface SlideItem {
  id: string;
  index: number;
  timestamp: number;
  start_time: number;
  end_time: number;
  timestamp_label: string;
  youtube_jump_url: string | null;
  chapter_title: string | null;
  image_url: string;
  thumb_url: string;
  width: number;
  height: number;
  similarity_to_prev: number;
  scroll_overlap_to_prev: number;
  sharpness: number;
  content_density: number;
  ocr_text: string;
  transcript_text: string;
  ai_summary: string;
  user_notes: string;
  kept: boolean;
  filter_reason: string;
}

export interface PipelineStats {
  frames_scanned: number;
  stable_windows: number;
  slides_kept: number;
  duplicates_filtered: number;
  progressive_merged: number;
  webcam_masked: boolean;
  webcam_box: number[] | null;
  crop_box: number[] | null;
  elapsed_seconds: number;
}

export interface ExtractionJob {
  job_id: string;
  status:
    | "queued"
    | "inspecting"
    | "downloading"
    | "scanning"
    | "segmenting"
    | "capturing"
    | "enriching"
    | "completed"
    | "failed";
  progress: number;
  message: string;
  error: string | null;
  config: ExtractionConfig;
  metadata: VideoMetadata | null;
  slides: SlideItem[];
  stats: PipelineStats;
  lecture_summary: string;
}

export interface ProgressEventPayload {
  job_id: string;
  status: ExtractionJob["status"];
  progress: number;
  message: string;
  error: string | null;
  stats: PipelineStats;
  slides_count: number;
}

export interface HealthStatus {
  status: string;
  version: string;
  ffmpeg: boolean;
  ocr_available: boolean;
  ollama_models: string[];
}

export interface ExportRequest {
  format: ExportFormat;
  pdf_layout: PdfLayout;
  include_ocr: boolean;
  include_transcript: boolean;
  include_ai_summary: boolean;
  include_user_notes: boolean;
  title_override: string | null;
}

export const PRESET_CONFIGS: Record<ExtractionPreset, Partial<ExtractionConfig>> = {
  smart: {
    preset: "smart",
    max_similarity: 0.72,
    scroll_max_overlap: 0.30,
    collapse_progressive: true,
    global_dedup: true,
    skip_blank_or_facecam: true,
  },
  strict_overlap: {
    preset: "strict_overlap",
    max_similarity: 0.30,
    scroll_max_overlap: 0.28,
    collapse_progressive: true,
    global_dedup: true,
    skip_blank_or_facecam: true,
  },
  detailed: {
    preset: "detailed",
    max_similarity: 0.86,
    scroll_max_overlap: 0.55,
    collapse_progressive: false,
    global_dedup: false,
    skip_blank_or_facecam: true,
  },
};

export const DEFAULT_CONFIG: ExtractionConfig = {
  preset: "smart",
  max_similarity: 0.72,
  scroll_max_overlap: 0.30,
  collapse_progressive: true,
  global_dedup: true,
  ignore_webcam: true,
  auto_crop_borders: true,
  skip_blank_or_facecam: true,
  enable_ocr: true,
  enable_transcript: true,
  ollama_vision_filter: false,
  vision_model: "",
  cleanup_video: false,
  ai_notes_provider: "off",
  ai_model: "",
  ai_api_key: "",
  video_quality: "1080p",
  sample_fps: 0,
  min_stable_seconds: 0.7,
  exclude_region: null,
};
