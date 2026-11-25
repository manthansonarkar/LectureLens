"""Two-pass adaptive lecture slide & scrolling-page extraction engine."""

from __future__ import annotations

import math
import subprocess
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .models import (
    Chapter,
    ExtractionConfig,
    ExtractionPreset,
    PipelineStats,
    SlideItem,
    VideoMetadata,
)
from .similarity import (
    FrameSignature,
    build_eval_mask,
    check_scaled_additive_containment,
    cluster_webcam_mask,
    compare_frames,
    compute_signature,
    compute_template_mask,
    detect_active_crop,
    grid_tile_diff_matrix,
)
from .utils import build_youtube_jump_url, find_ffmpeg, format_timestamp, probe_video


@dataclass
class CandidateFrame:
    """Candidate frame extracted from a stable plateau or checkpoint."""

    id: str
    timestamp: float
    start_time: float
    end_time: float
    signature: FrameSignature
    preview_rgb: np.ndarray | None = None
    intra_motion: float = 0.0


@dataclass
class CachedScan:
    """Reusable Pass-1 scan cache enabling instant re-filtering without re-scanning video."""

    video_path: Path
    metadata: VideoMetadata
    src_width: int
    src_height: int
    duration: float
    scan_width: int
    scan_height: int
    frames_scanned: int
    stable_windows: int
    crop_box: tuple[int, int, int, int] | None
    webcam_mask: np.ndarray | None
    webcam_box: list[float] | None
    eval_mask: np.ndarray
    template_mask: np.ndarray | None
    candidates: list[CandidateFrame] = field(default_factory=list)


ProgressCallback = Callable[[str, float, str], None]


def _choose_sample_fps(duration: float, requested_fps: float) -> float:
    if requested_fps > 0:
        return requested_fps
    if duration <= 30:
        return 4.0
    if duration <= 300:
        return 2.0
    if duration <= 1500:
        return 1.5
    if duration <= 4500:
        return 1.0
    return 0.6


