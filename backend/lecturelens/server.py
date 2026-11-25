"""FastAPI backend, SSE live progress streaming, job manager, and static UI server."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import __version__
from .detector import (
    CachedScan,
    build_slides_from_decisions,
    capture_frame_hd,
    scan_video,
    segment_candidates,
)
from .downloader import download_youtube_video, inspect_local_video, inspect_youtube
from .exporter import export_docx, export_images_zip, export_markdown_zip, export_pdf
from .models import (
    AddFrameRequest,
    ExportFormat,
    ExportRequest,
    ExtractionConfig,
    ExtractionJob,
    ExtractRequest,
    InspectRequest,
    JobStatus,
    RefilterRequest,
    SlideItem,
    SlideUpdateRequest,
    TranscriptSegment,
    VideoMetadata,
)
from .ocr import (
    align_transcript_to_slides,
    enrich_slides,
    extract_text_from_image,
    list_ollama_models,
    ocr_available,
)
from .utils import (
    build_youtube_jump_url,
    find_ffmpeg,
    format_timestamp,
    get_cache_root,
    is_youtube_url,
    sanitize_filename,
)


@dataclass
class _JobRuntime:
    job: ExtractionJob
    work_dir: Path
    scan: CachedScan | None = None
    transcript: list[TranscriptSegment] = field(default_factory=list)
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)


_JOBS: dict[str, _JobRuntime] = {}
_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Create and configure the LectureLens FastAPI application."""
    app = FastAPI(
        title="LectureLens API",
        version=__version__,
        description="Automated YouTube lecture slide & page extraction studio.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _notify(runtime: _JobRuntime) -> None:
        payload = {
            "job_id": runtime.job.job_id,
            "status": runtime.job.status.value,
            "progress": round(runtime.job.progress, 3),
            "message": runtime.job.message,
            "error": runtime.job.error,
            "stats": runtime.job.stats.model_dump(),
            "slides_count": sum(1 for s in runtime.job.slides if s.kept),
        }
        for q in list(runtime.subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def _renumber_kept(slides: list[SlideItem]) -> None:
        slides.sort(key=lambda s: s.timestamp)
        idx = 1
        for s in slides:
            if s.kept:
                s.index = idx
                idx += 1
            else:
                s.index = 0

    def _run_pipeline_sync(
        runtime: _JobRuntime,
        source_url: str | None = None,
        local_video_path: Path | None = None,
    ) -> None:
        t0 = time.perf_counter()
        job = runtime.job
        cfg = job.config
        url_prefix = f"/api/jobs/{job.job_id}/media"

        def _prog(stage: str, pct: float, msg: str) -> None:
            status_map = {
                "inspecting": JobStatus.INSPECTING,
                "downloading": JobStatus.DOWNLOADING,
                "scanning": JobStatus.SCANNING,
                "segmenting": JobStatus.SEGMENTING,
                "capturing": JobStatus.CAPTURING,
                "enriching": JobStatus.ENRICHING,
            }
            job.status = status_map.get(stage, JobStatus.SCANNING)
            job.progress = max(0.0, min(0.99, pct))
            job.message = msg
            _notify(runtime)

        try:
            if local_video_path is not None:
                _prog("inspecting", 0.04, "Inspecting uploaded video...")
                meta = inspect_local_video(local_video_path)
                transcript: list[TranscriptSegment] = []
                video_path = local_video_path
            else:
                assert source_url is not None
                _prog("inspecting", 0.02, "Fetching YouTube metadata, chapters & captions...")
                meta, transcript = inspect_youtube(source_url, fetch_transcript=cfg.enable_transcript)
                job.metadata = meta
                runtime.transcript = transcript
                _prog("downloading", 0.05, f"Preparing {cfg.video_quality} stream...")
                video_path = download_youtube_video(
                    source_url,
                    meta.video_id,
                    quality=cfg.video_quality,
                    progress_cb=_prog,
                )

            job.metadata = meta
            runtime.transcript = transcript

            _prog("scanning", 0.22, "Running fast multi-signal visual scan...")
            scan = scan_video(video_path, meta, cfg, progress_cb=_prog)
            runtime.scan = scan

            _prog("segmenting", 0.67, "Segmenting slides, collapsing incremental builds & masking webcam...")
            decisions, stats = segment_candidates(scan, cfg)
            job.stats = stats

            _prog("capturing", 0.70, f"Extracting {stats.slides_kept} crisp HD frames...")
            slides = build_slides_from_decisions(
                scan,
                decisions,
                cfg,
                runtime.work_dir,
                url_prefix=url_prefix,
                include_rejected_thumbs=True,
                progress_cb=_prog,
            )
            job.slides = slides

            _prog("enriching", 0.88, "Aligning transcript & running OCR...")
            summary = enrich_slides(
                slides,
                transcript,
                cfg,
                lecture_title=meta.title,
                progress_cb=_prog,
            )
            job.lecture_summary = summary

            stats.elapsed_seconds = round(time.perf_counter() - t0, 2)
            stats.slides_kept = sum(1 for s in slides if s.kept)
            if cfg.cleanup_video and video_path.exists():
                try:
                    video_path.unlink()
                except OSError:
                    pass
            job.stats = stats
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.message = f"Ready! Captured {stats.slides_kept} slides in {stats.elapsed_seconds:.1f}s."
            _notify(runtime)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.message = f"Extraction failed: {exc}"
            _notify(runtime)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        ffmpeg_ok = True
        try:
            find_ffmpeg()
        except Exception:
            ffmpeg_ok = False
        return {
            "status": "ok",
            "version": __version__,
            "ffmpeg": ffmpeg_ok,
            "ocr_available": ocr_available(),
            "ollama_models": list_ollama_models(),
        }

    @app.post("/api/inspect", response_model=VideoMetadata)
    def inspect_url(req: InspectRequest) -> VideoMetadata:
        url = req.url.strip()
        if not is_youtube_url(url):
            raise HTTPException(status_code=400, detail="Please enter a valid YouTube video URL.")
        try:
            meta, _ = inspect_youtube(url, fetch_transcript=False)
            return meta
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not inspect YouTube link: {exc}") from exc

    @app.post("/api/extract")
    async def start_extract(req: ExtractRequest) -> dict[str, str]:
        url = req.url.strip()
        if not is_youtube_url(url):
            raise HTTPException(status_code=400, detail="Please enter a valid YouTube video URL.")

        job_id = uuid.uuid4().hex[:12]
        work_dir = get_cache_root() / "jobs" / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        job = ExtractionJob(job_id=job_id, config=req.config)
        runtime = _JobRuntime(job=job, work_dir=work_dir)
        _JOBS[job_id] = runtime

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _run_pipeline_sync, runtime, url, None)
        return {"job_id": job_id}

    @app.post("/api/upload")
    async def upload_and_extract(
        file: Annotated[UploadFile, File()],
        config_json: Annotated[str, Form()] = "{}",
    ) -> dict[str, str]:
        try:
            cfg = ExtractionConfig(**(json.loads(config_json) if config_json else {}))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid config JSON: {exc}") from exc

        job_id = uuid.uuid4().hex[:12]
        work_dir = get_cache_root() / "jobs" / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(Path(file.filename or "lecture.mp4").stem) + (
            Path(file.filename or ".mp4").suffix or ".mp4"
        )
        video_path = work_dir / safe_name
        with video_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        job = ExtractionJob(job_id=job_id, config=cfg)
        runtime = _JobRuntime(job=job, work_dir=work_dir)
        _JOBS[job_id] = runtime

        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _run_pipeline_sync, runtime, None, video_path)
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}", response_model=ExtractionJob)
    def get_job(job_id: str) -> ExtractionJob:
        runtime = _JOBS.get(job_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Job not found")
        return runtime.job

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str) -> EventSourceResponse:
        runtime = _JOBS.get(job_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Job not found")

        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        runtime.subscribers.append(q)

        async def _stream():
            try:
                # Send initial snapshot immediately
                init_payload = {
                    "job_id": runtime.job.job_id,
                    "status": runtime.job.status.value,
                    "progress": round(runtime.job.progress, 3),
                    "message": runtime.job.message,
                    "error": runtime.job.error,
                    "stats": runtime.job.stats.model_dump(),
                    "slides_count": sum(1 for s in runtime.job.slides if s.kept),
                }
                yield {"event": "progress", "data": json.dumps(init_payload)}
                if runtime.job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
                    return

                while True:
                    data = await q.get()
                    yield {"event": "progress", "data": json.dumps(data)}
                    if data["status"] in {JobStatus.COMPLETED.value, JobStatus.FAILED.value}:
                        break
            finally:
                if q in runtime.subscribers:
                    runtime.subscribers.remove(q)

        return EventSourceResponse(_stream())

    @app.post("/api/jobs/{job_id}/refilter", response_model=ExtractionJob)
    def refilter_job(job_id: str, req: RefilterRequest) -> ExtractionJob:
        runtime = _JOBS.get(job_id)
        if not runtime or not runtime.scan:
            raise HTTPException(status_code=404, detail="Completed scan not found for re-filtering")

        prev_by_id = {s.id: s for s in runtime.job.slides}
        runtime.job.config = req.config
        decisions, stats = segment_candidates(runtime.scan, req.config)
        url_prefix = f"/api/jobs/{job_id}/media"
        new_slides = build_slides_from_decisions(
            runtime.scan,
            decisions,
            req.config,
            runtime.work_dir,
            url_prefix=url_prefix,
            include_rejected_thumbs=True,
        )

        # Preserve existing OCR, transcript, and user edits across matching IDs
        for sl in new_slides:
            old = prev_by_id.get(sl.id)
            if old:
                sl.ocr_text = old.ocr_text
                sl.user_notes = old.user_notes
                sl.ai_summary = old.ai_summary
                sl.transcript_text = old.transcript_text

        if req.config.enable_transcript and runtime.transcript:
            align_transcript_to_slides(new_slides, runtime.transcript)
        if req.config.enable_ocr and ocr_available():
            for sl in new_slides:
                if sl.kept and not sl.ocr_text and sl.image_path:
                    sl.ocr_text = extract_text_from_image(sl.image_path)

        stats.elapsed_seconds = runtime.job.stats.elapsed_seconds
        stats.slides_kept = sum(1 for s in new_slides if s.kept)
        runtime.job.slides = new_slides
        runtime.job.stats = stats
        runtime.job.message = f"Re-filtered to {stats.slides_kept} slides (instant mode)."
        return runtime.job

    @app.patch("/api/jobs/{job_id}/slides/{slide_id}", response_model=ExtractionJob)
    def update_slide(job_id: str, slide_id: str, req: SlideUpdateRequest) -> ExtractionJob:
        runtime = _JOBS.get(job_id)
        if not runtime:
            raise HTTPException(status_code=404, detail="Job not found")

        target = next((s for s in runtime.job.slides if s.id == slide_id), None)
        if not target:
            raise HTTPException(status_code=404, detail="Slide not found")

        if req.kept is not None:
            target.kept = req.kept
            target.filter_reason = "kept" if req.kept else "manual_excluded"
            if req.kept:
                # Ensure HD image exists if restoring a previously rejected frame
                png_p = runtime.work_dir / "slides" / f"{target.id}.png"
                thumb_p = runtime.work_dir / "thumbs" / f"{target.id}.jpg"
                if not png_p.exists() and runtime.scan:
                    crop = runtime.scan.crop_box if runtime.job.config.auto_crop_borders else None
                    w, h = capture_frame_hd(runtime.scan.video_path, target.timestamp, png_p, thumb_p, crop)
                    target.width, target.height = w, h
                    target.image_path = str(png_p)
                    target.image_url = f"/api/jobs/{job_id}/media/slides/{target.id}.png"
                if runtime.job.config.enable_ocr and not target.ocr_text and ocr_available():
                    target.ocr_text = extract_text_from_image(target.image_path)

        if req.user_notes is not None:
            target.user_notes = req.user_notes
        if req.ocr_text is not None:
            target.ocr_text = req.ocr_text
        if req.transcript_text is not None:
            target.transcript_text = req.transcript_text

        _renumber_kept(runtime.job.slides)
        if runtime.job.config.enable_transcript and runtime.transcript:
            align_transcript_to_slides(runtime.job.slides, runtime.transcript)
        runtime.job.stats.slides_kept = sum(1 for s in runtime.job.slides if s.kept)
        return runtime.job

    @app.post("/api/jobs/{job_id}/add-frame", response_model=ExtractionJob)
    def add_manual_frame(job_id: str, req: AddFrameRequest) -> ExtractionJob:
        runtime = _JOBS.get(job_id)
        if not runtime or not runtime.scan or not runtime.job.metadata:
            raise HTTPException(status_code=404, detail="Video scan not found")

        ts = min(max(0.0, req.timestamp), runtime.scan.duration or req.timestamp)
        cid = f"manual_{uuid.uuid4().hex[:8]}"
        png_p = runtime.work_dir / "slides" / f"{cid}.png"
        thumb_p = runtime.work_dir / "thumbs" / f"{cid}.jpg"
        crop = runtime.scan.crop_box if runtime.job.config.auto_crop_borders else None
        w, h = capture_frame_hd(runtime.scan.video_path, ts, png_p, thumb_p, crop)

        jump_url = None
        if not runtime.job.metadata.is_local_file:
            jump_url = build_youtube_jump_url(runtime.job.metadata.source_url, ts)

        ocr_txt = extract_text_from_image(png_p) if (runtime.job.config.enable_ocr and ocr_available()) else ""
        slide = SlideItem(
            id=cid,
            index=0,
            timestamp=round(ts, 3),
            start_time=round(ts, 3),
            end_time=round(min(runtime.scan.duration, ts + 2.0), 3),
            timestamp_label=format_timestamp(ts),
            youtube_jump_url=jump_url,
            image_path=str(png_p),
            thumb_path=str(thumb_p),
            image_url=f"/api/jobs/{job_id}/media/slides/{cid}.png",
            thumb_url=f"/api/jobs/{job_id}/media/thumbs/{cid}.jpg",
            width=w,
            height=h,
            ocr_text=ocr_txt,
            kept=True,
            filter_reason="manual_added",
        )
        runtime.job.slides.append(slide)
        _renumber_kept(runtime.job.slides)
        if runtime.job.config.enable_transcript and runtime.transcript:
            align_transcript_to_slides(runtime.job.slides, runtime.transcript)
        runtime.job.stats.slides_kept = sum(1 for s in runtime.job.slides if s.kept)
        return runtime.job

    @app.get("/api/jobs/{job_id}/media/{kind}/{filename}")
    def get_media(job_id: str, kind: str, filename: str) -> FileResponse:
        runtime = _JOBS.get(job_id)
        if not runtime or kind not in {"slides", "thumbs"}:
            raise HTTPException(status_code=404, detail="Media not found")
        safe = Path(filename).name
        target = (runtime.work_dir / kind / safe).resolve()
        expected_parent = (runtime.work_dir / kind).resolve()
        if target.parent != expected_parent or not target.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)

    @app.post("/api/jobs/{job_id}/export")
    def export_job(job_id: str, req: ExportRequest) -> FileResponse:
        runtime = _JOBS.get(job_id)
        if not runtime or not runtime.job.metadata:
            raise HTTPException(status_code=404, detail="Job not found")

        kept = [s for s in runtime.job.slides if s.kept]
        if not kept:
            raise HTTPException(status_code=400, detail="No slides are currently marked as kept.")

        stem = sanitize_filename(req.title_override or runtime.job.metadata.title)
        exports_dir = runtime.work_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        if req.format == ExportFormat.PDF:
            out_path = exports_dir / f"{stem}_notes.pdf"
            export_pdf(out_path, runtime.job.metadata, runtime.job.slides, req, runtime.job.lecture_summary)
            media_type = "application/pdf"
        elif req.format == ExportFormat.DOCX:
            out_path = exports_dir / f"{stem}_notes.docx"
            export_docx(out_path, runtime.job.metadata, runtime.job.slides, req, runtime.job.lecture_summary)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif req.format == ExportFormat.MARKDOWN_ZIP:
            out_path = exports_dir / f"{stem}_markdown_notes.zip"
            export_markdown_zip(out_path, runtime.job.metadata, runtime.job.slides, req, runtime.job.lecture_summary)
            media_type = "application/zip"
        else:
            out_path = exports_dir / f"{stem}_slides.zip"
            export_images_zip(out_path, runtime.job.slides)
            media_type = "application/zip"

        return FileResponse(out_path, media_type=media_type, filename=out_path.name)

    # Serve built Vite React Studio UI if compiled into static/
    if _STATIC_DIR.exists() and (_STATIC_DIR / "index.html").exists():
        assets_dir = _STATIC_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str) -> Response:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (_STATIC_DIR / full_path).resolve()
            if full_path and candidate.is_file() and str(candidate).startswith(str(_STATIC_DIR.resolve())):
                return FileResponse(candidate)
            return HTMLResponse((_STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    return app


app = create_app()
