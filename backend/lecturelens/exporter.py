"""Publication-grade PDF, DOCX, Markdown ZIP, and Raw Images ZIP exporters."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

from .models import (
    ExportRequest,
    PdfLayout,
    SlideItem,
    VideoMetadata,
)
from .utils import format_timestamp


def _resolve_pdf_fonts() -> tuple[str, str]:
    """Register clean Unicode-capable sans fonts if available on host, else Helvetica."""
    candidates = [
        (
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]
    for regular_p, bold_p in candidates:
        if regular_p.exists() and bold_p.exists():
            try:
                if "LLSans" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("LLSans", str(regular_p)))
                    pdfmetrics.registerFont(TTFont("LLSans-Bold", str(bold_p)))
                return "LLSans", "LLSans-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"


def _safe_pdf_text(text: str, font_name: str) -> str:
    """Escape XML entities and strip characters unsupported by non-Unicode fallback fonts."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if font_name == "Helvetica":
        # Replace common Unicode math/punctuation cleanly for Helvetica WinAnsi safety
        replacements = {
            "•": "-",
            "—": "--",
            "–": "-",
            "→": "->",
            "←": "<-",
            "≥": ">=",
            "≤": "<=",
            "≠": "!=",
            "≈": "~=",
            "×": "x",
            "÷": "/",
            "↗": "->",
            "⏱": "",
        }
        for k, v in replacements.items():
            cleaned = cleaned.replace(k, v)
        cleaned = cleaned.encode("latin-1", errors="ignore").decode("latin-1")
    return escape(cleaned).replace("\n", "<br/>")


class _CornellNotesBox(Flowable):
    """Vector ruled note-taking box for Cornell / printable study PDF layout."""

    def __init__(self, width: float, height: float = 1.65 * inch, line_gap: float = 17.0) -> None:
        super().__init__()
        self.width = width
        self.height = height
        self.line_gap = line_gap

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setFillColor(colors.HexColor("#F8FAFC"))
        c.setLineWidth(0.8)
        c.roundRect(0, 0, self.width, self.height, 6, stroke=1, fill=1)

        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(colors.HexColor("#64748B"))
        c.drawString(10, self.height - 14, "STUDY NOTES & KEY TAKEAWAYS")

        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.6)
        y = self.height - 28
        while y >= 10:
            c.line(10, y, self.width - 10, y)
            y -= self.line_gap
        c.restoreState()


def _fit_image_size(img_path: Path, max_w: float, max_h: float) -> tuple[float, float]:
    """Compute aspect-ratio-preserving (w, h) fitting within (max_w, max_h)."""
    with PILImage.open(img_path) as im:
        iw, ih = im.size
    if iw <= 0 or ih <= 0:
        return max_w, max_h * 0.56
    scale = min(max_w / iw, max_h / ih)
    return iw * scale, ih * scale


def _optimized_doc_image_stream(img_path: Path, max_dim: int = 1600, quality: int = 91) -> io.BytesIO:
    """Convert raw PNG to crisp high-DPI JPEG stream to keep PDF/DOCX sizes fast & shareable."""
    buf = io.BytesIO()
    with PILImage.open(img_path) as im:
        rgb = im.convert("RGB")
        if max(rgb.size) > max_dim:
            rgb.thumbnail((max_dim, max_dim), PILImage.Resampling.LANCZOS)
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
    buf.seek(0)
    return buf


