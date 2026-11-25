"""Computer vision metrics for background-invariant lecture slide & scroll similarity."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FrameSignature:
    """Compact multi-signal representation of a sampled video frame."""

    timestamp: float
    gray: np.ndarray  # float32 HxW in [0, 255]
    fg_mask: np.ndarray  # bool HxW crisp foreground ink/text/graphics (median-isolated)
    fg_small: np.ndarray  # bool 54x96 downsampled foreground for fast scroll correlation
    fg_small_dil: np.ndarray  # bool 54x96 1px-dilated foreground for sub-row scroll quantization
    gray_small: np.ndarray  # float32 54x96 downsampled gray for scroll band verification
    tile_vecs: np.ndarray  # float32 (T, 257) per-tile normalized local descriptors
    tile_active: np.ndarray  # bool (T,) whether tile holds meaningful foreground strokes
    dhash: np.ndarray  # bool length-256 16x16 difference hash
    sharpness: float
    content_density: float
    edge_energy: float
    smooth_frac: float = 1.0


@dataclass
class FrameComparison:
    """Pairwise visual and structural comparison between two frames."""

    fg_iou: float
    ret_a_to_b: float
    ret_b_to_a: float
    disappeared_frac: float
    added_frac: float
    struct_sim: float
    dhash_sim: float
    scroll_overlap: float
    scroll_dy: int
    is_scroll_continuation: bool
    combined_similarity: float


def compute_dhash(gray: np.ndarray, hash_size: int = 16) -> np.ndarray:
    """Compute a 256-bit (16x16) perceptual difference hash."""
    resized = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def build_eval_mask(
    height: int,
    width: int,
    webcam_mask: np.ndarray | None = None,
    exclude_region: list[float] | None = None,
) -> np.ndarray:
    """Build boolean mask of pixels INCLUDED in slide comparison (True = include)."""
    mask = np.ones((height, width), dtype=bool)
    if webcam_mask is not None and webcam_mask.shape == (height, width):
        mask &= ~webcam_mask
    if exclude_region and len(exclude_region) == 4:
        x1, y1, x2, y2 = exclude_region
        ix1 = max(0, min(width, int(round(min(x1, x2) * width))))
        ix2 = max(0, min(width, int(round(max(x1, x2) * width))))
        iy1 = max(0, min(height, int(round(min(y1, y2) * height))))
        iy2 = max(0, min(height, int(round(max(y1, y2) * height))))
        if ix2 > ix1 and iy2 > iy1:
            mask[iy1:iy2, ix1:ix2] = False
    if float(mask.mean()) < 0.30:
        return np.ones((height, width), dtype=bool)
    return mask


def _extract_tile_descriptors(
    gray: np.ndarray,
    fg_mask: np.ndarray,
    eval_mask: np.ndarray | None,
    rows: int = 9,
    cols: int = 16,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute crisp 16x16+luma local descriptors and active flags across a 16x9 grid."""
    h, w = gray.shape
    ch = max(1, h // rows)
    cw = max(1, w // cols)
    vecs: list[np.ndarray] = []
    actives: list[bool] = []

    for r in range(rows):
        r0 = r * ch
        r1 = h if r == rows - 1 else (r + 1) * ch
        for c in range(cols):
            c0 = c * cw
            c1 = w if c == cols - 1 else (c + 1) * cw
            if eval_mask is not None and float(eval_mask[r0:r1, c0:c1].mean()) < 0.35:
                vecs.append(np.zeros(257, dtype=np.float32))
                actives.append(False)
                continue

            patch = cv2.resize(gray[r0:r1, c0:c1], (16, 16), interpolation=cv2.INTER_AREA).flatten()
            mean_val = float(patch.mean())
            centered = patch - mean_val
            norm = float(np.linalg.norm(centered))
            if norm > 8.0:
                desc = centered / norm
            else:
                desc = np.zeros(256, dtype=np.float32)

            # Include brightness polarity so light-vs-dark flip drops correlation
            luma_comp = ((mean_val / 127.5) - 1.0) * 0.45
            desc_full = np.append(desc * 0.90, luma_comp).astype(np.float32)
            fn = float(np.linalg.norm(desc_full))
            if fn > 1e-6:
                desc_full /= fn
            vecs.append(desc_full)

            fg_count = int(fg_mask[r0:r1, c0:c1].sum())
            actives.append(fg_count >= 5)

    return np.stack(vecs, axis=0), np.array(actives, dtype=bool)


def compute_signature(
    rgb_frame: np.ndarray,
    timestamp: float,
    eval_mask: np.ndarray | None = None,
) -> FrameSignature:
    """Extract multi-signal visual signature from an RGB frame."""
    gray_u8 = cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2GRAY)
    gray_f = gray_u8.astype(np.float32)
    gray_smooth = cv2.GaussianBlur(gray_f, (3, 3), 0.6)

    # Median background removes uniform/gradient backgrounds with ZERO Gaussian halo around text
    median_bg = cv2.medianBlur(gray_u8, 15).astype(np.float32)
    fg_diff = np.abs(gray_f - median_bg)

    gx = cv2.Sobel(gray_smooth, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray_smooth, cv2.CV_32F, 0, 1, ksize=3)
    edge_mag = np.sqrt(gx * gx + gy * gy)
    smooth_pixels = (np.abs(gx) + np.abs(gy)) <= 24.0

    fg_mask = fg_diff > 16.0

    h, w = gray_u8.shape
    if eval_mask is not None and eval_mask.shape == (h, w):
        active_fg = fg_mask & eval_mask
        active_area = float(eval_mask.sum()) + 1e-6
        masked_gray = np.where(eval_mask, gray_f, 128.0)
        masked_edge = np.where(eval_mask, edge_mag, 0.0)
        smooth_frac = float(smooth_pixels[eval_mask].mean())
    else:
        active_fg = fg_mask
        active_area = float(h * w)
        masked_gray = gray_f
        masked_edge = edge_mag
        smooth_frac = float(smooth_pixels.mean())

    content_density = float(active_fg.sum()) / active_area
    edge_energy = float(masked_edge.sum()) / active_area

    lap = cv2.Laplacian(gray_smooth, cv2.CV_32F)
    if eval_mask is not None and eval_mask.shape == (h, w):
        sharpness = float(np.var(lap[eval_mask]))
    else:
        sharpness = float(np.var(lap))

    small_w, small_h = 96, 54
    fg_small = cv2.resize(active_fg.astype(np.uint8), (small_w, small_h), interpolation=cv2.INTER_AREA) > 0
    k3 = np.ones((3, 3), dtype=np.uint8)
    fg_small_dil = cv2.dilate(fg_small.astype(np.uint8), k3, iterations=1) > 0
    gray_small = cv2.resize(masked_gray, (small_w, small_h), interpolation=cv2.INTER_AREA).astype(np.float32)

    tile_vecs, tile_active = _extract_tile_descriptors(gray_f, active_fg, eval_mask)
    dhash = compute_dhash(masked_gray, hash_size=16)

    return FrameSignature(
        timestamp=timestamp,
        gray=gray_f,
        fg_mask=fg_mask,
        fg_small=fg_small,
        fg_small_dil=fg_small_dil,
        gray_small=gray_small,
        tile_vecs=tile_vecs,
        tile_active=tile_active,
        dhash=dhash,
        sharpness=sharpness,
        content_density=content_density,
        edge_energy=edge_energy,
        smooth_frac=smooth_frac,
    )


def detect_active_crop(
    rgb_frames: list[np.ndarray],
    src_width: int,
    src_height: int,
) -> tuple[int, int, int, int] | None:
    """Detect constant letterbox/pillarbox black bars and return source-pixel crop box (x, y, w, h) or None."""
    if not rgb_frames:
        return None
    sample = np.stack([cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in rgb_frames], axis=0)
    max_proj = np.percentile(sample, 90, axis=0)
    h, w = max_proj.shape

    row_active = np.mean(max_proj > 16, axis=1) > 0.03
    col_active = np.mean(max_proj > 16, axis=0) > 0.03
    if not np.any(row_active) or not np.any(col_active):
        return None

    y1 = int(np.argmax(row_active))
    y2 = int(h - np.argmax(row_active[::-1]))
    x1 = int(np.argmax(col_active))
    x2 = int(w - np.argmax(col_active[::-1]))

    margin_frac = 1.0 - ((x2 - x1) * (y2 - y1)) / float(w * h)
    if margin_frac < 0.05 or (x2 - x1) < 0.55 * w or (y2 - y1) < 0.55 * h:
        return None

    sx = int(round((x1 / w) * src_width)) & ~1
    sy = int(round((y1 / h) * src_height)) & ~1
    sw = int(round(((x2 - x1) / w) * src_width)) & ~1
    sh = int(round(((y2 - y1) / h) * src_height)) & ~1
    if sw < 64 or sh < 64 or (sw >= src_width - 8 and sh >= src_height - 8):
        return None
    return (sx, sy, sw, sh)


def grid_tile_diff_matrix(
    gray_a: np.ndarray,
    gray_b: np.ndarray,
    rows: int = 12,
    cols: int = 16,
) -> np.ndarray:
    """Compute per-tile mean absolute difference across a rows x cols spatial grid."""
    h, w = gray_a.shape
    ch = max(1, h // rows)
    cw = max(1, w // cols)
    diff = np.abs(gray_a - gray_b)
    tile_means = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        r0 = r * ch
        r1 = h if r == rows - 1 else (r + 1) * ch
        for c in range(cols):
            c0 = c * cw
            c1 = w if c == cols - 1 else (c + 1) * cw
            tile_means[r, c] = float(diff[r0:r1, c0:c1].mean())
    return tile_means


def cluster_webcam_mask(
    flicker_counts: np.ndarray,
    pair_count: int,
    height: int,
    width: int,
    min_pairs: int = 6,
) -> tuple[np.ndarray | None, list[float] | None]:
    """Cluster localized perimeter/near-perimeter high-motion tiles into a PiP webcam mask."""
    if pair_count < min_pairs:
        return None, None

    grid_rows, grid_cols = flicker_counts.shape
    cell_h = max(1, height // grid_rows)
    cell_w = max(1, width // grid_cols)

    rates = flicker_counts / float(pair_count)
    hot_seed = rates >= 0.25
    if not np.any(hot_seed):
        return None, None

    # Hysteresis grow to include soft border/hair tiles (>= 0.14) touching core motion tiles
    hot = hot_seed.copy()
    k3 = np.ones((3, 3), dtype=np.uint8)
    for _ in range(2):
        adj = cv2.dilate(hot.astype(np.uint8), k3) > 0
        new_hot = hot | (adj & (rates >= 0.14))
        if np.array_equal(new_hot, hot):
            break
        hot = new_hot

    # Allow inset floating PiP cards situated within outer 2 tiles (12-16% border band) on 16x12 grids
    margin_r = max(1, grid_rows // 6)
    margin_c = max(1, grid_cols // 8)
    perimeter_mask = np.zeros((grid_rows, grid_cols), dtype=bool)
    perimeter_mask[:margin_r, :] = True
    perimeter_mask[-margin_r:, :] = True
    perimeter_mask[:, :margin_c] = True
    perimeter_mask[:, -margin_c:] = True

    num_labels, labels, _, _ = cv2.connectedComponentsWithStats(hot.astype(np.uint8), connectivity=8)
    best_cluster: np.ndarray | None = None
    best_area = 0
    min_tiles = 2 if (grid_rows * grid_cols) >= 128 else 1
    max_allowed_tiles = int(0.36 * grid_rows * grid_cols)

    for lbl in range(1, num_labels):
        comp = labels == lbl
        area = int(comp.sum())
        if min_tiles <= area <= max_allowed_tiles and np.any(comp & perimeter_mask) and np.any(comp & hot_seed):
            if area > best_area:
                best_area = area
                best_cluster = comp

    if best_cluster is None:
        return None, None

    ys, xs = np.where(best_cluster)
    r_min, r_max = int(ys.min()), int(ys.max())
    c_min, c_max = int(xs.min()), int(xs.max())

    y1 = max(0, r_min * cell_h)
    y2 = min(height, height if r_max == grid_rows - 1 else (r_max + 1) * cell_h)
    x1 = max(0, c_min * cell_w)
    x2 = min(width, width if c_max == grid_cols - 1 else (c_max + 1) * cell_w)

    # Expand inward edges slightly (~3.2%) so static rounded card frames around PiP never leak into eval_mask
    pad_x = max(2, int(round(0.032 * width)))
    pad_y = max(2, int(round(0.035 * height)))
    x1 = max(0, x1 - pad_x) if c_min > 0 else 0
    x2 = min(width, x2 + pad_x) if c_max < grid_cols - 1 else width
    y1 = max(0, y1 - pad_y) if r_min > 0 else 0
    y2 = min(height, y2 + pad_y) if r_max < grid_rows - 1 else height

    pixel_mask = np.zeros((height, width), dtype=bool)
    pixel_mask[y1:y2, x1:x2] = True
    norm_box = [round(x1 / width, 4), round(y1 / height, 4), round(x2 / width, 4), round(y2 / height, 4)]
    return pixel_mask, norm_box


def detect_webcam_mask(
    grays: list[np.ndarray],
    grid_cols: int = 16,
    grid_rows: int = 12,
) -> tuple[np.ndarray | None, list[float] | None]:
    """Identify persistent corner/edge PiP speaker overlay via tile temporal variance on slide-like frames."""
    if len(grays) < 8:
        return None, None

    h, w = grays[0].shape
    slide_flicker = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    slide_pairs = 0
    all_flicker = np.zeros((grid_rows, grid_cols), dtype=np.int32)
    all_pairs = 0

    def _is_slide_smooth(g: np.ndarray) -> bool:
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        return float(((np.abs(gx) + np.abs(gy)) <= 24.0).mean()) >= 0.50

    prev_smooth = _is_slide_smooth(grays[0])
    for i in range(1, len(grays)):
        cur_smooth = _is_slide_smooth(grays[i])
        tile_means = grid_tile_diff_matrix(grays[i - 1], grays[i], rows=grid_rows, cols=grid_cols)
        med = float(np.median(tile_means))
        hot_tiles = (tile_means > 3.5).astype(np.int32)
        if med < 1.8:
            all_pairs += 1
            all_flicker += hot_tiles
            if prev_smooth and cur_smooth and med < 1.6:
                slide_pairs += 1
                slide_flicker += hot_tiles
        prev_smooth = cur_smooth

    if slide_pairs >= 6:
        mask, box = cluster_webcam_mask(slide_flicker, slide_pairs, h, w)
        if mask is not None:
            return mask, box
    return cluster_webcam_mask(all_flicker, all_pairs, h, w)


def compute_template_mask(signatures: list[FrameSignature]) -> np.ndarray | None:
    """Detect static channel watermarks / borders present across >72% of distinct slides."""
    if len(signatures) < 5:
        return None

    distinct: list[FrameSignature] = [signatures[0]]
    for sig in signatures[1:]:
        active = distinct[-1].tile_active | sig.tile_active
        dots = np.sum(distinct[-1].tile_vecs * sig.tile_vecs, axis=1)
        mean_dot = float(dots[active].mean()) if np.any(active) else float(dots.mean())
        if mean_dot < 0.85:
            distinct.append(sig)

    if len(distinct) < 5:
        return None

    stack = np.stack([s.fg_mask for s in distinct], axis=0)
    presence = np.mean(stack, axis=0)
    template = presence >= 0.72
    if float(template.mean()) > 0.22:
        return None
    return template


def _compute_scroll_overlap(
    sig_a: FrameSignature,
    sig_b: FrameSignature,
    valid_mask: np.ndarray | None = None,
) -> tuple[float, int]:
    """Search vertical scroll shifts and verify top candidates at full analysis resolution."""
    hs, _ = sig_a.fg_small.shape
    a_sum = float(sig_a.fg_small.sum())
    b_sum = float(sig_b.fg_small.sum())
    if a_sum < 12 or b_sum < 12:
        return 0.0, 0

    max_shift = int(0.84 * hs)
    coarse_hits: list[tuple[float, int]] = []

    for dy in range(-max_shift, max_shift + 1, 1):
        if abs(dy) < 3:
            continue
        if dy > 0:
            fg_a = sig_a.fg_small[:-dy, :]
            fg_b_dil = sig_b.fg_small_dil[dy:, :]
            ga = sig_a.gray_small[:-dy, :]
            gb = sig_b.gray_small[dy:, :]
        else:
            s = -dy
            fg_a = sig_a.fg_small[s:, :]
            fg_b_dil = sig_b.fg_small_dil[:-s, :]
            ga = sig_a.gray_small[s:, :]
            gb = sig_b.gray_small[:-s, :]

        if float(fg_a.sum()) < 10 or float(fg_b_dil.sum()) < 10:
            continue

        va = ga - float(ga.mean())
        vb = gb - float(gb.mean())
        na = float(np.linalg.norm(va))
        nb = float(np.linalg.norm(vb))
        if na < 1e-5 or nb < 1e-5:
            continue
        band_corr = float(np.dot(va.ravel(), vb.ravel())) / (na * nb)
        if band_corr < 0.65:
            continue

        score = band_corr * float(np.sum(fg_a & fg_b_dil))
        coarse_hits.append((score, dy))

    if not coarse_hits:
        return 0.0, 0

    coarse_hits.sort(reverse=True)

    # Stage 2: Verify top coarse shifts at full analysis resolution (320x180)
    hf, _ = sig_a.gray.shape
    fg_a_full = sig_a.fg_mask & valid_mask if valid_mask is not None else sig_a.fg_mask
    fg_b_full = sig_b.fg_mask & valid_mask if valid_mask is not None else sig_b.fg_mask
    denom_full = max(float(fg_a_full.sum()), float(fg_b_full.sum()), 1.0)

    best_overlap = 0.0
    best_dy_full = 0
    tested: set[int] = set()

    for _, dy_s in coarse_hits[:8]:
        base_dy = int(round(dy_s * hf / float(hs)))
        for delta in range(-2, 3):
            dy_f = base_dy + delta
            if dy_f in tested or abs(dy_f) < 8 or abs(dy_f) >= int(0.88 * hf):
                continue
            tested.add(dy_f)

            if dy_f > 0:
                ga_f = sig_a.gray[:-dy_f, :]
                gb_f = sig_b.gray[dy_f:, :]
                fa_f = fg_a_full[:-dy_f, :]
                fb_f = fg_b_full[dy_f:, :]
            else:
                sf = -dy_f
                ga_f = sig_a.gray[sf:, :]
                gb_f = sig_b.gray[:-sf, :]
                fa_f = fg_a_full[sf:, :]
                fb_f = fg_b_full[:-sf, :]

            band_fa = float(fa_f.sum())
            band_fb = float(fb_f.sum())
            if band_fa < 25 or band_fb < 25:
                continue

            va_f = ga_f - float(ga_f.mean())
            vb_f = gb_f - float(gb_f.mean())
            na_f = float(np.linalg.norm(va_f))
            nb_f = float(np.linalg.norm(vb_f))
            if na_f < 1e-5 or nb_f < 1e-5:
                continue
            corr_f = float(np.dot(va_f.ravel(), vb_f.ravel())) / (na_f * nb_f)
            if corr_f < 0.84:
                continue

            # Verify true pixel luminance match inside the overlapping band (rejects fake contrast-rescaled aliases)
            band_mae = float(np.mean(np.abs(ga_f - gb_f)))
            if band_mae > 11.0:
                continue

            # Pixel-accurate intensity-checked stroke overlap inside the overlapping slice
            matched_fg = fa_f & fb_f & (np.abs(ga_f - gb_f) < 22.0)
            inter_f = float(matched_fg.sum())
            band_iou = (2.0 * inter_f) / (band_fa + band_fb + 1e-6)
            if band_iou < 0.45:
                continue

            total_overlap = inter_f / denom_full
            if total_overlap > best_overlap:
                best_overlap = total_overlap
                best_dy_full = dy_f

    return float(min(1.0, best_overlap)), best_dy_full


def _template_tile_mask(template_mask: np.ndarray | None, rows: int = 9, cols: int = 16) -> np.ndarray | None:
    """Identify grid tiles dominated by static template/watermark edges."""
    if template_mask is None:
        return None
    h, w = template_mask.shape
    ch = max(1, h // rows)
    cw = max(1, w // cols)
    out = np.zeros(rows * cols, dtype=bool)
    idx = 0
    for r in range(rows):
        r0 = r * ch
        r1 = h if r == rows - 1 else (r + 1) * ch
        for c in range(cols):
            c0 = c * cw
            c1 = w if c == cols - 1 else (c + 1) * cw
            out[idx] = float(template_mask[r0:r1, c0:c1].mean()) > 0.03
            idx += 1
    return out


def check_scaled_additive_containment(
    sig_a: FrameSignature,
    sig_b: FrameSignature,
    valid_mask: np.ndarray | None = None,
) -> tuple[float, float]:
    """Detect whether active content of `sig_a` is contained inside `sig_b` after canvas zoom-out/pan."""
    h, w = sig_a.gray.shape
    mask = valid_mask if (valid_mask is not None and valid_mask.shape == (h, w)) else np.ones((h, w), dtype=bool)
    fg_a = sig_a.fg_mask & mask
    fg_b = sig_b.fg_mask & mask
    ys, xs = np.where(fg_a)
    if len(xs) < 40:
        return 0.0, 0.0

    x1 = max(0, int(xs.min()) - 2)
    x2 = min(w, int(xs.max()) + 3)
    y1 = max(0, int(ys.min()) - 2)
    y2 = min(h, int(ys.max()) + 3)
    bw, bh = x2 - x1, y2 - y1
    if bw < 8 or bh < 8 or (bw >= int(0.88 * w) and bh >= int(0.88 * h)):
        return 0.0, 0.0

    patch_g = sig_a.gray[y1:y2, x1:x2]
    patch_fg = fg_a[y1:y2, x1:x2].astype(np.uint8)
    bg_fill = float(np.median(sig_b.gray[mask])) if np.any(mask) else 128.0
    b_g = np.where(mask, sig_b.gray, bg_fill).astype(np.float32)

    k3 = np.ones((3, 3), dtype=np.uint8)
    b_dil = cv2.dilate(fg_b.astype(np.uint8), k3) > 0

    best_cc = 0.0
    best_ret = 0.0
    for sc in (0.55, 0.62, 0.70, 0.75, 0.82, 0.90, 1.0):
        tw = max(8, int(round(bw * sc)))
        th = max(8, int(round(bh * sc)))
        if tw >= w - 2 or th >= h - 2:
            continue
        tg = cv2.resize(patch_g, (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32)
        if float(np.std(tg)) < 3.0:
            continue
        res = cv2.matchTemplate(b_g, tg, cv2.TM_CCOEFF_NORMED)
        _, max_v, _, (lx, ly) = cv2.minMaxLoc(res)
        if max_v > best_cc:
            tfg = cv2.resize(patch_fg, (tw, th), interpolation=cv2.INTER_NEAREST) > 0
            denom = float(tfg.sum())
            if denom > 10.0:
                bg_win = b_g[ly : ly + th, lx : lx + tw]
                ret = float((tfg & b_dil[ly : ly + th, lx : lx + tw] & (np.abs(bg_win - tg) < 30.0)).sum()) / denom
            else:
                ret = 0.0
            best_cc = float(max_v)
            best_ret = float(ret)
    return best_cc, best_ret


def compare_frames(
    sig_a: FrameSignature,
    sig_b: FrameSignature,
    eval_mask: np.ndarray | None = None,
    template_mask: np.ndarray | None = None,
    check_scroll: bool = True,
) -> FrameComparison:
    """Compare two frame signatures using intensity-aware foreground & active-tile metrics."""
    valid = np.ones_like(sig_a.fg_mask, dtype=bool)
    if eval_mask is not None and eval_mask.shape == valid.shape:
        valid &= eval_mask
    if template_mask is not None and template_mask.shape == valid.shape:
        valid &= ~template_mask

    fg_a = sig_a.fg_mask & valid
    fg_b = sig_b.fg_mask & valid

    sum_a = float(fg_a.sum())
    sum_b = float(fg_b.sum())

    if sum_a < 10.0 and sum_b < 10.0:
        return FrameComparison(
            fg_iou=1.0,
            ret_a_to_b=1.0,
            ret_b_to_a=1.0,
            disappeared_frac=0.0,
            added_frac=0.0,
            struct_sim=1.0,
            dhash_sim=1.0,
            scroll_overlap=0.0,
            scroll_dy=0,
            is_scroll_continuation=False,
            combined_similarity=1.0,
        )

    # Pixel-accurate intensity-checked foreground overlap (tolerates minor codec noise via 1px envelope)
    gray_diff = np.abs(sig_a.gray - sig_b.gray)
    strict_match = fg_a & fg_b & (gray_diff < 26.0)
    strict_inter = float(strict_match.sum())

    k3 = np.ones((3, 3), dtype=np.uint8)
    b_min = cv2.erode(sig_b.gray, k3)
    b_max = cv2.dilate(sig_b.gray, k3)
    b_fg_dil = cv2.dilate(fg_b.astype(np.uint8), k3) > 0
    a_min = cv2.erode(sig_a.gray, k3)
    a_max = cv2.dilate(sig_a.gray, k3)
    a_fg_dil = cv2.dilate(fg_a.astype(np.uint8), k3) > 0

    tol = 22.0
    a_in_b = fg_a & b_fg_dil & ((sig_a.gray >= b_min - tol) & (sig_a.gray <= b_max + tol))
    b_in_a = fg_b & a_fg_dil & ((sig_b.gray >= a_min - tol) & (sig_b.gray <= a_max + tol))

    inter_ab = float(a_in_b.sum())
    inter_ba = float(b_in_a.sum())

    # Retention uses 1px envelope so MP4 compression jitter never breaks additive build detection
    ret_a_to_b = min(1.0, inter_ab / (sum_a + 1e-6)) if sum_a >= 10.0 else 0.0
    ret_b_to_a = min(1.0, inter_ba / (sum_b + 1e-6)) if sum_b >= 10.0 else 0.0
    disappeared_frac = max(0.0, 1.0 - ret_a_to_b)
    added_frac = max(0.0, 1.0 - ret_b_to_a)

    # IoU uses strict 1x1 pixel agreement blended lightly with envelope to discriminate fine text
    eff_inter = 0.70 * strict_inter + 0.30 * min(inter_ab, inter_ba)
    fg_iou = min(1.0, (2.0 * eff_inter) / (sum_a + sum_b + 1e-6))

    # Equal-weight active-tile structural similarity (prevents header bars from drowning out text!)
    tile_dots = np.sum(sig_a.tile_vecs * sig_b.tile_vecs, axis=1)
    tile_sims = np.clip(tile_dots, 0.0, 1.0)
    active_tiles = sig_a.tile_active | sig_b.tile_active
    t_tile_mask = _template_tile_mask(template_mask)
    if t_tile_mask is not None:
        non_tmpl = active_tiles & ~t_tile_mask
        if np.any(non_tmpl):
            active_tiles = non_tmpl

    if np.any(active_tiles):
        vals = tile_sims[active_tiles]
        struct_sim = float(0.55 * np.mean(vals) + 0.45 * np.percentile(vals, 35))
    else:
        struct_sim = float(np.mean(tile_sims))

    hamming = float(np.count_nonzero(sig_a.dhash != sig_b.dhash))
    dhash_sim = max(0.0, min(1.0, 1.0 - hamming / float(sig_a.dhash.size)))

    base_sim = 0.48 * fg_iou + 0.40 * struct_sim + 0.12 * dhash_sim

    scroll_overlap = 0.0
    scroll_dy = 0
    is_scroll = False
    if check_scroll and fg_iou < 0.72 and sum_a > 25.0 and sum_b > 25.0:
        scroll_overlap, scroll_dy = _compute_scroll_overlap(sig_a, sig_b, valid_mask=valid)
        if scroll_overlap > fg_iou + 0.08 and scroll_overlap >= 0.15:
            is_scroll = True

    combined = max(base_sim, scroll_overlap) if is_scroll else base_sim
    return FrameComparison(
        fg_iou=float(fg_iou),
        ret_a_to_b=float(ret_a_to_b),
        ret_b_to_a=float(ret_b_to_a),
        disappeared_frac=float(disappeared_frac),
        added_frac=float(added_frac),
        struct_sim=float(struct_sim),
        dhash_sim=float(dhash_sim),
        scroll_overlap=float(scroll_overlap),
        scroll_dy=int(scroll_dy),
        is_scroll_continuation=is_scroll,
        combined_similarity=float(min(1.0, max(0.0, combined))),
    )
