"""OCR text extraction, transcript alignment, and optional AI note synthesis."""

from __future__ import annotations

import base64
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import httpx

from .models import ExtractionConfig, SlideItem, TranscriptSegment

_OCR_LOCK = threading.Lock()
_OCR_INSTANCE: Any = None
_OCR_CHECKED = False


def get_ocr_engine() -> Any | None:
    """Lazily initialize RapidOCR singleton in a thread-safe manner."""
    global _OCR_INSTANCE, _OCR_CHECKED
    with _OCR_LOCK:
        if _OCR_CHECKED:
            return _OCR_INSTANCE
        _OCR_CHECKED = True
        try:
            from rapidocr_onnxruntime import RapidOCR

            _OCR_INSTANCE = RapidOCR()
        except Exception:
            _OCR_INSTANCE = None
        return _OCR_INSTANCE


def ocr_available() -> bool:
    """Return True if RapidOCR is importable and ready."""
    return get_ocr_engine() is not None


def extract_text_from_image(image_path: str | Path) -> str:
    """Run OCR on a slide image and reconstruct reading-order text lines."""
    engine = get_ocr_engine()
    if engine is None:
        return ""
    path = Path(image_path)
    if not path.exists():
        return ""

    img = cv2.imread(str(path))
    if img is None:
        return ""

    with _OCR_LOCK:
        result, _ = engine(img)

    if not result:
        return ""

    items: list[tuple[float, float, float, str]] = []
    for entry in result:
        box, text, conf_raw = entry[0], str(entry[1]).strip(), entry[2]
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            conf = 1.0
        if not text or conf < 0.42:
            continue
        ys = [pt[1] for pt in box]
        xs = [pt[0] for pt in box]
        y_center = sum(ys) / len(ys)
        y_height = max(8.0, max(ys) - min(ys))
        x_left = min(xs)
        items.append((y_center, x_left, y_height, text))

    if not items:
        return ""

    items.sort(key=lambda t: (t[0], t[1]))
    lines: list[list[tuple[float, float, float, str]]] = []
    for item in items:
        if not lines:
            lines.append([item])
            continue
        prev_y = sum(x[0] for x in lines[-1]) / len(lines[-1])
        tol = max(12.0, item[2] * 0.55)
        if abs(item[0] - prev_y) <= tol:
            lines[-1].append(item)
        else:
            lines.append([item])

    formatted_lines: list[str] = []
    for line in lines:
        line.sort(key=lambda t: t[1])
        formatted_lines.append("  ".join(t[3] for t in line))
    return "\n".join(formatted_lines)


def align_transcript_to_slides(
    slides: list[SlideItem],
    transcript: list[TranscriptSegment],
) -> None:
    """Assign spoken YouTube transcript segments to the matching slide time windows."""
    if not slides or not transcript:
        return

    kept_slides = sorted((s for s in slides if s.kept), key=lambda s: s.timestamp)
    if not kept_slides:
        return

    # Build contiguous non-overlapping ownership windows between consecutive kept slides
    windows: list[tuple[float, float, SlideItem]] = []
    for i, sl in enumerate(kept_slides):
        win_start = 0.0 if i == 0 else kept_slides[i - 1].end_time
        if i == 0:
            win_start = min(sl.start_time, 0.0)
        else:
            prev_mid = 0.5 * (kept_slides[i - 1].timestamp + sl.timestamp)
            win_start = max(kept_slides[i - 1].timestamp, min(sl.start_time, prev_mid))
        if i + 1 < len(kept_slides):
            next_sl = kept_slides[i + 1]
            next_mid = 0.5 * (sl.timestamp + next_sl.timestamp)
            win_end = max(sl.end_time, next_mid)
        else:
            win_end = float("inf")
        windows.append((win_start, win_end, sl))

    buckets: dict[str, list[str]] = {sl.id: [] for sl in kept_slides}
    for seg in transcript:
        mid = 0.5 * (seg.start + seg.end)
        placed = False
        for w_start, w_end, sl in windows:
            if w_start <= mid < w_end:
                buckets[sl.id].append(seg.text)
                placed = True
                break
        if not placed and windows:
            buckets[windows[-1][2].id].append(seg.text)

    for sl in kept_slides:
        words_joined = " ".join(buckets.get(sl.id, [])).strip()
        sl.transcript_text = words_joined


def list_ollama_models(timeout: float = 1.5) -> list[str]:
    """Return available local Ollama model tags if Ollama server is reachable."""
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=timeout)
        if resp.status_code == 200:
            models = resp.json().get("models") or []
            return [str(m.get("name")) for m in models if m.get("name")]
    except Exception:
        pass
    return []


def _call_llm(provider: str, model: str, api_key: str, prompt: str) -> str:
    """Call configured local Ollama or cloud OpenAI/Gemini provider."""
    if provider == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        model_name = model or (list_ollama_models() or ["gemma3:4b"])[0]
        resp = httpx.post(
            f"{host}/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=45.0,
        )
        resp.raise_for_status()
        return str(resp.json().get("response") or "").strip()

    if provider == "openai":
        if not api_key:
            return ""
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"]).strip()

    if provider == "gemini":
        if not api_key:
            return ""
        model_name = model or "gemini-2.5-flash"
        resp = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30.0,
        )
        resp.raise_for_status()
        cands = resp.json().get("candidates") or []
        if cands:
            parts = (cands[0].get("content") or {}).get("parts") or []
            return "".join(str(p.get("text") or "") for p in parts).strip()

    return ""


