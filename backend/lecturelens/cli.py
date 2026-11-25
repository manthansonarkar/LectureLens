"""Rich CLI for LectureLens web studio and headless slide/document extraction."""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from . import __version__
from .detector import build_slides_from_decisions, scan_video, segment_candidates
from .downloader import download_youtube_video, inspect_local_video, inspect_youtube
from .exporter import export_docx, export_images_zip, export_markdown_zip, export_pdf
from .models import (
    ExportFormat,
    ExportRequest,
    ExtractionConfig,
    ExtractionPreset,
    PdfLayout,
    TranscriptSegment,
)
from .ocr import enrich_slides
from .utils import format_timestamp, is_youtube_url, sanitize_filename

app = typer.Typer(
    name="lecturelens",
    help="Turn YouTube lectures or local lecture videos into crisp, deduplicated slide notes (PDF & DOCX).",
    add_completion=False,
)
console = Console()


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on.")] = 8000,
    open_browser: Annotated[bool, typer.Option("--open", help="Open Web Studio in default browser.")] = False,
) -> None:
    """Launch the LectureLens Web Studio."""
    url = f"http://{host}:{port}"
    console.print(
        Panel.fit(
            f"[bold cyan]LectureLens v{__version__}[/bold cyan]\n"
            f"Studio running at [link={url}]{url}[/link]",
            border_style="bright_blue",
        )
    )
    if open_browser:
        webbrowser.open(url)
    uvicorn.run("lecturelens.server:app", host=host, port=port, log_level="info")