def _grid_tile_diffs(gray_a: np.ndarray, gray_b: np.ndarray, rows: int = 6, cols: int = 8) -> tuple[float, float]:
    """Return (75th-percentile tile diff, max tile diff) across an 8x6 grid.

    Using the 75th percentile naturally ignores up to 25% localized webcam/cursor motion
    while remaining sensitive to full-slide transitions, scrolls, and fades.
    """
    h, w = gray_a.shape
    ch = max(1, h // rows)
    cw = max(1, w // cols)
    diff = np.abs(gray_a - gray_b)
    vals: list[float] = []
    for r in range(rows):
        r0 = r * ch
        r1 = h if r == rows - 1 else (r + 1) * ch
        for c in range(cols):
            c0 = c * cw
            c1 = w if c == cols - 1 else (c + 1) * cw
            vals.append(float(diff[r0:r1, c0:c1].mean()))
    arr = np.array(vals, dtype=np.float32)
    return float(np.percentile(arr, 75)), float(arr.max())


def _quick_frame_metrics(gray: np.ndarray) -> tuple[float, float, float]:
    """Lightweight sharpness, edge density, and flat-background smoothness inside a window."""
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    sharp = float(np.var(lap))
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    density = float(np.mean((gx * gx + gy * gy) > 500.0))
    smooth_frac = float(np.mean((np.abs(gx) + np.abs(gy)) <= 24.0))
    return sharp, density, smooth_frac


def _chapter_for_time(chapters: list[Chapter], ts: float) -> str | None:
    for ch in chapters:
        if ch.start_time <= ts <= ch.end_time + 0.5:
            return ch.title
    return None


def scan_video(
    video_path: Path,
    metadata: VideoMetadata,
    config: ExtractionConfig,
    progress_cb: ProgressCallback | None = None,
) -> CachedScan:
    """Pass 1: Stream downscaled frames through FFmpeg, detect stability windows & masks."""
    ffmpeg = find_ffmpeg()
    info = probe_video(video_path)
    src_w = int(info["width"])
    src_h = int(info["height"])
    duration = float(info["duration"]) or metadata.duration or 60.0

    sample_fps = _choose_sample_fps(duration, config.sample_fps)
    scan_w = 320
    scan_h = max(90, (int(round(scan_w * src_h / max(1, src_w))) // 2) * 2)

    if progress_cb:
        progress_cb("scanning", 0.05, f"Streaming visual scan at {sample_fps:.1f} fps ({scan_w}x{scan_h})...")

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(video_path),
        "-vf",
        f"fps={sample_fps:.4f},scale={scan_w}:{scan_h}:flags=bilinear",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    frame_size = scan_w * scan_h * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None

    expected_frames = max(1, int(math.ceil(duration * sample_fps)))
    sample_stride_for_masks = max(1, expected_frames // 140)

    mask_rgb_samples: list[np.ndarray] = []

    grid_rows, grid_cols = 12, 16
    slide_flicker = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    slide_pairs = 0
    all_flicker = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    all_pairs = 0

    # Stability window tracking (O(1) steady memory for intermediate frames)
    transition_p75_thresh = 2.6
    checkpoint_max_tile_thresh = 3.8
    min_window_frames = 2 if sample_fps >= 1.2 else 1

    # Pending checkpoints: (best_ts, win_start_t, win_end_t, best_rgb, mean_tile_motion_12x16)
    raw_checkpoints: list[tuple[float, float, float, np.ndarray, np.ndarray]] = []

    prev_gray: np.ndarray | None = None
    prev_smooth = 1.0
    win_start_t = 0.0
    win_frames = 0
    best_win_score = -1.0
    best_win_t = 0.0
    best_win_rgb: np.ndarray | None = None
    checkpoint_ref_gray: np.ndarray | None = None
    win_tm_sum = np.zeros((grid_rows, grid_cols), dtype=np.float32)
    win_tm_count = 0
    plateau_tm_sum = np.zeros((grid_rows, grid_cols), dtype=np.float32)
    plateau_tm_count = 0

    def _window_motion_avg() -> np.ndarray:
        if win_tm_count > 0:
            return win_tm_sum / float(win_tm_count)
        if plateau_tm_count > 0:
            return plateau_tm_sum / float(plateau_tm_count)
        return np.zeros((grid_rows, grid_cols), dtype=np.float32)

    idx = 0
    while True:
        buf = proc.stdout.read(frame_size)
        if len(buf) < frame_size:
            break
        rgb = np.frombuffer(buf, dtype=np.uint8).reshape((scan_h, scan_w, 3)).copy()
        ts = idx / sample_fps
        gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (3, 3), 0.7).astype(np.float32)

        if idx % sample_stride_for_masks == 0:
            mask_rgb_samples.append(rgb)

        sharp, density, smooth_frac = _quick_frame_metrics(gray)
        quality_score = sharp * (0.4 + 2.5 * min(0.35, density))

        if prev_gray is None:
            win_start_t = ts
            win_frames = 1
            best_win_score = quality_score
            best_win_t = ts
            best_win_rgb = rgb
            checkpoint_ref_gray = gray
            win_tm_sum.fill(0.0)
            win_tm_count = 0
            plateau_tm_sum.fill(0.0)
            plateau_tm_count = 0
        else:
            tm_prev = grid_tile_diff_matrix(prev_gray, gray, rows=grid_rows, cols=grid_cols)
            med_diff = float(np.median(tm_prev))
            hot_tiles = (tm_prev > 3.5).astype(np.int32)
            if med_diff < 1.8:
                all_pairs += 1
                all_flicker += hot_tiles
                if med_diff < 1.6 and prev_smooth >= 0.55 and smooth_frac >= 0.55:
                    slide_pairs += 1
                    slide_flicker += hot_tiles

            p75_diff = float(np.percentile(tm_prev, 75))
            if p75_diff > transition_p75_thresh:
                if win_frames >= min_window_frames and best_win_rgb is not None:
                    raw_checkpoints.append((best_win_t, win_start_t, ts, best_win_rgb, _window_motion_avg()))
                win_start_t = ts
                win_frames = 1
                best_win_score = quality_score
                best_win_t = ts
                best_win_rgb = rgb
                checkpoint_ref_gray = gray
                win_tm_sum.fill(0.0)
                win_tm_count = 0
                plateau_tm_sum.fill(0.0)
                plateau_tm_count = 0
            else:
                win_frames += 1
                win_tm_sum += tm_prev
                win_tm_count += 1
                plateau_tm_sum += tm_prev
                plateau_tm_count += 1
                if quality_score >= best_win_score:
                    best_win_score = quality_score
                    best_win_t = ts
                    best_win_rgb = rgb

                # Inside long stable plateaus (e.g. slow handwriting or scroll pauses),
                # emit checkpoint whenever localized content changes noticeably.
                if checkpoint_ref_gray is not None and win_frames >= min_window_frames:
                    _, max_since_ref = _grid_tile_diffs(checkpoint_ref_gray, gray)
                    if max_since_ref > checkpoint_max_tile_thresh and best_win_rgb is not None:
                        raw_checkpoints.append((best_win_t, win_start_t, ts, best_win_rgb, _window_motion_avg()))
                        win_start_t = ts
                        best_win_score = quality_score
                        best_win_t = ts
                        best_win_rgb = rgb
                        checkpoint_ref_gray = gray
                        win_tm_sum.fill(0.0)
                        win_tm_count = 0

        prev_gray = gray
        prev_smooth = smooth_frac
        idx += 1
        if progress_cb and idx % max(1, expected_frames // 20) == 0:
            frac = min(0.95, idx / expected_frames)
            progress_cb("scanning", 0.05 + 0.55 * frac, f"Scanning frames ({idx}/{expected_frames})...")

    proc.stdout.close()
    stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
    ret_code = proc.wait()
    if ret_code != 0 and idx == 0:
        raise RuntimeError(f"FFmpeg scan failed: {stderr_out.strip()}")

    final_end_t = max(duration, idx / sample_fps)
    if win_frames >= min_window_frames and best_win_rgb is not None:
        raw_checkpoints.append((best_win_t, win_start_t, final_end_t, best_win_rgb, _window_motion_avg()))

    # Fallback: if video was super dynamic and yielded 0 stable windows, sample evenly
    if not raw_checkpoints and mask_rgb_samples:
        zero_tm = np.zeros((grid_rows, grid_cols), dtype=np.float32)
        for i, rgb in enumerate(mask_rgb_samples):
            t_approx = (i * sample_stride_for_masks) / sample_fps
            raw_checkpoints.append((t_approx, t_approx, min(final_end_t, t_approx + 1.0), rgb, zero_tm))

    if progress_cb:
        progress_cb("segmenting", 0.65, f"Building motion masks & analyzing {len(raw_checkpoints)} stable checkpoints...")

    crop_box = detect_active_crop(mask_rgb_samples, src_w, src_h) if config.auto_crop_borders else None

    # Compute pixel crop slice in scan coordinates so masks match cropped active frame
    if crop_box is not None:
        cx, cy, cw, ch = crop_box
        sx1 = max(0, int(round((cx / src_w) * scan_w)))
        sy1 = max(0, int(round((cy / src_h) * scan_h)))
        sx2 = min(scan_w, int(round(((cx + cw) / src_w) * scan_w)))
        sy2 = min(scan_h, int(round(((cy + ch) / src_h) * scan_h)))
        if (sx2 - sx1) < 32 or (sy2 - sy1) < 32:
            crop_box = None
            sx1, sy1, sx2, sy2 = 0, 0, scan_w, scan_h
    else:
        sx1, sy1, sx2, sy2 = 0, 0, scan_w, scan_h

    webcam_mask_full: np.ndarray | None = None
    webcam_mask: np.ndarray | None = None
    webcam_box: list[float] | None = None
    if config.ignore_webcam:
        if slide_pairs >= 6:
            webcam_mask_full, _ = cluster_webcam_mask(slide_flicker, slide_pairs, scan_h, scan_w)
        if webcam_mask_full is None and all_pairs >= 6:
            webcam_mask_full, _ = cluster_webcam_mask(all_flicker, all_pairs, scan_h, scan_w)
        if webcam_mask_full is not None:
            sliced = webcam_mask_full[sy1:sy2, sx1:sx2]
            if np.any(sliced):
                webcam_mask = sliced
                ah, aw = sliced.shape
                ys_w, xs_w = np.where(sliced)
                webcam_box = [
                    round(int(xs_w.min()) / aw, 4),
                    round(int(ys_w.min()) / ah, 4),
                    round((int(xs_w.max()) + 1) / aw, 4),
                    round((int(ys_w.max()) + 1) / ah, 4),
                ]

    active_h = sy2 - sy1
    active_w = sx2 - sx1
    eval_mask = build_eval_mask(active_h, active_w, webcam_mask=webcam_mask, exclude_region=config.exclude_region)

    # Identify 16x12 scan tiles belonging to the evaluated (non-webcam, cropped) area for intra-window motion checks
    full_eval_tiles = np.zeros((grid_rows, grid_cols), dtype=bool)
    full_eval_mask = np.zeros((scan_h, scan_w), dtype=bool)
    full_eval_mask[sy1:sy2, sx1:sx2] = eval_mask
    cell_h = max(1, scan_h // grid_rows)
    cell_w = max(1, scan_w // grid_cols)
    for r in range(grid_rows):
        r0, r1 = r * cell_h, (scan_h if r == grid_rows - 1 else (r + 1) * cell_h)
        for c in range(grid_cols):
            c0, c1 = c * cell_w, (scan_w if c == grid_cols - 1 else (c + 1) * cell_w)
            full_eval_tiles[r, c] = float(full_eval_mask[r0:r1, c0:c1].mean()) >= 0.50
    if not np.any(full_eval_tiles):
        full_eval_tiles[:] = True

    candidates: list[CandidateFrame] = []
    for i, (ts, st, en, rgb, win_tm_avg) in enumerate(raw_checkpoints):
        cropped_rgb = rgb[sy1:sy2, sx1:sx2]
        sig = compute_signature(cropped_rgb, timestamp=ts, eval_mask=eval_mask)
        intra_motion = float(win_tm_avg[full_eval_tiles].mean()) if win_tm_avg.size == full_eval_tiles.size else 0.0
        candidates.append(
            CandidateFrame(
                id=f"cand_{i:04d}_{uuid.uuid4().hex[:6]}",
                timestamp=round(ts, 3),
                start_time=round(st, 3),
                end_time=round(en, 3),
                signature=sig,
                preview_rgb=cropped_rgb,
                intra_motion=round(intra_motion, 3),
            )
        )

    template_mask = compute_template_mask([c.signature for c in candidates])

    return CachedScan(
        video_path=video_path,
        metadata=metadata,
        src_width=src_w,
        src_height=src_h,
        duration=duration,
        scan_width=active_w,
        scan_height=active_h,
        frames_scanned=idx,
        stable_windows=len(candidates),
        crop_box=crop_box,
        webcam_mask=webcam_mask,
        webcam_box=webcam_box,
        eval_mask=eval_mask,
        template_mask=template_mask,
        candidates=candidates,
    )


@dataclass
class SegmentDecision:
    candidate: CandidateFrame
    kept: bool
    filter_reason: str
    similarity_to_prev: float
    scroll_overlap_to_prev: float
    start_time: float
    end_time: float


def segment_candidates(scan: CachedScan, config: ExtractionConfig) -> tuple[list[SegmentDecision], PipelineStats]:
    """Run intelligent slide segmentation, progressive-build collapse, scroll overlap gating & dedup."""
    eval_mask = build_eval_mask(
        scan.scan_height,
        scan.scan_width,
        webcam_mask=scan.webcam_mask if config.ignore_webcam else None,
        exclude_region=config.exclude_region,
    )
    decisions: list[SegmentDecision] = []
    kept_indices: list[int] = []  # indices into `decisions` of currently active kept slides
    pending_scroll_tail: CandidateFrame | None = None
    pending_scroll_overlap: float = 0.0

    prog_merged = 0
    dups_filtered = 0

    def _emit_pending_tail_if_needed() -> None:
        nonlocal pending_scroll_tail, pending_scroll_overlap
        if (
            pending_scroll_tail is not None
            and config.preset != ExtractionPreset.OVERLAP_STRICT
            and kept_indices
        ):
            last_dec = decisions[kept_indices[-1]]
            tail_cmp = compare_frames(
                last_dec.candidate.signature,
                pending_scroll_tail.signature,
                eval_mask=eval_mask,
                template_mask=scan.template_mask,
                check_scroll=True,
            )
            if tail_cmp.scroll_overlap <= 0.65:
                decisions.append(
                    SegmentDecision(
                        candidate=pending_scroll_tail,
                        kept=True,
                        filter_reason="kept",
                        similarity_to_prev=round(tail_cmp.combined_similarity, 4),
                        scroll_overlap_to_prev=round(tail_cmp.scroll_overlap, 4),
                        start_time=pending_scroll_tail.start_time,
                        end_time=pending_scroll_tail.end_time,
                    )
                )
                kept_indices.append(len(decisions) - 1)
        pending_scroll_tail = None
        pending_scroll_overlap = 0.0

    valid_containment_mask = eval_mask & (~scan.template_mask if scan.template_mask is not None else True)

    def _collapse_trailing_scaled_builds() -> None:
        nonlocal prog_merged
        while config.collapse_progressive and len(kept_indices) >= 2:
            cur_pos = kept_indices[-1]
            prev_pos = kept_indices[-2]
            cur_dec = decisions[cur_pos]
            prev_dec = decisions[prev_pos]
            if (
                (cur_dec.start_time - prev_dec.end_time) <= 1.5
                and (prev_dec.candidate.end_time - prev_dec.candidate.start_time) <= 2.5
                and cur_dec.candidate.signature.content_density > prev_dec.candidate.signature.content_density * 1.15
                and prev_dec.candidate.signature.content_density < 0.08
            ):
                prev_cc, prev_sr = check_scaled_additive_containment(
                    prev_dec.candidate.signature,
                    cur_dec.candidate.signature,
                    valid_containment_mask,
                )
                if prev_cc >= 0.75 and prev_sr >= 0.38:
                    decisions[cur_pos] = SegmentDecision(
                        candidate=cur_dec.candidate,
                        kept=True,
                        filter_reason="kept",
                        similarity_to_prev=prev_dec.similarity_to_prev,
                        scroll_overlap_to_prev=prev_dec.scroll_overlap_to_prev,
                        start_time=prev_dec.start_time,
                        end_time=max(prev_dec.end_time, cur_dec.end_time),
                    )
                    decisions[prev_pos] = SegmentDecision(
                        candidate=prev_dec.candidate,
                        kept=False,
                        filter_reason="progressive_step",
                        similarity_to_prev=round(prev_cc, 4),
                        scroll_overlap_to_prev=0.0,
                        start_time=prev_dec.candidate.start_time,
                        end_time=prev_dec.candidate.end_time,
                    )
                    kept_indices.pop(-2)
                    prog_merged += 1
                    continue
            break

    for cand in scan.candidates:
        # 1. Blank / extremely sparse screen & full-screen talking-head camera filter
        if config.skip_blank_or_facecam:
            if cand.signature.content_density < 0.0035:
                decisions.append(
                    SegmentDecision(
                        candidate=cand,
                        kept=False,
                        filter_reason="low_content",
                        similarity_to_prev=1.0,
                        scroll_overlap_to_prev=0.0,
                        start_time=cand.start_time,
                        end_time=cand.end_time,
                    )
                )
                dups_filtered += 1
                continue

            is_facecam = (
                cand.signature.smooth_frac < 0.44
                and cand.signature.content_density > 0.16
                and cand.intra_motion >= 0.70
            )
            if is_facecam:
                decisions.append(
                    SegmentDecision(
                        candidate=cand,
                        kept=False,
                        filter_reason="facecam",
                        similarity_to_prev=0.0,
                        scroll_overlap_to_prev=0.0,
                        start_time=cand.start_time,
                        end_time=cand.end_time,
                    )
                )
                dups_filtered += 1
                continue

        if not kept_indices:
            decisions.append(
                SegmentDecision(
                    candidate=cand,
                    kept=True,
                    filter_reason="kept",
                    similarity_to_prev=0.0,
                    scroll_overlap_to_prev=0.0,
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                )
            )
            kept_indices.append(len(decisions) - 1)
            continue

        active_pos = kept_indices[-1]
        active = decisions[active_pos]
        cmp = compare_frames(
            active.candidate.signature,
            cand.signature,
            eval_mask=eval_mask,
            template_mask=scan.template_mask,
            check_scroll=True,
        )

        # 2. Progressive / Additive Build Detection (bullet reveals, handwriting & canvas zoom-outs)
        is_additive = (
            cmp.ret_a_to_b >= 0.78
            and cmp.disappeared_frac <= 0.22
            and cand.signature.content_density > active.candidate.signature.content_density * 1.03
            and cmp.added_frac >= 0.08
        )
        if (
            not is_additive
            and config.collapse_progressive
            and (cand.start_time - active.end_time) <= 2.2
            and (active.candidate.end_time - active.candidate.start_time) <= 2.5
            and cand.signature.content_density >= active.candidate.signature.content_density * 0.92
            and active.candidate.signature.content_density < 0.08
        ):
            scaled_cc, scaled_ret = check_scaled_additive_containment(
                active.candidate.signature,
                cand.signature,
                valid_containment_mask,
            )
            if scaled_cc >= 0.75 and scaled_ret >= 0.38:
                is_additive = True
        if is_additive:
            if config.collapse_progressive:
                decisions[active_pos] = SegmentDecision(
                    candidate=cand,
                    kept=True,
                    filter_reason="kept",
                    similarity_to_prev=active.similarity_to_prev,
                    scroll_overlap_to_prev=active.scroll_overlap_to_prev,
                    start_time=active.start_time,
                    end_time=max(active.end_time, cand.end_time),
                )
                decisions.append(
                    SegmentDecision(
                        candidate=active.candidate,
                        kept=False,
                        filter_reason="progressive_step",
                        similarity_to_prev=round(cmp.combined_similarity, 4),
                        scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                        start_time=active.candidate.start_time,
                        end_time=active.candidate.end_time,
                    )
                )
                prog_merged += 1
                pending_scroll_tail = None
                _collapse_trailing_scaled_builds()
                continue
            # Step-by-Step mode: keep meaningful progressive additions directly
            decisions.append(
                SegmentDecision(
                    candidate=cand,
                    kept=True,
                    filter_reason="kept",
                    similarity_to_prev=round(cmp.combined_similarity, 4),
                    scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                )
            )
            kept_indices.append(len(decisions) - 1)
            continue

        # 2b. Subtractive / Erased-Board Guard (never emit half-erased states of the current completed slide)
        is_erased_subset = (
            config.collapse_progressive
            and cmp.ret_b_to_a >= 0.80
            and cmp.added_frac <= 0.16
            and cand.signature.content_density < active.candidate.signature.content_density * 0.92
        )
        if is_erased_subset:
            decisions.append(
                SegmentDecision(
                    candidate=cand,
                    kept=False,
                    filter_reason="erased_step",
                    similarity_to_prev=round(cmp.combined_similarity, 4),
                    scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                )
            )
            dups_filtered += 1
            continue

        # 3. Near-identical static repeat (including 1px sub-pixel zoom/pan drift)
        is_mutual_stroke_match = (
            cmp.ret_a_to_b >= 0.90
            and cmp.ret_b_to_a >= 0.90
            and cmp.struct_sim >= 0.78
        )
        if cmp.fg_iou >= 0.85 or (cmp.dhash_sim >= 0.92 and cmp.struct_sim >= 0.90) or is_mutual_stroke_match:
            active_q = active.candidate.signature.sharpness * (0.5 + active.candidate.signature.content_density * 2.0)
            cand_q = cand.signature.sharpness * (0.5 + cand.signature.content_density * 2.0)
            annotation_upgrade = (
                config.collapse_progressive
                and cand.signature.content_density >= active.candidate.signature.content_density * 1.015
                and cmp.ret_a_to_b >= 0.88
            )
            sharper_upgrade = (
                cand_q > active_q * 1.08
                and cand.signature.content_density >= active.candidate.signature.content_density * 0.95
            )
            if annotation_upgrade or sharper_upgrade:
                decisions[active_pos] = SegmentDecision(
                    candidate=cand,
                    kept=True,
                    filter_reason="kept",
                    similarity_to_prev=active.similarity_to_prev,
                    scroll_overlap_to_prev=active.scroll_overlap_to_prev,
                    start_time=active.start_time,
                    end_time=max(active.end_time, cand.end_time),
                )
                decisions.append(
                    SegmentDecision(
                        candidate=active.candidate,
                        kept=False,
                        filter_reason="duplicate",
                        similarity_to_prev=round(cmp.combined_similarity, 4),
                        scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                        start_time=active.candidate.start_time,
                        end_time=active.candidate.end_time,
                    )
                )
            else:
                active.end_time = max(active.end_time, cand.end_time)
                decisions.append(
                    SegmentDecision(
                        candidate=cand,
                        kept=False,
                        filter_reason="duplicate",
                        similarity_to_prev=round(cmp.combined_similarity, 4),
                        scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                        start_time=cand.start_time,
                        end_time=cand.end_time,
                    )
                )
            dups_filtered += 1
            continue

        # 4. Scroll Continuation Gate (enforce target scroll overlap e.g. 20-30%)
        if cmp.is_scroll_continuation:
            if cmp.scroll_overlap > config.scroll_max_overlap:
                if cmp.scroll_overlap <= 0.65:
                    pending_scroll_tail = cand
                    pending_scroll_overlap = cmp.scroll_overlap
                active.end_time = max(active.end_time, cand.end_time)
                decisions.append(
                    SegmentDecision(
                        candidate=cand,
                        kept=False,
                        filter_reason="duplicate",
                        similarity_to_prev=round(cmp.combined_similarity, 4),
                        scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                        start_time=cand.start_time,
                        end_time=cand.end_time,
                    )
                )
                dups_filtered += 1
                continue
            # Scroll overlap dropped <= threshold -> genuine new scrolled section!
            pending_scroll_tail = None

        # 5. General Similarity Threshold Check
        if cmp.combined_similarity > config.max_similarity:
            active.end_time = max(active.end_time, cand.end_time)
            decisions.append(
                SegmentDecision(
                    candidate=cand,
                    kept=False,
                    filter_reason="duplicate",
                    similarity_to_prev=round(cmp.combined_similarity, 4),
                    scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                )
            )
            dups_filtered += 1
            continue

        # Switching away from a scrolled document: preserve final bottom view if uncaptured
        if not cmp.is_scroll_continuation and pending_scroll_tail is not None:
            _emit_pending_tail_if_needed()
            # Re-compute comparison against newly emitted tail
            active = decisions[kept_indices[-1]]
            cmp = compare_frames(
                active.candidate.signature,
                cand.signature,
                eval_mask=eval_mask,
                template_mask=scan.template_mask,
                check_scroll=True,
            )

        # 6. Global Repeat Check (e.g. speaker jumped back to an earlier slide)
        if config.global_dedup and len(kept_indices) > 1:
            is_global_repeat = False
            for k_idx in kept_indices[:-1]:
                prev_dec = decisions[k_idx]
                g_cmp = compare_frames(
                    prev_dec.candidate.signature,
                    cand.signature,
                    eval_mask=eval_mask,
                    template_mask=scan.template_mask,
                    check_scroll=False,
                )
                is_subset_repeat = g_cmp.ret_b_to_a >= 0.88 and g_cmp.added_frac <= 0.12
                if (
                    g_cmp.fg_iou >= 0.82
                    or (g_cmp.dhash_sim >= 0.90 and g_cmp.struct_sim >= 0.88)
                    or is_subset_repeat
                ):
                    is_global_repeat = True
                    decisions.append(
                        SegmentDecision(
                            candidate=cand,
                            kept=False,
                            filter_reason="global_repeat",
                            similarity_to_prev=round(g_cmp.combined_similarity, 4),
                            scroll_overlap_to_prev=0.0,
                            start_time=cand.start_time,
                            end_time=cand.end_time,
                        )
                    )
                    dups_filtered += 1
                    break
            if is_global_repeat:
                continue

        # 7. Keep genuine new slide/page!
        decisions.append(
            SegmentDecision(
                candidate=cand,
                kept=True,
                filter_reason="kept",
                similarity_to_prev=round(cmp.combined_similarity, 4),
                scroll_overlap_to_prev=round(cmp.scroll_overlap, 4),
                start_time=cand.start_time,
                end_time=cand.end_time,
            )
        )
        kept_indices.append(len(decisions) - 1)
        _collapse_trailing_scaled_builds()

    _emit_pending_tail_if_needed()

    # Keep chronological order by timestamp
    decisions.sort(key=lambda d: d.candidate.timestamp)

    kept_count = sum(1 for d in decisions if d.kept)
    stats = PipelineStats(
        frames_scanned=scan.frames_scanned,
        stable_windows=scan.stable_windows,
        slides_kept=kept_count,
        duplicates_filtered=dups_filtered,
        progressive_merged=prog_merged,
        webcam_masked=scan.webcam_mask is not None and config.ignore_webcam,
        webcam_box=scan.webcam_box if config.ignore_webcam else None,
        crop_box=list(scan.crop_box) if (scan.crop_box and config.auto_crop_borders) else None,
    )
    return decisions, stats


def capture_frame_hd(
    video_path: Path,
    timestamp: float,
    out_png: Path,
    out_thumb: Path,
    crop_box: tuple[int, int, int, int] | None = None,
) -> tuple[int, int]:
    """Extract a crisp full-resolution PNG frame and 480px thumbnail at `timestamp`."""
    ffmpeg = find_ffmpeg()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_thumb.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg,
        "-v",
        "error",
        "-ss",
        f"{max(0.0, timestamp):.3f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
    ]
    if crop_box is not None:
        cx, cy, cw, ch = crop_box
        cmd.extend(["-vf", f"crop={cw}:{ch}:{cx}:{cy}"])
    cmd.extend(["-y", str(out_png)])
    subprocess.run(cmd, check=True, capture_output=True)

    with Image.open(out_png) as img:
        w, h = img.size
        thumb = img.copy()
        thumb.thumbnail((480, 480), Image.Resampling.LANCZOS)
        thumb.convert("RGB").save(out_thumb, format="JPEG", quality=86, optimize=True)
    return w, h


def build_slides_from_decisions(
    scan: CachedScan,
    decisions: list[SegmentDecision],
    config: ExtractionConfig,
    output_dir: Path,
    url_prefix: str = "",
    include_rejected_thumbs: bool = True,
    progress_cb: ProgressCallback | None = None,
) -> list[SlideItem]:
    """Pass 2: Extract full-resolution HD PNGs for kept slides (and fast thumbs for filtered ones)."""
    slides_dir = output_dir / "slides"
    thumbs_dir = output_dir / "thumbs"
    slides_dir.mkdir(parents=True, exist_ok=True)
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    crop = scan.crop_box if config.auto_crop_borders else None
    targets = [d for d in decisions if d.kept or include_rejected_thumbs]

    # Reuse already-captured HD frames when re-filtering!
    to_capture: list[SegmentDecision] = []
    for dec in targets:
        png_path = slides_dir / f"{dec.candidate.id}.png"
        thumb_path = thumbs_dir / f"{dec.candidate.id}.jpg"
        if dec.kept:
            if not png_path.exists() or not thumb_path.exists():
                to_capture.append(dec)
        else:
            if not thumb_path.exists() and dec.candidate.preview_rgb is not None:
                Image.fromarray(dec.candidate.preview_rgb).save(
                    thumb_path, format="JPEG", quality=82
                )

    total = max(1, len(to_capture))
    done = 0
    dims_map: dict[str, tuple[int, int]] = {}

    if to_capture:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {
                pool.submit(
                    capture_frame_hd,
                    scan.video_path,
                    dec.candidate.timestamp,
                    slides_dir / f"{dec.candidate.id}.png",
                    thumbs_dir / f"{dec.candidate.id}.jpg",
                    crop,
                ): dec
                for dec in to_capture
            }
            for fut in as_completed(futs):
                dec = futs[fut]
                dims_map[dec.candidate.id] = fut.result()
                done += 1
                if progress_cb:
                    frac = done / total
                    progress_cb("capturing", 0.70 + 0.18 * frac, f"Capturing HD frames ({done}/{total})...")

    slides: list[SlideItem] = []
    kept_counter = 0
    for dec in targets:
        cand = dec.candidate
        png_path = slides_dir / f"{cand.id}.png"
        thumb_path = thumbs_dir / f"{cand.id}.jpg"
        if cand.id in dims_map:
            w, h = dims_map[cand.id]
        elif png_path.exists():
            with Image.open(png_path) as im:
                w, h = im.size
        else:
            w, h = scan.src_width, scan.src_height

        if dec.kept:
            kept_counter += 1
            disp_idx = kept_counter
        else:
            disp_idx = 0

        jump_url = None
        if not scan.metadata.is_local_file:
            jump_url = build_youtube_jump_url(scan.metadata.source_url, cand.timestamp)

        img_url = (
            f"{url_prefix}/slides/{cand.id}.png"
            if (url_prefix and png_path.exists())
            else (f"{url_prefix}/thumbs/{cand.id}.jpg" if url_prefix else str(png_path))
        )

        slides.append(
            SlideItem(
                id=cand.id,
                index=disp_idx,
                timestamp=cand.timestamp,
                start_time=dec.start_time,
                end_time=dec.end_time,
                timestamp_label=format_timestamp(cand.timestamp),
                youtube_jump_url=jump_url,
                chapter_title=_chapter_for_time(scan.metadata.chapters, cand.timestamp),
                image_path=str(png_path),
                thumb_path=str(thumb_path),
                image_url=img_url,
                thumb_url=f"{url_prefix}/thumbs/{cand.id}.jpg" if url_prefix else str(thumb_path),
                width=w,
                height=h,
                similarity_to_prev=dec.similarity_to_prev,
                scroll_overlap_to_prev=dec.scroll_overlap_to_prev,
                sharpness=round(cand.signature.sharpness, 2),
                content_density=round(cand.signature.content_density, 4),
                kept=dec.kept,
                filter_reason=dec.filter_reason,
            )
        )

    return slides
