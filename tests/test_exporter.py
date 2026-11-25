"""Tests for PDF, DOCX, Markdown ZIP, and Images ZIP exporters."""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document
from lecturelens.exporter import export_docx, export_images_zip, export_markdown_zip, export_pdf
from lecturelens.models import ExportRequest, PdfLayout, SlideItem, VideoMetadata
from PIL import Image, ImageDraw


def _sample_data(tmp_path: Path) -> tuple[VideoMetadata, list[SlideItem]]:
    slides: list[SlideItem] = []
    for i in range(1, 5):
        img_p = tmp_path / f"slide_{i}.png"
        im = Image.new("RGB", (1280, 720), "#F8FAFC")
        d = ImageDraw.Draw(im)
        d.rectangle([40, 40, 1240, 120], fill="#4F46E5")
        d.text((60, 70), f"Slide {i}: Algorithms & Proofs", fill="white")
        im.save(img_p)

        slides.append(
            SlideItem(
                id=f"s{i}",
                index=i,
                timestamp=float(i * 45),
                start_time=float(i * 45),
                end_time=float(i * 45 + 38),
                timestamp_label=f"0{i}:00",
                youtube_jump_url=f"https://www.youtube.com/watch?v=demo123&t={i * 45}s",
                chapter_title=f"Chapter {i}",
                image_path=str(img_p),
                thumb_path=str(img_p),
                width=1280,
                height=720,
                ocr_text=f"Theorem {i}: x < y & dS >= dQ/T",
                transcript_text=f"Here we derive theorem {i} carefully.",
                user_notes=f"Important for exam #{i}" if i == 1 else "",
                kept=True,
            )
        )

    meta = VideoMetadata(
        video_id="demo123",
        source_url="https://www.youtube.com/watch?v=demo123",
        title="MIT 6.006 Lecture 1: Algorithmic Thinking",
        channel="MIT OpenCourseWare",
        duration=240.0,
    )
    return meta, slides


def test_pdf_all_layouts(tmp_path: Path) -> None:
    meta, slides = _sample_data(tmp_path)
    for layout in PdfLayout:
        out = tmp_path / f"notes_{layout.value}.pdf"
        req = ExportRequest(pdf_layout=layout, include_ocr=True, include_transcript=True)
        export_pdf(out, meta, slides, req, lecture_summary="• Core asymptotic bounds.\n• Peak finding algorithms.")
        assert out.exists()
        raw = out.read_bytes()
        assert raw.startswith(b"%PDF-")
        assert len(raw) > 5000


def test_docx_export_valid_and_contains_images_and_text(tmp_path: Path) -> None:
    meta, slides = _sample_data(tmp_path)
    out = tmp_path / "notes.docx"
    req = ExportRequest(include_ocr=True, include_transcript=True)
    export_docx(out, meta, slides, req, lecture_summary="Summary of lecture.")
    assert out.exists()

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "MIT 6.006 Lecture 1" in full_text
    assert "Theorem 1" in full_text
    assert "Here we derive theorem 1 carefully." in full_text
    # Verify 4 embedded slide images
    assert len(doc.inline_shapes) == 4


def test_markdown_and_images_zips(tmp_path: Path) -> None:
    meta, slides = _sample_data(tmp_path)
    md_zip = tmp_path / "md.zip"
    export_markdown_zip(md_zip, meta, slides, ExportRequest())
    with zipfile.ZipFile(md_zip, "r") as zf:
        names = zf.namelist()
        assert "notes.md" in names
        assert any(n.endswith(".png") for n in names)
        md_content = zf.read("notes.md").decode("utf-8")
        assert "MIT 6.006 Lecture 1" in md_content

    img_zip = tmp_path / "imgs.zip"
    export_images_zip(img_zip, slides)
    with zipfile.ZipFile(img_zip, "r") as zf:
        assert len(zf.namelist()) == 4