def export_pdf(
    output_path: Path,
    metadata: VideoMetadata,
    slides: list[SlideItem],
    req: ExportRequest,
    lecture_summary: str = "",
) -> Path:
    """Export kept slides into a cleanly designed PDF study document."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [s for s in slides if s.kept]
    title = req.title_override or metadata.title or "Lecture Notes"
    font_reg, font_bold = _resolve_pdf_fonts()

    page_w, page_h = A4
    margin = 0.5 * inch
    content_w = page_w - 2 * margin

    styles = getSampleStyleSheet()
    s_title = ParagraphStyle(
        "LLTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=19,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    s_sub = ParagraphStyle(
        "LLSub",
        parent=styles["Normal"],
        fontName=font_reg,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )
    s_section_hdr = ParagraphStyle(
        "LLSlideHdr",
        parent=styles["Heading3"],
        fontName=font_bold,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=4,
    )
    s_label = ParagraphStyle(
        "LLLabel",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#4F46E5"),
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )
    s_body = ParagraphStyle(
        "LLBody",
        parent=styles["Normal"],
        fontName=font_reg,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    s_mono = ParagraphStyle(
        "LLOcr",
        parent=styles["Normal"],
        fontName=font_reg,
        fontSize=8.2,
        leading=11.5,
        textColor=colors.HexColor("#475569"),
    )

    def _draw_chrome(canvas_obj, doc_obj) -> None:
        canvas_obj.saveState()
        # Top subtle accent bar & title on pages >= 2
        if doc_obj.page > 1:
            canvas_obj.setStrokeColor(colors.HexColor("#E2E8F0"))
            canvas_obj.setLineWidth(0.6)
            canvas_obj.line(margin, page_h - 0.36 * inch, page_w - margin, page_h - 0.36 * inch)
            canvas_obj.setFont(font_reg, 8)
            canvas_obj.setFillColor(colors.HexColor("#64748B"))
            short_title = (title[:72] + "...") if len(title) > 75 else title
            canvas_obj.drawString(margin, page_h - 0.30 * inch, short_title)

        # Footer
        canvas_obj.setStrokeColor(colors.HexColor("#E2E8F0"))
        canvas_obj.setLineWidth(0.6)
        canvas_obj.line(margin, 0.38 * inch, page_w - margin, 0.38 * inch)
        canvas_obj.setFont(font_reg, 8)
        canvas_obj.setFillColor(colors.HexColor("#64748B"))
        canvas_obj.drawString(margin, 0.24 * inch, "Generated with LectureLens")
        canvas_obj.drawRightString(page_w - margin, 0.24 * inch, f"Page {doc_obj.page}")
        canvas_obj.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=0.52 * inch,
        bottomMargin=0.52 * inch,
        title=title,
        author=metadata.channel,
    )

    story: list[Flowable] = []

    # Cover Header Banner
    banner_tbl = Table(
        [[Paragraph("<font color='#FFFFFF'><b>LECTURELENS STUDY NOTES</b></font>", s_sub)]],
        colWidths=[content_w],
    )
    banner_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#4F46E5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(banner_tbl)
    story.append(Spacer(1, 10))
    story.append(Paragraph(_safe_pdf_text(title, font_reg), s_title))

    source_display = (
        f'<link href="{escape(metadata.source_url)}"><font color="#4F46E5"><u>{_safe_pdf_text(metadata.source_url, font_reg)}</u></font></link>'
        if not metadata.is_local_file
        else _safe_pdf_text(metadata.source_url, font_reg)
    )
    meta_rows = [
        [
            Paragraph(f"<b>Channel / Source:</b> {_safe_pdf_text(metadata.channel, font_reg)}", s_sub),
            Paragraph(f"<b>Duration:</b> {format_timestamp(metadata.duration)}", s_sub),
        ],
        [
            Paragraph(f"<b>Slides Captured:</b> {len(kept)}", s_sub),
            Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}", s_sub),
        ],
        [Paragraph(f"<b>Video URL:</b> {source_display}", s_sub), Paragraph("", s_sub)],
    ]
    meta_tbl = Table(meta_rows, colWidths=[content_w * 0.65, content_w * 0.35])
    meta_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E2E8F0")),
                ("SPAN", (0, 2), (1, 2)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    if req.include_ai_summary and lecture_summary.strip():
        story.append(Paragraph("EXECUTIVE LECTURE SUMMARY", s_label))
        sum_tbl = Table(
            [[Paragraph(_safe_pdf_text(lecture_summary, font_reg), s_body)]],
            colWidths=[content_w],
        )
        sum_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#C7D2FE")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(sum_tbl)
        story.append(Spacer(1, 12))

    # Layout branching
    layout = req.pdf_layout
    if layout == PdfLayout.GRID_2X2:
        cell_w = (content_w - 14) / 2.0
        img_max_w = cell_w - 12
        img_max_h = 2.15 * inch
        grid_rows: list[list[Flowable]] = []
        row_cells: list[Flowable] = []

        for sl in kept:
            p = Path(sl.image_path)
            if not p.exists():
                continue
            iw, ih = _fit_image_size(p, img_max_w, img_max_h)
            jump = (
                f' - <link href="{escape(sl.youtube_jump_url)}"><font color="#4F46E5"><u>{sl.timestamp_label}</u></font></link>'
                if sl.youtube_jump_url
                else f" - {sl.timestamp_label}"
            )
            caption = Paragraph(f"<b>Slide {sl.index:02d}</b>{jump}", s_sub)
            cell_tbl = Table(
                [[RLImage(_optimized_doc_image_stream(p), width=iw, height=ih)], [caption]],
                colWidths=[cell_w],
            )
            cell_tbl.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            row_cells.append(cell_tbl)
            if len(row_cells) == 2:
                grid_rows.append(row_cells)
                row_cells = []
        if row_cells:
            row_cells.append(Spacer(cell_w, 10))
            grid_rows.append(row_cells)

        for r_idx, pair in enumerate(grid_rows):
            tbl = Table([pair], colWidths=[cell_w, cell_w])
            tbl.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story.append(tbl)
            story.append(Spacer(1, 10))
            if (r_idx + 1) % 3 == 0 and r_idx + 1 < len(grid_rows):
                story.append(PageBreak())

    elif layout == PdfLayout.HANDOUT_2X1:
        for idx_item, sl in enumerate(kept):
            p = Path(sl.image_path)
            if not p.exists():
                continue
            iw, ih = _fit_image_size(p, content_w - 14, 3.65 * inch)
            hdr_bits = [f"Slide {sl.index:02d}", sl.timestamp_label]
            if sl.chapter_title:
                hdr_bits.append(sl.chapter_title)
            hdr_text = "  |  ".join(hdr_bits)
            link_part = (
                f'  <link href="{escape(sl.youtube_jump_url)}"><font color="#4F46E5"><u>[Watch]</u></font></link>'
                if sl.youtube_jump_url
                else ""
            )
            block: list[Flowable] = [
                Paragraph(f"{_safe_pdf_text(hdr_text, font_reg)}{link_part}", s_section_hdr),
                Table(
                    [[RLImage(_optimized_doc_image_stream(p), width=iw, height=ih)]],
                    colWidths=[content_w],
                    style=TableStyle(
                        [
                            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    ),
                ),
            ]
            if req.include_ocr and sl.ocr_text.strip():
                preview_ocr = sl.ocr_text.strip()[:260]
                block.append(Spacer(1, 4))
                block.append(Paragraph(_safe_pdf_text(preview_ocr, font_reg), s_sub))
            block.append(Spacer(1, 12))
            story.append(KeepTogether(block))
            if (idx_item + 1) % 2 == 0 and idx_item + 1 < len(kept):
                story.append(PageBreak())

    else:
        # STUDY_FULL or CORNELL_NOTES
        for idx_item, sl in enumerate(kept):
            p = Path(sl.image_path)
            if not p.exists():
                continue
            has_notes = bool(
                (req.include_user_notes and sl.user_notes.strip())
                or (req.include_ai_summary and sl.ai_summary.strip())
                or (req.include_transcript and sl.transcript_text.strip())
            )
            if layout == PdfLayout.CORNELL_NOTES:
                max_img_h = 4.35 * inch
            elif not has_notes:
                max_img_h = 3.55 * inch
            else:
                max_img_h = 5.0 * inch
            iw, ih = _fit_image_size(p, content_w - 12, max_img_h)

            hdr_parts = [f"Slide {sl.index:02d}", f"{sl.timestamp_label} - {format_timestamp(sl.end_time)}"]
            if sl.chapter_title:
                hdr_parts.append(sl.chapter_title)
            hdr_line = _safe_pdf_text("  |  ".join(hdr_parts), font_reg)
            if sl.youtube_jump_url:
                hdr_line += f'   <link href="{escape(sl.youtube_jump_url)}"><font color="#4F46E5"><u>Open in YouTube</u></font></link>'

            img_frame = Table(
                [[RLImage(_optimized_doc_image_stream(p), width=iw, height=ih)]],
                colWidths=[content_w],
                style=TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#CBD5E1")),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                ),
            )
            ocr_tbl: Table | None = None
            ocr_lines_count = 0
            if req.include_ocr and sl.ocr_text.strip():
                ocr_lines = [ln for ln in sl.ocr_text.strip().splitlines() if ln.strip()]
                ocr_lines_count = len(ocr_lines)
                if len(ocr_lines) > 26:
                    ocr_lines = ocr_lines[:26] + ["..."]
                clipped_ocr = "\n".join(ocr_lines)
                if len(clipped_ocr) > 1400:
                    clipped_ocr = clipped_ocr[:1400].rstrip() + "..."
                ocr_tbl = Table(
                    [[Paragraph(_safe_pdf_text(clipped_ocr, font_reg), s_mono)]],
                    colWidths=[content_w],
                )
                ocr_tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E2E8F0")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )

            if layout != PdfLayout.CORNELL_NOTES and not has_notes and ocr_tbl is not None and ocr_lines_count <= 10:
                story.append(
                    KeepTogether(
                        [
                            Paragraph(hdr_line, s_section_hdr),
                            img_frame,
                            Spacer(1, 4),
                            Paragraph("EXTRACTED SLIDE TEXT (OCR)", s_label),
                            ocr_tbl,
                        ]
                    )
                )
            else:
                story.append(KeepTogether([Paragraph(hdr_line, s_section_hdr), img_frame, Spacer(1, 6)]))

                if layout == PdfLayout.CORNELL_NOTES:
                    story.append(_CornellNotesBox(content_w, height=1.6 * inch))
                    story.append(Spacer(1, 6))

                if req.include_user_notes and sl.user_notes.strip():
                    story.append(Paragraph("MY NOTES", s_label))
                    story.append(Paragraph(_safe_pdf_text(sl.user_notes, font_reg), s_body))

                if req.include_ai_summary and sl.ai_summary.strip():
                    story.append(Paragraph("KEY TAKEAWAYS", s_label))
                    story.append(Paragraph(_safe_pdf_text(sl.ai_summary, font_reg), s_body))

                if req.include_transcript and sl.transcript_text.strip():
                    story.append(Paragraph("LECTURER EXPLANATION", s_label))
                    clipped = sl.transcript_text.strip()
                    if len(clipped) > 1500:
                        clipped = clipped[:1500] + "..."
                    story.append(Paragraph(_safe_pdf_text(clipped, font_reg), s_body))

                if ocr_tbl is not None:
                    story.append(KeepTogether([Paragraph("EXTRACTED SLIDE TEXT (OCR)", s_label), ocr_tbl]))

            if idx_item + 1 < len(kept):
                story.append(Spacer(1, 16))
                if layout == PdfLayout.CORNELL_NOTES:
                    story.append(PageBreak())

    doc.build(story, onFirstPage=_draw_chrome, onLaterPages=_draw_chrome)
    return output_path


def _add_docx_hyperlink(paragraph, url: str, label: str, color_hex: str = "4F46E5") -> None:
    """Attach a clickable hyperlink run to a python-docx paragraph."""
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    c = OxmlElement("w:color")
    c.set(qn("w:val"), color_hex)
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "20")
    r_pr.append(c)
    r_pr.append(u)
    r_pr.append(sz)
    new_run.append(r_pr)

    t = OxmlElement("w:t")
    t.text = label
    new_run.append(t)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def _shade_docx_paragraph(paragraph, fill_hex: str) -> None:
    """Apply soft background shading to a python-docx paragraph."""
    p_pr = paragraph._p.get_or_add_pPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    p_pr.append(shd)


def export_docx(
    output_path: Path,
    metadata: VideoMetadata,
    slides: list[SlideItem],
    req: ExportRequest,
    lecture_summary: str = "",
) -> Path:
    """Export kept slides into an editable, richly formatted Microsoft Word (.docx) file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [s for s in slides if s.kept]
    title = req.title_override or metadata.title or "Lecture Notes"

    doc = Document()
    for section in doc.sections:
        section.top_margin = Inches(0.65)
        section.bottom_margin = Inches(0.65)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(10.5)

    # Title Banner
    p_brand = doc.add_paragraph()
    r_brand = p_brand.add_run("LECTURELENS  •  AUTOMATED LECTURE NOTES")
    r_brand.bold = True
    r_brand.font.size = Pt(9)
    r_brand.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)

    h1 = doc.add_heading(title, level=0)
    for run in h1.runs:
        run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Metadata block
    meta_table = doc.add_table(rows=3, cols=2)
    meta_table.style = "Table Grid"
    cells = [
        ("Channel / Source", metadata.channel),
        ("Duration", format_timestamp(metadata.duration)),
        ("Slides Captured", str(len(kept))),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    for idx_cell, (k, v) in enumerate(cells):
        row = idx_cell // 2
        col = idx_cell % 2
        p = meta_table.cell(row, col).paragraphs[0]
        rk = p.add_run(f"{k}: ")
        rk.bold = True
        rk.font.size = Pt(9.5)
        rv = p.add_run(v)
        rv.font.size = Pt(9.5)

    url_cell = meta_table.cell(2, 0).merge(meta_table.cell(2, 1))
    p_url = url_cell.paragraphs[0]
    rk = p_url.add_run("Source Video: ")
    rk.bold = True
    rk.font.size = Pt(9.5)
    if not metadata.is_local_file:
        _add_docx_hyperlink(p_url, metadata.source_url, metadata.source_url)
    else:
        p_url.add_run(metadata.source_url)

    doc.add_paragraph()

    if req.include_ai_summary and lecture_summary.strip():
        p_sum_hdr = doc.add_paragraph()
        rs = p_sum_hdr.add_run("Executive Summary")
        rs.bold = True
        rs.font.size = Pt(12)
        rs.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
        p_sum = doc.add_paragraph(lecture_summary.strip())
        _shade_docx_paragraph(p_sum, "EEF2FF")
        doc.add_paragraph()

    # Slides
    for sl in kept:
        p = Path(sl.image_path)
        if not p.exists():
            continue

        hdr_p = doc.add_paragraph()
        hdr_p.paragraph_format.keep_with_next = True
        hdr_p.paragraph_format.space_before = Pt(10)
        hdr_p.paragraph_format.space_after = Pt(4)

        r_num = hdr_p.add_run(f"Slide {sl.index:02d}  •  {sl.timestamp_label}")
        r_num.bold = True
        r_num.font.size = Pt(12)
        r_num.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

        if sl.chapter_title:
            r_ch = hdr_p.add_run(f"  |  {sl.chapter_title}")
            r_ch.font.size = Pt(10.5)
            r_ch.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

        if sl.youtube_jump_url:
            hdr_p.add_run("   ")
            _add_docx_hyperlink(hdr_p, sl.youtube_jump_url, "[Jump to Video]")

        img_p = doc.add_paragraph()
        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_p.paragraph_format.keep_with_next = True
        dw, dh = _fit_image_size(p, 6.8, 7.6)
        img_p.add_run().add_picture(_optimized_doc_image_stream(p), width=Inches(dw), height=Inches(dh))

        if req.include_user_notes and sl.user_notes.strip():
            lbl = doc.add_paragraph()
            rl = lbl.add_run("My Study Notes:")
            rl.bold = True
            rl.font.size = Pt(9.5)
            rl.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
            doc.add_paragraph(sl.user_notes.strip())

        if req.include_ai_summary and sl.ai_summary.strip():
            lbl = doc.add_paragraph()
            rl = lbl.add_run("Key Takeaways:")
            rl.bold = True
            rl.font.size = Pt(9.5)
            rl.font.color.rgb = RGBColor(0x4F, 0x46, 0xE5)
            p_ai = doc.add_paragraph(sl.ai_summary.strip())
            _shade_docx_paragraph(p_ai, "EEF2FF")

        if req.include_transcript and sl.transcript_text.strip():
            lbl = doc.add_paragraph()
            rl = lbl.add_run("Lecturer Explanation:")
            rl.bold = True
            rl.font.size = Pt(9.5)
            rl.font.color.rgb = RGBColor(0x0F, 0x76, 0x6E)
            doc.add_paragraph(sl.transcript_text.strip())

        if req.include_ocr and sl.ocr_text.strip():
            lbl = doc.add_paragraph()
            rl = lbl.add_run("Slide Text (OCR):")
            rl.bold = True
            rl.font.size = Pt(9.5)
            rl.font.color.rgb = RGBColor(0x47, 0x55, 0x69)
            p_ocr = doc.add_paragraph(sl.ocr_text.strip())
            for r in p_ocr.runs:
                r.font.size = Pt(9)
                r.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
            _shade_docx_paragraph(p_ocr, "F8FAFC")

    doc.save(str(output_path))
    return output_path


def export_markdown_zip(
    output_path: Path,
    metadata: VideoMetadata,
    slides: list[SlideItem],
    req: ExportRequest,
    lecture_summary: str = "",
) -> Path:
    """Export Notion/Obsidian-friendly Markdown + relative PNG images inside a ZIP archive."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [s for s in slides if s.kept]
    title = req.title_override or metadata.title or "Lecture Notes"

    md_lines: list[str] = [
        f"# {title}",
        "",
        f"- **Channel / Source:** {metadata.channel}",
        f"- **Duration:** {format_timestamp(metadata.duration)}",
        f"- **Slides Captured:** {len(kept)}",
        f"- **Video URL:** {metadata.source_url}",
        "",
    ]
    if req.include_ai_summary and lecture_summary.strip():
        md_lines.extend(["## Executive Summary", "", lecture_summary.strip(), ""])

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for sl in kept:
            p = Path(sl.image_path)
            if not p.exists():
                continue
            rel_img = f"slides/slide_{sl.index:02d}_{sl.timestamp_label.replace(':', '-')}.png"
            zf.write(p, arcname=rel_img)

            chap = f" — {sl.chapter_title}" if sl.chapter_title else ""
            ts_link = f"[{sl.timestamp_label}]({sl.youtube_jump_url})" if sl.youtube_jump_url else sl.timestamp_label
            md_lines.append(f"## Slide {sl.index:02d} ({ts_link}){chap}")
            md_lines.append("")
            md_lines.append(f"![Slide {sl.index:02d}]({rel_img})")
            md_lines.append("")
            if req.include_user_notes and sl.user_notes.strip():
                md_lines.extend(["**My Notes:**", "", sl.user_notes.strip(), ""])
            if req.include_ai_summary and sl.ai_summary.strip():
                md_lines.extend(["**Key Takeaways:**", "", sl.ai_summary.strip(), ""])
            if req.include_transcript and sl.transcript_text.strip():
                md_lines.extend(["**Spoken Explanation:**", "", f"> {sl.transcript_text.strip()}", ""])
            if req.include_ocr and sl.ocr_text.strip():
                md_lines.extend(["<details><summary>Slide Text (OCR)</summary>", "", "```text", sl.ocr_text.strip(), "```", "</details>", ""])

        zf.writestr("notes.md", "\n".join(md_lines).encode("utf-8"))
    return output_path


def export_images_zip(output_path: Path, slides: list[SlideItem]) -> Path:
    """Export all kept HD PNG screenshots inside a cleanly numbered ZIP archive."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    kept = [s for s in slides if s.kept]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for sl in kept:
            p = Path(sl.image_path)
            if p.exists():
                fname = f"slide_{sl.index:02d}_{sl.timestamp_label.replace(':', '-')}.png"
                zf.write(p, arcname=fname)
    output_path.write_bytes(buf.getvalue())
    return output_path
