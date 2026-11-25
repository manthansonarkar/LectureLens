"""Unit tests for background-invariant visual similarity & scroll overlap metrics."""

from __future__ import annotations

import numpy as np
from lecturelens.similarity import (
    build_eval_mask,
    check_scaled_additive_containment,
    compare_frames,
    compute_signature,
    compute_template_mask,
    detect_active_crop,
    detect_webcam_mask,
)
from PIL import Image, ImageDraw


def _draw_slide(title: str, bullets: list[str], bg: str = "white", fg: str = "black", size=(320, 180)) -> np.ndarray:
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    # Header bar
    d.rectangle([10, 8, size[0] - 10, 26], fill="#1E293B")
    d.text((16, 12), title, fill="white")
    y = 38
    for b in bullets:
        d.rectangle([18, y + 3, 24, y + 9], fill=fg)
        d.text((30, y), b, fill=fg)
        y += 22
    return np.array(im)


def test_different_slides_same_white_bg_have_low_similarity() -> None:
    # Distinct slide layouts on identical white background
    im1 = Image.new("RGB", (320, 180), "white")
    d1 = ImageDraw.Draw(im1)
    d1.rectangle([16, 12, 190, 32], fill="#1E293B")
    d1.text((22, 17), "1. Kinematics", fill="white")
    d1.text((22, 48), "v(t) = dx / dt\na(t) = dv / dt", fill="black")
    d1.ellipse([210, 50, 295, 135], outline="#2563EB", width=3)

    im2 = Image.new("RGB", (320, 180), "white")
    d2 = ImageDraw.Draw(im2)
    d2.rectangle([140, 12, 305, 32], fill="#1E293B")
    d2.text((146, 17), "2. Entropy", fill="white")
    d2.rectangle([20, 60, 130, 150], fill="#0F172A")
    d2.text((148, 72), "dS >= dQ / T\nCarnot = 1 - Tc/Th", fill="black")

    sig1 = compute_signature(np.array(im1), 1.0)
    sig2 = compute_signature(np.array(im2), 5.0)
    cmp = compare_frames(sig1, sig2)
    assert cmp.fg_iou < 0.30
    assert cmp.combined_similarity < 0.35

    # Even with identical header template across two slides, removing template keeps similarity well below duplicate threshold
    s1 = _draw_slide("Lecture 1: Kinematics", ["Velocity = dx / dt", "Acceleration = dv / dt", "Constant g = 9.81 m/s^2"])
    s2 = _draw_slide("Lecture 2: Thermodynamics", ["First Law: dU = dQ - dW", "Entropy dS >= dQ / T", "Carnot efficiency 1 - Tc/Th"])
    template = np.zeros((180, 320), dtype=bool)
    template[6:29, 8:312] = True  # Shared header bar
    cmp_tmpl = compare_frames(compute_signature(s1, 1.0), compute_signature(s2, 5.0), template_mask=template)
    assert cmp_tmpl.combined_similarity < 0.60


def test_additive_progressive_build_detected_as_retention() -> None:
    s1 = _draw_slide("Newton Laws", ["1. Law of Inertia"])
    s2 = _draw_slide(
        "Newton Laws",
        ["1. Law of Inertia", "2. F = m * a", "3. Action = -Reaction", "4. Momentum conserved"],
    )
    sig1 = compute_signature(s1, 1.0)
    sig2 = compute_signature(s2, 4.0)
    cmp = compare_frames(sig1, sig2)
    assert cmp.ret_a_to_b >= 0.78
    assert cmp.disappeared_frac <= 0.22
    assert sig2.content_density > sig1.content_density


def test_scroll_overlap_measurement() -> None:
    # Tall virtual lecture PDF page with non-repeating varied boxes, headings & diagrams
    tall = Image.new("RGB", (320, 480), "white")
    d = ImageDraw.Draw(tall)
    specs = [
        (14, 18, 220, 42, "#0F172A", "Chapter 1: Vector Spaces"),
        (56, 24, 290, 80, "#E2E8F0", "Span & Linear Independence"),
        (96, 18, 185, 128, "#1D4ED8", "Theorem 1.2: Basis Rank"),
        (144, 40, 300, 174, "#0F766E", "Proof: Induction on dim(V)"),
        (192, 16, 250, 226, "#4F46E5", "Matrix Nullspace Kernel"),
        (244, 70, 304, 274, "#DC2626", "Eigenvalues: det(A - lI) = 0"),
        (292, 20, 210, 326, "#0F172A", "Spectral Theorem Summary"),
        (344, 30, 285, 384, "#334155", "SVD: U Sigma V^T"),
    ]
    for y1, x1, x2, y2, fill, label in specs:
        d.rectangle([x1, y1, x2, y2], fill=fill)
        fg = "#0F172A" if fill == "#E2E8F0" else "white"
        d.text((x1 + 8, y1 + 8), label, fill=fg)
    arr = np.array(tall)

    view_top = arr[0:180, :, :]
    view_tiny_scroll = arr[25:205, :, :]  # ~86% overlap
    view_big_scroll = arr[135:315, :, :]  # ~25% overlap

    sig_top = compute_signature(view_top, 1.0)
    sig_tiny = compute_signature(view_tiny_scroll, 3.0)
    sig_big = compute_signature(view_big_scroll, 6.0)

    cmp_tiny = compare_frames(sig_top, sig_tiny)
    cmp_big = compare_frames(sig_top, sig_big)
    assert cmp_tiny.is_scroll_continuation
    assert cmp_tiny.scroll_overlap > 0.55
    assert cmp_big.scroll_overlap < 0.38


