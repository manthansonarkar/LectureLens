"""Pydantic schemas and configuration models for LectureLens."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ExtractionPreset(StrEnum):
    SMART_LECTURE = "smart"
    OVERLAP_STRICT = "strict_overlap"
    STEP_BY_STEP = "detailed"


class ExportFormat(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    MARKDOWN_ZIP = "markdown_zip"
    IMAGES_ZIP = "images_zip"


class PdfLayout(StrEnum):
    STUDY_FULL = "study_full"
    CORNELL_NOTES = "cornell_notes"
    HANDOUT_2X1 = "handout_2x1"
    GRID_2X2 = "grid_2x2"


class ExtractionConfig(BaseModel):
    preset: ExtractionPreset = ExtractionPreset.SMART_LECTURE
    max_similarity: float = Field(default=0.72, ge=0.05, le=0.98)
    scroll_max_overlap: float = Field(default=0.30, ge=0.05, le=0.90)
    collapse_progressive: bool = True
    global_dedup: bool = True
    ignore_webcam: bool = True
    auto_crop_borders: bool = True
    skip_blank_or_facecam: bool = True
    enable_ocr: bool = True
    enable_transcript: bool = True
    ollama_vision_filter: bool = False
    vision_model: str = ""
    cleanup_video: bool = False
    ai_notes_provider: Literal["off", "ollama", "openai"] = "off"
    ai_model: str = ""
    ai_api_key: str = ""
    video_quality: Literal["720p", "1080p", "best"] = "1080p"
    sample_fps: float = Field(default=0.0, ge=0.0, le=5.0)
    min_stable_seconds: float = Field(default=0.7, ge=0.2, le=5.0)
    exclude_region: list[float] | None = Field(
        default=None,
        description="Optional normalized [x1, y1, x2, y2] exclusion box in [0, 1].",
    )

    @classmethod
    def from_preset(cls, preset: ExtractionPreset, **overrides: object) -> ExtractionConfig:
        """Build a well-tuned ExtractionConfig for a named preset."""
        preset_defaults: dict[ExtractionPreset, dict[str, object]] = {
            ExtractionPreset.SMART_LECTURE: dict(
                max_similarity=0.72,
                scroll_max_overlap=0.30,
                collapse_progressive=True,
                global_dedup=True,
                skip_blank_or_facecam=True,
            ),
            ExtractionPreset.OVERLAP_STRICT: dict(
                max_similarity=0.30,
                scroll_max_overlap=0.28,
                collapse_progressive=True,
                global_dedup=True,
                skip_blank_or_facecam=True,
            ),
            ExtractionPreset.STEP_BY_STEP: dict(
                max_similarity=0.86,
                scroll_max_overlap=0.55,
                collapse_progressive=False,
                global_dedup=False,
                skip_blank_or_facecam=True,
            ),
        }
        params = {"preset": preset, **preset_defaults[preset], **overrides}
        return cls(**params)  # type: ignore[arg-type]


class Chapter(BaseModel):
    title: str
    start_time: float
    end_time: float


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class VideoMetadata(BaseModel):
    video_id: str
    source_url: str
    title: str
    channel: str = "Unknown Channel"
    duration: float = 0.0
    thumbnail_url: str = ""
    chapters: list[Chapter] = Field(default_factory=list)
    has_transcript: bool = False
    transcript_language: str = ""
    is_local_file: bool = False


class SlideItem(BaseModel):
    id: str
    index: int
    timestamp: float
    start_time: float
    end_time: float
    timestamp_label: str
    youtube_jump_url: str | None = None
    chapter_title: str | None = None
    image_path: str = Field(default="", exclude=True)
    thumb_path: str = Field(default="", exclude=True)
    image_url: str = ""
    thumb_url: str = ""
    width: int = 0
    height: int = 0
    similarity_to_prev: float = 0.0
    scroll_overlap_to_prev: float = 0.0
    sharpness: float = 0.0
    content_density: float = 0.0
    ocr_text: str = ""
    transcript_text: str = ""
    ai_summary: str = ""
    user_notes: str = ""
    kept: bool = True
    filter_reason: str = "kept"


class PipelineStats(BaseModel):
    frames_scanned: int = 0
    stable_windows: int = 0
    slides_kept: int = 0
    duplicates_filtered: int = 0
    progressive_merged: int = 0
    webcam_masked: bool = False
    webcam_box: list[float] | None = None
    crop_box: list[int] | None = None
    elapsed_seconds: float = 0.0


class JobStatus(StrEnum):
    QUEUED = "queued"
    INSPECTING = "inspecting"
    DOWNLOADING = "downloading"
    SCANNING = "scanning"
    SEGMENTING = "segmenting"
    CAPTURING = "capturing"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractionJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = "Queued..."
    error: str | None = None
    config: ExtractionConfig
    metadata: VideoMetadata | None = None
    slides: list[SlideItem] = Field(default_factory=list)
    stats: PipelineStats = Field(default_factory=PipelineStats)
    lecture_summary: str = ""


class InspectRequest(BaseModel):
    url: str


class ExtractRequest(BaseModel):
    url: str
    config: ExtractionConfig = Field(default_factory=ExtractionConfig)


class RefilterRequest(BaseModel):
    config: ExtractionConfig


class SlideUpdateRequest(BaseModel):
    kept: bool | None = None
    user_notes: str | None = None
    ocr_text: str | None = None
    transcript_text: str | None = None


class AddFrameRequest(BaseModel):
    timestamp: float = Field(ge=0.0)


class ExportRequest(BaseModel):
    format: ExportFormat = ExportFormat.PDF
    pdf_layout: PdfLayout = PdfLayout.STUDY_FULL
    include_ocr: bool = True
    include_transcript: bool = True
    include_ai_summary: bool = True
    include_user_notes: bool = True
    title_override: str | None = None