def pick_ollama_vision_model(preferred: str = "") -> str | None:
    """Return an installed local Ollama vision-capable model tag, or None."""
    if preferred.strip():
        return preferred.strip()
    installed = list_ollama_models()
    vision_hints = ("gemma3", "vision", "vl", "llava", "minicpm-v", "moondream")
    for name in installed:
        low = name.lower()
        if any(h in low for h in vision_hints):
            return name
    return None


def filter_slides_with_ollama_vision(
    slides: list[SlideItem],
    model: str = "",
    progress_cb: Callable[[str, float, str], None] | None = None,
) -> int:
    """Use an offline local Ollama vision model to flag non-note/facecam/blank slides."""
    chosen = pick_ollama_vision_model(model)
    if not chosen:
        return 0
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    kept = [s for s in slides if s.kept]
    filtered_count = 0

    prompt = (
        "Evaluate this lecture video frame for student PDF notes. "
        'Reply ONLY in JSON: {"useful": true/false, "reason": "short 5 word reason"}. '
        "Mark useful=false ONLY if it is just a speaker facecam without slides/notes, "
        "a blank/loading/intro logo screen, or heavily blocked by a hand."
    )

    for i, sl in enumerate(kept):
        img_file = Path(sl.thumb_path or sl.image_path)
        if not img_file.exists():
            continue
        try:
            b64 = base64.b64encode(img_file.read_bytes()).decode("ascii")
            resp = httpx.post(
                f"{host}/api/generate",
                json={
                    "model": chosen,
                    "prompt": prompt,
                    "images": [b64],
                    "stream": False,
                    "format": "json",
                },
                timeout=30.0,
            )
            if resp.status_code == 200:
                raw_txt = str(resp.json().get("response") or "{}")
                parsed = json.loads(raw_txt)
                if parsed.get("useful") is False:
                    sl.kept = False
                    sl.filter_reason = "ai_filtered"
                    reason = str(parsed.get("reason") or "").strip()
                    if reason and not sl.ai_summary:
                        sl.ai_summary = f"Filtered by {chosen}: {reason}"
                    filtered_count += 1
        except Exception:
            continue

        if progress_cb:
            frac = (i + 1) / max(1, len(kept))
            progress_cb(
                "enriching",
                0.85 + 0.05 * frac,
                f"Offline Ollama Vision check ({chosen}: {i + 1}/{len(kept)})...",
            )

    if filtered_count > 0:
        idx = 1
        for sl in slides:
            if sl.kept:
                sl.index = idx
                idx += 1
            else:
                sl.index = 0
    return filtered_count


def enrich_slides(
    slides: list[SlideItem],
    transcript: list[TranscriptSegment],
    config: ExtractionConfig,
    lecture_title: str = "",
    progress_cb: Callable[[str, float, str], None] | None = None,
) -> str:
    """Populate OCR text, aligned spoken transcript, and optional AI summaries on kept slides."""
    if config.ollama_vision_filter:
        filter_slides_with_ollama_vision(slides, model=config.vision_model, progress_cb=progress_cb)

    kept = [s for s in slides if s.kept]
    if not kept:
        return ""

    if config.enable_transcript and transcript:
        align_transcript_to_slides(slides, transcript)

    if config.enable_ocr and ocr_available():
        for i, sl in enumerate(kept):
            if not sl.ocr_text and sl.image_path:
                sl.ocr_text = extract_text_from_image(sl.image_path)
            if progress_cb:
                frac = (i + 1) / len(kept)
                progress_cb("enriching", 0.88 + 0.09 * frac, f"Running OCR & note alignment ({i + 1}/{len(kept)})...")

    lecture_summary = ""
    if config.ai_notes_provider != "off":
        if progress_cb:
            progress_cb("enriching", 0.97, f"Synthesizing AI study notes via {config.ai_notes_provider}...")
        for sl in kept:
            if sl.ai_summary or (not sl.ocr_text and not sl.transcript_text):
                continue
            prompt = (
                "Summarize this lecture slide into 2-3 concise, crisp study bullet points (no preamble).\n"
                f"Slide Text (OCR): {sl.ocr_text[:1200]}\n"
                f"Lecturer Spoken Words: {sl.transcript_text[:1200]}"
            )
            try:
                sl.ai_summary = _call_llm(config.ai_notes_provider, config.ai_model, config.ai_api_key, prompt)
            except Exception:
                pass

        combined_context = "\n".join(
            f"[{s.timestamp_label}] {s.ocr_text[:200]} | {s.transcript_text[:220]}"
            for s in kept[:25]
        )
        if combined_context.strip():
            try:
                lecture_summary = _call_llm(
                    config.ai_notes_provider,
                    config.ai_model,
                    config.ai_api_key,
                    f"Create a concise 4-bullet executive study overview for the lecture '{lecture_title}'.\n\n{combined_context}",
                )
            except Exception:
                lecture_summary = ""

    return lecture_summary