def test_webcam_mask_detects_moving_corner_box() -> None:
    base = _draw_slide("Static Slide", ["Line A", "Line B", "Line C"])
    grays = []
    rng = np.random.default_rng(42)
    for _ in range(14):
        frame = base.copy()
        # Simulate flickering corner speaker PiP in bottom-right
        frame[132:176, 250:315, :] = rng.integers(30, 230, size=(44, 65, 3), dtype=np.uint8)
        gray = np.mean(frame, axis=2).astype(np.float32)
        grays.append(gray)

    mask, box = detect_webcam_mask(grays)
    assert mask is not None
    assert box is not None
    # Verify bottom-right is masked while top-left content stays unmasked
    assert mask[155, 280]
    assert not mask[50, 60]

    eval_mask = build_eval_mask(180, 320, webcam_mask=mask)
    assert not eval_mask[155, 280]
    assert eval_mask[50, 60]


def test_detect_active_crop_removes_letterbox() -> None:
    frames = []
    for i in range(6):
        im = Image.new("RGB", (320, 180), "black")
        d = ImageDraw.Draw(im)
        d.rectangle([0, 30, 320, 150], fill="white")
        d.text((40, 60), f"Slide Content {i}", fill="black")
        frames.append(np.array(im))
    crop = detect_active_crop(frames, 1280, 720)
    assert crop is not None
    _, cy, cw, ch = crop
    assert cw == 1280
    assert 100 <= cy <= 140
    assert 440 <= ch <= 510


def test_template_mask_identifies_static_watermark() -> None:
    sigs = []
    for i in range(6):
        im = Image.new("RGB", (320, 180), "white")
        d = ImageDraw.Draw(im)
        # Persistent top-right channel logo box on every distinct slide
        d.rectangle([265, 6, 312, 22], fill="#DC2626")
        # Unique slide content per frame
        y = 35 + i * 20
        d.rectangle([20, y, 220, y + 14], fill="black")
        sigs.append(compute_signature(np.array(im), float(i)))

    t_mask = compute_template_mask(sigs)
    assert t_mask is not None
    assert np.any(t_mask[6:23, 265:313])


def test_webcam_mask_detects_inset_pip_during_camera_cuts() -> None:
    rng = np.random.default_rng(123)
    grays: list[np.ndarray] = []

    # First 8 frames: noisy full-screen camera frames (low flat smoothness, full-frame motion)
    for _ in range(8):
        cam = rng.integers(25, 220, size=(180, 320), dtype=np.uint8).astype(np.float32)
        grays.append(cam)

    # Next 10 frames: clean white canvas slide with inset floating right-side PiP box (does not touch outer border)
    base = _draw_slide("System Design", ["Node 1: API Gateway", "Node 2: Worker Queue"])
    base_gray = np.mean(base, axis=2).astype(np.float32)
    for _ in range(10):
        g = base_gray.copy()
        g[42:136, 224:302] = rng.integers(30, 230, size=(94, 78), dtype=np.uint8).astype(np.float32)
        grays.append(g)

    mask, box = detect_webcam_mask(grays)
    assert mask is not None
    assert box is not None
    assert mask[90, 265]
    assert not mask[80, 100]


def test_scaled_additive_containment_detects_zoom_out() -> None:
    # Small central box zoomed out when an enclosing container box is added
    im1 = Image.new("RGB", (320, 180), "white")
    d1 = ImageDraw.Draw(im1)
    d1.rectangle([110, 68, 210, 112], outline="#1D4ED8", fill="#EFF6FF", width=3)
    d1.text((125, 84), "Core Module", fill="#0F172A")

    im2 = Image.new("RGB", (320, 180), "white")
    d2 = ImageDraw.Draw(im2)
    d2.rectangle([50, 22, 270, 158], outline="#0F172A", width=3)
    d2.text((64, 30), "Outer Architecture", fill="#0F172A")
    # Replicate scaled (~0.70x) Core Module inside
    crop1 = im1.crop((108, 66, 212, 114)).resize((74, 34), Image.Resampling.BILINEAR)
    im2.paste(crop1, (124, 76))

    im3 = Image.new("RGB", (320, 180), "white")
    d3 = ImageDraw.Draw(im3)
    d3.ellipse([40, 30, 140, 140], fill="#DC2626")
    d3.text((170, 80), "Completely Different Chart", fill="black")

    sig1 = compute_signature(np.array(im1), 1.0)
    sig2 = compute_signature(np.array(im2), 2.0)
    sig3 = compute_signature(np.array(im3), 4.0)

    cc_12, ret_12 = check_scaled_additive_containment(sig1, sig2)
    cc_13, ret_13 = check_scaled_additive_containment(sig1, sig3)
    assert cc_12 >= 0.75 and ret_12 >= 0.38
    assert cc_13 < 0.75 or ret_13 < 0.38
