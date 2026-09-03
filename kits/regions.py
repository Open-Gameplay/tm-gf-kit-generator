"""Region masks + shading map derived from the game's kit template.

The template (`template_kit.png`, 1024x1024) encodes a region map and a shading map:
  - shirt  region: y 0..418   (color1 marker #D3D3D3)  -> painted with the shirt color
  - shorts region: y 419..582 (color2 marker #FFFFFF)  -> painted with the shorts color
  - socks  region: y 583..766 (color2 marker #FFFFFF)  -> painted with the socks color
  - seams / background: pixels with a dark green channel (#002A00 and darker shades)
    stay black; pure black stays black; bottom quarter (y>766) is unused.

The green channel of the non-black pixels carries fabric shading: a knit texture on the
shirt and dense knit dots on shorts/socks. Render = region_color * (G / base_g), where
base_g is the green value of the region's marker (shirt=211, shorts/socks=255).
"""

from pathlib import Path

import numpy as np
from PIL import Image

SHIRT_Y_END = 419
SHORTS_Y_END = 583

REGION_SHIRT = 0
REGION_SHORTS = 1
REGION_SOCKS = 2
REGION_BLACK = 3

# green-channel value of each region's marker color; shading is relative to it.
BASE_G = {REGION_SHIRT: 211.0, REGION_SHORTS: 255.0, REGION_SOCKS: 255.0}


class RegionMap:
    def __init__(self, regions: np.ndarray, brightness: np.ndarray):
        # regions: (H, W) uint8, REGION_* codes
        # brightness: (H, W) float32 in [0, 1]
        self.regions = regions
        self.brightness = brightness

    def mask(self, region: int) -> np.ndarray:
        return self.regions == region


def build_region_map(template_path: str | Path) -> RegionMap:
    img = Image.open(template_path).convert("RGB")
    if img.size != (1024, 1024):
        raise ValueError(f"expected 1024x1024 template, got {img.size}")
    arr = np.asarray(img, dtype=np.uint8)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    h, w = arr.shape[:2]
    ys = np.arange(h)[:, None]

    is_black = (g < 128) & (r < 40) & (b < 40)

    regions = np.full((h, w), REGION_BLACK, dtype=np.uint8)
    regions[~is_black & (ys < SHIRT_Y_END)] = REGION_SHIRT
    regions[~is_black & (ys >= SHIRT_Y_END) & (ys < SHORTS_Y_END)] = REGION_SHORTS
    regions[~is_black & (ys >= SHORTS_Y_END)] = REGION_SOCKS

    brightness = np.zeros((h, w), dtype=np.float32)
    for region, base in BASE_G.items():
        mask = regions == region
        bm = g[mask] / base
        brightness[mask] = np.clip(bm, 0.0, 1.0)

    return RegionMap(regions, brightness)


def save_mask_view(region_map: RegionMap, out_path: str | Path) -> None:
    """Debug view: shirt=red, shorts=green, socks=blue, black=black."""
    rgb = np.zeros((*region_map.regions.shape, 3), dtype=np.uint8)
    rgb[region_map.regions == REGION_SHIRT] = (200, 40, 40)
    rgb[region_map.regions == REGION_SHORTS] = (40, 200, 40)
    rgb[region_map.regions == REGION_SOCKS] = (40, 40, 200)
    Image.fromarray(rgb).save(out_path)