"""Shared utilities for LectureLens."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


def ensure_bin_paths() -> None:
    """Ensure common Homebrew and local binary directories are on PATH."""
    extra_paths = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
    ]
    current = os.environ.get("PATH", "")
    parts = [p for p in current.split(os.pathsep) if p]
    for p in reversed(extra_paths):
        if p not in parts and Path(p).exists():
            parts.insert(0, p)
    os.environ["PATH"] = os.pathsep.join(parts)


def find_ffmpeg() -> str:
    """Return the path to the ffmpeg binary or raise a clear error."""
    ensure_bin_paths()
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError(
            "ffmpeg binary not found. Please install ffmpeg (e.g. `brew install ffmpeg` on macOS or `apt install ffmpeg` on Linux)."
        )
    return path


def find_ffprobe() -> str:
    """Return the path to the ffprobe binary or raise a clear error."""
    ensure_bin_paths()
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe binary not found. Please install ffmpeg.")
    return path


def get_cache_root() -> Path:
    """Return writable cache directory for downloaded videos and job artifacts."""
    env_dir = os.environ.get("LECTURELENS_CACHE_DIR")
    if env_dir:
        root = Path(env_dir).expanduser()
    else:
        root = Path.home() / ".cache" / "lecturelens"
    try:
        root.mkdir(parents=True, exist_ok=True)
        test_file = root / ".write_test"
        test_file.touch()
        test_file.unlink()
        return root
    except OSError:
        fallback = Path.cwd() / ".lecturelens_cache"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    total = max(0, int(round(seconds)))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def extract_youtube_id(url: str) -> str | None:
    """Extract canonical 11-char YouTube video ID from any common YouTube URL format."""
    text = url.strip()
    if not text:
        return None
    parsed = urlparse(text)
    host = parsed.netloc.lower()
    if host in {"youtu.be", "www.youtu.be"}:
        vid = parsed.path.strip("/").split("/")[0]
        return vid or None
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        qs = parse_qs(parsed.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0]
        parts = [p for p in parsed.path.split("/") if p]
        for prefix in ("live", "shorts", "embed", "v"):
            if len(parts) >= 2 and parts[0] == prefix:
                return parts[1]
    return None


def is_youtube_url(url: str) -> bool:
    """Check whether input string looks like a YouTube URL."""
    return extract_youtube_id(url) is not None or "youtube.com/" in url or "youtu.be/" in url


def build_youtube_jump_url(source_url: str, seconds: float) -> str | None:
    """Build a YouTube deep link pointing to the exact timestamp."""
    vid = extract_youtube_id(source_url)
    if not vid:
        return None
    t = max(0, int(seconds))
    parsed = urlparse(source_url)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        qs["v"] = [vid]
        qs["t"] = [f"{t}s"]
        return urlunparse(("https", "www.youtube.com", "/watch", "", urlencode(qs, doseq=True), ""))
    return f"https://www.youtube.com/watch?v={vid}&t={t}s"


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Convert arbitrary title to safe cross-platform filename stem."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned[:max_len].strip("._")) or "lecture_notes"


def probe_video(video_path: Path) -> dict[str, float | int]:
    """Read width, height, fps, and duration using ffprobe."""
    ffprobe = find_ffprobe()
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}

    width = int(stream.get("width") or 1280)
    height = int(stream.get("height") or 720)
    duration = float(stream.get("duration") or fmt.get("duration") or 0.0)

    fps = 30.0
    rate_str = str(stream.get("r_frame_rate") or "30/1")
    if "/" in rate_str:
        num, den = rate_str.split("/", 1)
        if float(den) > 0:
            fps = float(num) / float(den)
    elif rate_str:
        fps = float(rate_str)

    return {"width": width, "height": height, "fps": fps, "duration": duration}