@app.command()
def extract(
    source: Annotated[str, typer.Argument(help="YouTube URL or path to local video file.")],
    output_dir: Annotated[Path, typer.Option("--out", "-o", help="Directory for exported files.")] = Path("outputs"),
    preset: Annotated[
        ExtractionPreset,
        typer.Option(
            "--preset",
            help="smart (balanced slides/boards), strict_overlap (<=30% overlap), detailed (every step).",
        ),
    ] = ExtractionPreset.SMART_LECTURE,
    max_similarity: Annotated[
        float | None,
        typer.Option("--max-similarity", min=0.05, max=0.98, help="Override max visual similarity threshold (0.05-0.98)."),
    ] = None,
    scroll_overlap: Annotated[
        float | None,
        typer.Option("--scroll-overlap", min=0.05, max=0.90, help="Override max scroll overlap ratio (0.05-0.90)."),
    ] = None,
    formats: Annotated[
        list[ExportFormat] | None,
        typer.Option(
            "--format",
            "-f",
            help="Export formats to generate (pdf, docx, markdown_zip, images_zip). Defaults to pdf & docx.",
        ),
    ] = None,
    pdf_layout: Annotated[
        PdfLayout, typer.Option("--pdf-layout", help="PDF layout style.")
    ] = PdfLayout.STUDY_FULL,
    quality: Annotated[
        str, typer.Option("--quality", "-q", help="YouTube stream quality: 720p, 1080p, or best.")
    ] = "1080p",
    no_ocr: Annotated[bool, typer.Option("--no-ocr", help="Disable OCR text extraction.")] = False,
    no_transcript: Annotated[bool, typer.Option("--no-transcript", help="Disable YouTube transcript alignment.")] = False,
    ai_provider: Annotated[
        str, typer.Option("--ai", help="Optional summary provider: off, ollama, or openai.")
    ] = "off",
    ai_model: Annotated[str, typer.Option("--ai-model", help="Optional model name for AI notes.")] = "",
    vision_filter: Annotated[
        bool, typer.Option("--vision-filter", help="Use offline local Ollama vision model to filter useless frames.")
    ] = False,
    cleanup: Annotated[
        bool, typer.Option("--cleanup", help="Delete downloaded video stream after extraction to save disk space.")
    ] = False,
) -> None:
    """Extract slides from a YouTube URL or local video and export PDF/DOCX notes."""
    t0 = time.perf_counter()
    selected_formats = formats or [ExportFormat.PDF, ExportFormat.DOCX]
    overrides: dict[str, object] = {
        "video_quality": quality,
        "enable_ocr": not no_ocr,
        "enable_transcript": not no_transcript,
        "ai_notes_provider": ai_provider,
        "ai_model": ai_model,
        "ollama_vision_filter": vision_filter,
        "cleanup_video": cleanup,
    }
    if max_similarity is not None:
        overrides["max_similarity"] = max_similarity
    if scroll_overlap is not None:
        overrides["scroll_max_overlap"] = scroll_overlap

    config = ExtractionConfig.from_preset(preset, **overrides)
    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=32),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Starting...", total=100)

        def _cb(_stage: str, pct: float, msg: str) -> None:
            progress.update(task_id, completed=int(pct * 100), description=msg)

        transcript: list[TranscriptSegment] = []
        if is_youtube_url(source):
            _cb("inspecting", 0.02, "Fetching YouTube metadata & transcript...")
            meta, transcript = inspect_youtube(source, fetch_transcript=config.enable_transcript)
            video_path = download_youtube_video(source, meta.video_id, quality=config.video_quality, progress_cb=_cb)
        else:
            local_p = Path(source).expanduser().resolve()
            if not local_p.exists():
                console.print(f"[red]Error:[/red] File not found: {local_p}")
                raise typer.Exit(code=1)
            meta = inspect_local_video(local_p)
            video_path = local_p

        scan = scan_video(video_path, meta, config, progress_cb=_cb)
        decisions, stats = segment_candidates(scan, config)
        job_work = output_dir / sanitize_filename(meta.title)
        slides = build_slides_from_decisions(
            scan, decisions, config, job_work, include_rejected_thumbs=False, progress_cb=_cb
        )
        summary = enrich_slides(slides, transcript, config, lecture_title=meta.title, progress_cb=_cb)
        progress.update(task_id, completed=100, description="Exporting documents...")

        req = ExportRequest(pdf_layout=pdf_layout)
        stem = sanitize_filename(meta.title)
        exported_paths: list[Path] = []
        for fmt in selected_formats:
            if fmt == ExportFormat.PDF:
                exported_paths.append(export_pdf(output_dir / f"{stem}_notes.pdf", meta, slides, req, summary))
            elif fmt == ExportFormat.DOCX:
                exported_paths.append(export_docx(output_dir / f"{stem}_notes.docx", meta, slides, req, summary))
            elif fmt == ExportFormat.MARKDOWN_ZIP:
                exported_paths.append(
                    export_markdown_zip(output_dir / f"{stem}_markdown_notes.zip", meta, slides, req, summary)
                )
            elif fmt == ExportFormat.IMAGES_ZIP:
                exported_paths.append(export_images_zip(output_dir / f"{stem}_slides.zip", slides))

        if config.cleanup_video and not meta.is_local_file and video_path.exists():
            try:
                video_path.unlink()
            except OSError:
                pass

    elapsed = time.perf_counter() - t0
    tbl = Table(title=f"LectureLens Summary — {meta.title}", show_header=False, border_style="cyan")
    tbl.add_row("Duration", format_timestamp(meta.duration))
    tbl.add_row("Frames Scanned", str(stats.frames_scanned))
    tbl.add_row("Slides Kept", f"[bold green]{stats.slides_kept}[/bold green]")
    tbl.add_row("Duplicates Filtered", str(stats.duplicates_filtered))
    tbl.add_row("Progressive Steps Collapsed", str(stats.progressive_merged))
    tbl.add_row("Webcam Overlay Masked", "Yes" if stats.webcam_masked else "No")
    tbl.add_row("Elapsed Time", f"{elapsed:.2f}s")
    for p in exported_paths:
        tbl.add_row("Exported File", str(p.resolve()))
    console.print(tbl)


if __name__ == "__main__":
    app()
