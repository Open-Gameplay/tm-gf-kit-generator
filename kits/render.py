"""Render a 1024x1024 kit PNG from a kit spec.

A spec assigns a palette index to each part (shirt/shorts/socks) and a shirt pattern.
The renderer paints the template regions, applies the pattern inside the shirt region,
and multiplies by the template's shading (knit texture).
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from .palette import hex_to_rgb, NEUTRAL_WHITE, NEUTRAL_BLACK
from .regions import RegionMap, REGION_SHIRT, REGION_BLACK

SIZE = 1024

# pattern name -> stripe period in pixels (halves has no period)
PATTERNS = ("plain", "stripes", "hoops", "sash", "halves")
PATTERN_PERIOD = {"stripes": 64, "hoops": 48, "sash": 80}


@lru_cache(maxsize=1)
def _region_map(template_path: str) -> RegionMap:
    from .regions import build_region_map

    return build_region_map(template_path)


def _resolve(palette: list[str], index, default) -> tuple[int, int, int]:
    if index is None:
        return default
    if 0 <= index < len(palette):
        try:
            return hex_to_rgb(palette[index])
        except (ValueError, IndexError):
            pass
    return default


def _shirt_pattern_mask(region_map: RegionMap, pattern: str, width: int, height: int) -> np.ndarray:
    """Boolean mask inside the shirt region where the pattern color replaces the shirt color."""
    shirt = region_map.mask(REGION_SHIRT)
    if pattern == "plain":
        return np.zeros((height, width), dtype=bool)

    # per-row connected runs of the shirt region; rel = x within the run
    x = np.arange(width)[None, :]
    padded = np.pad(shirt, ((0, 0), (1, 1)))
    starts = (padded[:, 1:] & ~padded[:, :-1])[:, :width]
    run_start = np.maximum.accumulate(np.where(starts, x, 0), axis=1)
    rel = np.where(shirt, x - run_start, 0)

    if pattern == "stripes":
        # absolute-x stripes: continuous vertical stripes across shoulders and torso columns
        period = PATTERN_PERIOD["stripes"]
        return shirt & (((x // period) % 2) == 0)

    if pattern == "halves":
        # run end (in original coords) via reversed accumulate
        shirt_rev = shirt[:, ::-1]
        padded_rev = np.pad(shirt_rev, ((0, 0), (1, 1)))
        starts_rev = (padded_rev[:, 1:] & ~padded_rev[:, :-1])[:, :width]
        rev_x = np.arange(width)[None, :]
        run_end_rev = np.maximum.accumulate(np.where(starts_rev, rev_x, 0), axis=1)
        run_end = width - 1 - run_end_rev[:, ::-1]
        run_width = np.maximum(1, run_end - run_start + 1)
        return shirt & ~(rel * 2 < run_width)

    if pattern == "hoops":
        period = PATTERN_PERIOD["hoops"]
        y = np.arange(height)[:, None]
        return shirt & (((y // period) % 2) == 0)

    if pattern == "sash":
        period = PATTERN_PERIOD["sash"]
        y = np.arange(height)[:, None]
        return shirt & ((((x - y) % period) < period // 2))

    return np.zeros((height, width), dtype=bool)


def render_kit(
    region_map: RegionMap,
    palette: list[str],
    spec: dict,
    template_path: str | None = None,
) -> Image.Image:
    """Render a kit image. spec keys: shirt, shorts, socks (palette indexes), pattern, pattern_color."""
    height = region_map.regions.shape[0]
    width = region_map.regions.shape[1]

    white = hex_to_rgb(NEUTRAL_WHITE)
    black = hex_to_rgb(NEUTRAL_BLACK)

    shirt_c = _resolve(palette, spec.get("shirt"), white)
    shorts_c = _resolve(palette, spec.get("shorts"), white)
    socks_c = _resolve(palette, spec.get("socks"), white)
    pattern_c = _resolve(palette, spec.get("pattern_color"), black)

    lut = np.array([shirt_c, shorts_c, socks_c, black], dtype=np.uint8)  # by region code
    base = lut[region_map.regions]  # (H, W, 3)

    pattern = spec.get("pattern", "plain")
    if pattern not in PATTERNS:
        pattern = "plain"
    if pattern != "plain":
        mask = _shirt_pattern_mask(region_map, pattern, width, height)
        base[mask] = pattern_c

    shaded = (base.astype(np.float32) * region_map.brightness[..., None]).astype(np.uint8)

    return Image.fromarray(shaded, "RGB")


def render_spec(region_map: RegionMap, palette: list[str], spec: dict) -> Image.Image:
    return render_kit(region_map, palette, spec)