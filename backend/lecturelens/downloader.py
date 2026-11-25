"""YouTube video metadata, subtitle transcript, and smart cached media downloader."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import httpx
import yt_dlp

from .models import Chapter, TranscriptSegment, VideoMetadata
from .utils import ensure_bin_paths, extract_youtube_id, get_cache_root, probe_video

ProgressCallback = Callable[[str, float, str], None]


def _pick_subtitle_track(info: dict) -> tuple[str, str] | None:
    """Select best available json3 subtitle URL and language code from yt-dlp info."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    preferred_langs = ["en", "en-US", "en-GB", "en-IN", "en-orig"]

    for source in (manual, auto):
        for lang in preferred_langs:
            tracks = source.get(lang)
            if tracks:
                for tr in tracks:
                    if tr.get("ext") == "json3" and tr.get("url"):
                        return lang, tr["url"]
        for lang, tracks in source.items():
            if tracks:
                for tr in tracks:
                    if tr.get("ext") == "json3" and tr.get("url"):
                        return lang, tr["url"]
    return None


def _parse_json3_transcript(raw_json: str) -> list[TranscriptSegment]:
    """Parse YouTube json3 caption payload into clean timestamped text segments."""
    data = json.loads(raw_json)
    segments: list[TranscriptSegment] = []
    for ev in data.get("events") or []:
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        text = re.sub(r"\s+", " ", text)
        if not text or text in {"[Music]", "[Applause]", "[Laughter]"}:
            continue
        start = float(ev.get("tStartMs", 0)) / 1000.0
        dur = float(ev.get("dDurationMs", 2000)) / 1000.0
        end = start + max(0.5, dur)
        # Deduplicate overlapping auto-caption rolling echoes
        if segments and text == segments[-1].text:
            segments[-1].end = max(segments[-1].end, end)
            continue
        segments.append(TranscriptSegment(start=round(start, 2), end=round(end, 2), text=text))
    return segments


def inspect_youtube(url: str, fetch_transcript: bool = True) -> tuple[VideoMetadata, list[TranscriptSegment]]:
    """Fetch YouTube video metadata, chapters, and caption transcript without downloading media."""
    ensure_bin_paths()
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Unable to retrieve metadata for this YouTube URL.")

    vid = str(info.get("id") or extract_youtube_id(url) or "video")
    duration = float(info.get("duration") or 0.0)
    chapters = [
        Chapter(
            title=str(ch.get("title") or f"Section {i + 1}"),
            start_time=float(ch.get("start_time") or 0.0),
            end_time=float(ch.get("end_time") or duration),
        )
        for i, ch in enumerate(info.get("chapters") or [])
    ]

    transcript: list[TranscriptSegment] = []
    lang = ""
    sub_pick = _pick_subtitle_track(info)
    if sub_pick:
        lang = sub_pick[0]
        if fetch_transcript:
            try:
                resp = httpx.get(sub_pick[1], timeout=8.0, follow_redirects=True)
                if resp.status_code == 200:
                    transcript = _parse_json3_transcript(resp.text)
            except Exception:
                transcript = []

    thumbs = info.get("thumbnails") or []
    thumb_url = str(info.get("thumbnail") or (thumbs[-1].get("url") if thumbs else ""))

    meta = VideoMetadata(
        video_id=vid,
        source_url=str(info.get("webpage_url") or url),
        title=str(info.get("title") or "YouTube Lecture"),
        channel=str(info.get("channel") or info.get("uploader") or "Unknown Channel"),
        duration=duration,
        thumbnail_url=thumb_url,
        chapters=chapters,
        has_transcript=bool(sub_pick),
        transcript_language=lang,
        is_local_file=False,
    )
    return meta, transcript


def download_youtube_video(
    url: str,
    video_id: str,
    quality: str = "1080p",
    progress_cb: ProgressCallback | None = None,
) -> Path:
    """Download video-only stream (or fallback) into local cache for fast slide analysis."""
    ensure_bin_paths()
    videos_dir = get_cache_root() / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)

    # Check cache first
    for ext in ("mp4", "webm", "mkv"):
        cached = videos_dir / f"{video_id}_{quality}.{ext}"
        if cached.exists() and cached.stat().st_size > 50_000:
            if progress_cb:
                progress_cb("downloading", 0.15, f"Using cached {quality} video...")
            return cached

    if quality == "720p":
        fmt = "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]/best[height<=720]"
    elif quality == "best":
        fmt = "bestvideo[ext=mp4]/bestvideo/best"
    else:
        fmt = "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]/best[height<=1080]"

    out_tmpl = str(videos_dir / f"{video_id}_{quality}.%(ext)s")

    def _hook(d: dict) -> None:
        if not progress_cb:
            return
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            frac = min(1.0, downloaded / total) if total > 0 else 0.0
            progress_cb(
                "downloading",
                0.02 + 0.18 * frac,
                f"Downloading {quality} lecture stream ({frac * 100:.0f}%)...",
            )
        elif status == "finished":
            progress_cb("downloading", 0.20, "Video download complete, preparing visual scan...")

    ydl_opts = {
        "format": fmt,
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "progress_hooks": [_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_path = Path(ydl.prepare_filename(info))
        if downloaded_path.exists():
            return downloaded_path

    # Locate matching cached file if extension changed
    matches = sorted(videos_dir.glob(f"{video_id}_{quality}.*"))
    if matches:
        return matches[0]
    raise RuntimeError("Video download succeeded but output file could not be located.")


def inspect_local_video(video_path: Path, title: str | None = None) -> VideoMetadata:
    """Build VideoMetadata for a local video file."""
    info = probe_video(video_path)
    return VideoMetadata(
        video_id=video_path.stem,
        source_url=str(video_path),
        title=title or video_path.stem.replace("_", " ").title(),
        channel="Local Video",
        duration=float(info["duration"]),
        thumbnail_url="",
        chapters=[],
        has_transcript=False,
        transcript_language="",
        is_local_file=True,
    )
