"""Integration tests for FastAPI backend endpoints."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from lecturelens.server import create_app
from lecturelens.utils import find_ffmpeg
from PIL import Image, ImageDraw


def _create_sample_mp4(out_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    fps = 4
    w, h = 640, 360
    frames: list[np.ndarray] = []
    for idx, title in enumerate(("Slide One", "Slide Two", "Slide Three"), start=1):
        bg = "#0F172A" if idx % 2 == 0 else "#FFFFFF"
        fg = "#F8FAFC" if idx % 2 == 0 else "#0F172A"
        accent = "#38BDF8" if idx % 2 == 0 else "#4F46E5"
        im = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(im)
        d.rectangle([20, 20, w - 20, 64], fill=accent)
        d.text((34, 34), f"SLIDE {idx}: {title}", fill="white")
        d.text((40, 110), f"Key Point {idx}.1", fill=fg)
        d.rectangle([380 + idx * 20, 120, 480 + idx * 20, 230], outline=accent, width=4)
        arr = np.array(im)
        frames.extend([arr.copy() for _ in range(fps * 2)])

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{w}x{h}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-y",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    for fr in frames:
        proc.stdin.write(fr.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0


def test_api_upload_refilter_edit_and_export(tmp_path: Path) -> None:
    mp4 = tmp_path / "api_demo.mp4"
    _create_sample_mp4(mp4)

    app = create_app()
    client = TestClient(app)

    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    assert r_health.json()["ffmpeg"] is True

    with mp4.open("rb") as f:
        r_up = client.post(
            "/api/upload",
            files={"file": ("api_demo.mp4", f, "video/mp4")},
            data={"config_json": json.dumps({"enable_ocr": True, "enable_transcript": False})},
        )
    assert r_up.status_code == 200
    job_id = r_up.json()["job_id"]

    job_data = None
    for _ in range(50):
        r_job = client.get(f"/api/jobs/{job_id}")
        assert r_job.status_code == 200
        job_data = r_job.json()
        if job_data["status"] in {"completed", "failed"}:
            break
        time.sleep(0.15)

    assert job_data is not None
    assert job_data["status"] == "completed", job_data.get("error")
    kept = [s for s in job_data["slides"] if s["kept"]]
    assert len(kept) == 3

    r_img = client.get(kept[0]["image_url"])
    assert r_img.status_code == 200
    assert len(r_img.content) > 1000

    r_refilter = client.post(
        f"/api/jobs/{job_id}/refilter",
        json={"config": {"preset": "strict_overlap", "max_similarity": 0.30, "enable_ocr": False}},
    )
    assert r_refilter.status_code == 200
    assert r_refilter.json()["stats"]["slides_kept"] == 3

    first_id = kept[0]["id"]
    r_patch = client.patch(
        f"/api/jobs/{job_id}/slides/{first_id}",
        json={"user_notes": "Review this definition!"},
    )
    assert r_patch.status_code == 200
    assert r_patch.json()["slides"][0]["user_notes"] == "Review this definition!"

    r_add = client.post(f"/api/jobs/{job_id}/add-frame", json={"timestamp": 1.0})
    assert r_add.status_code == 200
    assert r_add.json()["stats"]["slides_kept"] == 4

    r_pdf = client.post(f"/api/jobs/{job_id}/export", json={"format": "pdf", "pdf_layout": "cornell_notes"})
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")

    r_docx = client.post(f"/api/jobs/{job_id}/export", json={"format": "docx"})
    assert r_docx.status_code == 200
    assert r_docx.content[:2] == b"PK"
