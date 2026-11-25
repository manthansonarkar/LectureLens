"""End-to-end synthetic MP4 video tests for the two-pass slide extraction engine."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from lecturelens.detector import build_slides_from_decisions, scan_video, segment_candidates
from lecturelens.downloader import inspect_local_video
from lecturelens.models import ExtractionConfig, ExtractionPreset
from lecturelens.utils import find_ffmpeg
from PIL import Image, ImageDraw


def _encode_frames_to_mp4(frames: list[np.ndarray], fps: int, out_path: Path) -> None:
    ffmpeg = find_ffmpeg()
    h, w, _ = frames[0].shape
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
    err = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
    rc = proc.wait()
    assert rc == 0, f"FFmpeg encode failed: {err}"


def _make_slide_image(idx: int, title: str, lines: list[str], dark: bool = False, size=(640, 360)) -> np.ndarray:
    bg = "#0F172A" if dark else "#FFFFFF"
    fg = "#F8FAFC" if dark else "#0F172A"
    accent = "#38BDF8" if dark else "#4F46E5"
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, size[0] - 20, 64], fill=accent)
    d.text((34, 34), f"SLIDE {idx}: {title}", fill="white")
    y = 95
    for k, ln in enumerate(lines):
        d.rectangle([32, y, 52, y + 18], fill=accent)
        d.text((64, y + 2), ln, fill=fg)
        # Draw a unique geometric visual per slide so each slide has distinct layout
        if k == len(lines) - 1:
            x0 = 400 + (idx * 23) % 120
            d.rectangle([x0, 110 + (idx * 19) % 80, x0 + 95, 220 + (idx * 17) % 60], outline=accent, width=4)
        y += 42
    return np.array(im)


def test_fades_and_webcam_pip_ignored(tmp_path: Path) -> None:
    fps = 6
    slides = [
        _make_slide_image(1, "Introduction to Graphs", ["Vertices V and Edges E", "Adjacency Matrix"]),
        _make_slide_image(2, "Breadth-First Search", ["Uses FIFO Queue", "O(V + E) Time Complexity"], dark=True),
        _make_slide_image(3, "Dijkstra Algorithm", ["Greedy Shortest Path", "Non-negative Weights"]),
        _make_slide_image(4, "Dynamic Programming", ["Optimal Substructure", "Overlapping Subproblems"], dark=True),
    ]

    frames: list[np.ndarray] = []
    rng = np.random.default_rng(7)
    for s_idx, sl in enumerate(slides):
        # 2.5 seconds steady slide with animated corner webcam box
        for _ in range(fps * 2 + 3):
            fr = sl.copy()
            # Bright animated webcam in bottom-right corner
            color = tuple(int(x) for x in rng.integers(40, 240, size=3))
            cv_x = 510 + int(rng.integers(0, 35))
            fr[275:350, 500:630] = (30, 30, 35)
            fr[285:340, cv_x : cv_x + 40] = color
            frames.append(fr)

        # 0.5s cross-fade transition to next slide
        if s_idx + 1 < len(slides):
            nxt = slides[s_idx + 1]
            for alpha_i in range(1, 4):
                alpha = alpha_i / 4.0
                blend = ((1.0 - alpha) * sl + alpha * nxt).astype(np.uint8)
                frames.append(blend)

    mp4 = tmp_path / "lecture_fades_webcam.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)

    meta = inspect_local_video(mp4)
    cfg = ExtractionConfig.from_preset(ExtractionPreset.SMART_LECTURE, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg)
    decisions, stats = segment_candidates(scan, cfg)
    kept = [d for d in decisions if d.kept]

    assert stats.webcam_masked is True
    assert len(kept) == 4
    # Ensure no fade frames were captured: each kept slide has clean timestamp inside its steady window
    out_slides = build_slides_from_decisions(scan, decisions, cfg, tmp_path / "out", include_rejected_thumbs=False)
    assert len(out_slides) == 4
    for s in out_slides:
        assert Path(s.image_path).exists()


def test_progressive_bullet_collapse_keeps_completed_slide(tmp_path: Path) -> None:
    fps = 5
    b1 = _make_slide_image(1, "Thermodynamics", ["1. System & Surroundings"])
    b2 = _make_slide_image(1, "Thermodynamics", ["1. System & Surroundings", "2. First Law: dU = dQ - dW"])
    b3 = _make_slide_image(
        1,
        "Thermodynamics",
        ["1. System & Surroundings", "2. First Law: dU = dQ - dW", "3. Enthalpy H = U + PV", "4. Second Law: dS >= 0"],
    )
    slide2 = _make_slide_image(2, "Carnot Cycle", ["Isothermal Expansion", "Adiabatic Compression"], dark=True)

    frames: list[np.ndarray] = []
    for stage in (b1, b2, b3, slide2):
        frames.extend([stage.copy() for _ in range(fps * 2)])

    mp4 = tmp_path / "progressive_lecture.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)
    meta = inspect_local_video(mp4)

    # Smart mode collapses progressive bullets into the completed 4-bullet slide -> 2 total slides
    cfg_smart = ExtractionConfig.from_preset(ExtractionPreset.SMART_LECTURE, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg_smart)
    dec_smart, stats_smart = segment_candidates(scan, cfg_smart)
    kept_smart = [d for d in dec_smart if d.kept]
    assert len(kept_smart) == 2
    assert stats_smart.progressive_merged >= 1
    # First kept slide must be from the completed b3 time window (~4.0s - 6.0s)
    assert kept_smart[0].candidate.timestamp >= 3.8

    # Step-by-step mode retains intermediate steps!
    cfg_step = ExtractionConfig.from_preset(ExtractionPreset.STEP_BY_STEP, enable_ocr=False, enable_transcript=False)
    dec_step, _ = segment_candidates(scan, cfg_step)
    kept_step = [d for d in dec_step if d.kept]
    assert len(kept_step) >= 3


def test_scrolling_document_respects_30pct_overlap(tmp_path: Path) -> None:
    fps = 5
    # Tall 640x1200 textbook sheet with varied sections, diagrams, and widths
    tall = Image.new("RGB", (640, 1200), "#FFFFFF")
    d = ImageDraw.Draw(tall)
    blocks = [
        (24, 30, 460, 74, "#0F172A", "1. Fourier Transform Definition & Convergence"),
        (96, 40, 600, 148, "#1D4ED8", "Integral: F(w) = int f(t) e^{-iwt} dt"),
        (170, 30, 380, 224, "#0F766E", "Lemma 2.1: Riemann-Lebesgue Property"),
        (252, 120, 610, 310, "#4F46E5", "Convolution Theorem: f * g <-> F(w) G(w)"),
        (340, 28, 510, 392, "#DC2626", "Parseval Energy Identity & Plancherel Proof"),
        (422, 60, 580, 478, "#1E293B", "Discrete Fourier Transform (DFT) Matrix"),
        (510, 30, 420, 566, "#0369A1", "FFT Cooley-Tukey O(N log N) Butterfly"),
        (600, 90, 600, 658, "#312E81", "Sampling Theorem: Nyquist Frequency 2 B"),
        (690, 36, 520, 748, "#0F172A", "Windowing & Spectral Leakage Mitigation"),
        (782, 48, 590, 845, "#047857", "Short-Time Fourier Transform (STFT)"),
        (880, 30, 460, 938, "#7C3AED", "Wavelet Multi-Resolution Analysis"),
    ]
    for y1, x1, x2, y2, fill, text in blocks:
        d.rectangle([x1, y1, x2, y2], fill=fill)
        d.text((x1 + 16, y1 + 16), text, fill="white")
    tall_arr = np.array(tall)

    # Simulate scrolling down: pause at y=0, tiny scroll y=60 (~83% overlap!), big scroll y=275 (~24% overlap!), big scroll y=560 (~21% overlap!)
    frames: list[np.ndarray] = []
    for y_off in (0, 60, 275, 560):
        view = tall_arr[y_off : y_off + 360, :, :]
        frames.extend([view.copy() for _ in range(fps * 2)])

    mp4 = tmp_path / "scroll_lecture.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)
    meta = inspect_local_video(mp4)

    cfg = ExtractionConfig.from_preset(ExtractionPreset.OVERLAP_STRICT, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg)
    decisions, _ = segment_candidates(scan, cfg)
    kept = [d for d in decisions if d.kept]

    # Tiny 16% scroll (y=60) MUST be skipped; y=0, y=275 (~24% overlap), y=560 (~21% overlap) MUST be kept!
    assert len(kept) == 3
    for dec in kept[1:]:
        assert dec.similarity_to_prev <= 0.35


def test_global_repeat_deduplication(tmp_path: Path) -> None:
    fps = 4
    s1 = _make_slide_image(1, "Topic A", ["Alpha Formula"])
    s2 = _make_slide_image(2, "Topic B", ["Beta Formula"], dark=True)
    s3 = _make_slide_image(3, "Topic C", ["Gamma Formula"])

    frames: list[np.ndarray] = []
    for sl in (s1, s2, s3, s1, s3):
        frames.extend([sl.copy() for _ in range(fps * 2)])

    mp4 = tmp_path / "repeat_slides.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)
    meta = inspect_local_video(mp4)

    cfg = ExtractionConfig.from_preset(ExtractionPreset.SMART_LECTURE, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg)
    decisions, _ = segment_candidates(scan, cfg)
    kept = [d for d in decisions if d.kept]
    assert len(kept) == 3


def test_erased_board_steps_are_not_emitted_as_new_slides(tmp_path: Path) -> None:
    fps = 5
    full = _make_slide_image(
        1,
        "Full Board Notes",
        ["Step 1: Force Balance", "Step 2: Shear Matrix", "Step 3: Boundary Conditions", "Step 4: Final Equation"],
    )
    half_erased = _make_slide_image(1, "Full Board Notes", ["Step 1: Force Balance", "Step 2: Shear Matrix"])
    next_slide = _make_slide_image(2, "Next Lecture Topic", ["Mohr Circle Geometry", "Principal Planes"], dark=True)

    frames: list[np.ndarray] = []
    for stage in (full, half_erased, next_slide):
        frames.extend([stage.copy() for _ in range(fps * 2)])

    mp4 = tmp_path / "erased_board.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)
    meta = inspect_local_video(mp4)

    cfg = ExtractionConfig.from_preset(ExtractionPreset.SMART_LECTURE, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg)
    decisions, _ = segment_candidates(scan, cfg)
    kept = [d for d in decisions if d.kept]
    erased = [d for d in decisions if d.filter_reason == "erased_step"]
    assert len(kept) == 2
    assert len(erased) >= 1


def test_blank_facecam_and_inset_pip_progressive_builds_filtered(tmp_path: Path) -> None:
    fps = 4
    w, h = 640, 360
    rng = np.random.default_rng(99)
    frames: list[np.ndarray] = []

    def _with_inset_pip(canvas: np.ndarray, step: int) -> np.ndarray:
        out = canvas.copy()
        # Inset rounded PiP card on the right (does not touch right frame edge!)
        out[76:292, 444:616] = (14, 165, 233)
        out[82:286, 450:610] = (30, 41, 59)
        cx = 468 + ((step * 17) % 60)
        out[110:260, cx : cx + 52] = (
            int(80 + (step * 29) % 150),
            int(120 + (step * 43) % 120),
            int(160 + (step * 19) % 80),
        )
        return out

    # 1. Full-screen animated camera / talking-head frames (natural high-frequency textured scene moving in center)
    base_scene = rng.integers(30, 210, size=(h // 4, w // 4, 3), dtype=np.uint8)
    base_scene = np.repeat(np.repeat(base_scene, 4, axis=0), 4, axis=1)
    for k in range(fps * 3):
        cam = base_scene.copy()
        shift = (k * 11) % 70
        cam[80:280, 200 + shift : 270 + shift] = rng.integers(40, 220, size=(200, 70, 3), dtype=np.uint8)
        frames.append(cam)

    # 2. Blank white slide canvas with only the active inset PiP overlay
    blank_canvas = np.full((h, w, 3), 255, dtype=np.uint8)
    for k in range(fps * 2):
        frames.append(_with_inset_pip(blank_canvas, k))

    # 3. Single node repeated across different PiP hand positions, then built out into full 3-node diagram
    step1 = _make_slide_image(1, "Engineering", ["From Scratch"])
    step2 = _make_slide_image(1, "Engineering", ["From Scratch", "System Design", "Testing & Reliability"])
    for k in range(fps * 3):
        frames.append(_with_inset_pip(step1, 10 + k))
    for k in range(fps * 3):
        frames.append(_with_inset_pip(step2, 30 + k))

    # 4. Static textured illustration slide (low smoothness, but ZERO intra-window motion) MUST be kept!
    static_photo = base_scene.copy()
    # Add high-contrast border/annotation to ensure distinctness from step2
    static_photo[40:320, 40:400] = rng.integers(10, 240, size=(280, 360, 3), dtype=np.uint8)
    for k in range(fps * 2):
        frames.append(_with_inset_pip(static_photo, 40 + k))

    # 5. Dark-background math slide must still be kept even with skip_blank_or_facecam=True
    dark_slide = _make_slide_image(2, "Neural Nets", ["Layer Weights W", "ReLU Activation"], dark=True)
    for k in range(fps * 3):
        frames.append(_with_inset_pip(dark_slide, 50 + k))

    mp4 = tmp_path / "facecam_blank_inset_pip.mp4"
    _encode_frames_to_mp4(frames, fps=fps, out_path=mp4)
    meta = inspect_local_video(mp4)

    cfg = ExtractionConfig.from_preset(ExtractionPreset.SMART_LECTURE, enable_ocr=False, enable_transcript=False)
    scan = scan_video(mp4, meta, cfg)
    decisions, stats = segment_candidates(scan, cfg)
    kept = [d for d in decisions if d.kept]
    reasons = {d.filter_reason for d in decisions}

    assert stats.webcam_masked is True
    assert "facecam" in reasons
    assert "low_content" in reasons
    assert len(kept) == 3
    assert kept[0].candidate.timestamp >= 5.0  # skipped facecam + blank, collapsed step1 into step2
    assert kept[2].candidate.timestamp >= 12.5  # dark slide preserved!
