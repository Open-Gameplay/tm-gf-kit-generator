"""Color resolution for clubs: profile colors first, logo-derived colors second, neutrals last.

The club palette is an ordered list; kit specs reference colors by index into it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

NEUTRAL_WHITE = "#FFFFFF"
NEUTRAL_BLACK = "#000000"

# max colors extracted from a logo
MAX_LOGO_COLORS = 4
# min RGB distance between two palette colors before they merge
DEDUP_DISTANCE = 45.0


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02X%02X%02X" % rgb


def _distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return float(np.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))))


def _saturation(rgb: tuple[int, int, int]) -> float:
    mx, mn = max(rgb), min(rgb)
    return (mx - mn) / 255.0 if mx else 0.0


def _luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255.0 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def extract_logo_palette(logo_path: str | Path, max_colors: int = MAX_LOGO_COLORS) -> list[tuple[int, int, int]]:
    """Dominant opaque colors of a logo, most representative first."""
    with Image.open(logo_path) as img:
        img = img.convert("RGBA").resize((48, 48), Image.LANCZOS)
        data = np.asarray(img, dtype=np.uint8)
        alpha = data[..., 3]
        opaque = data[alpha >= 200]
        if opaque.size == 0:
            return []

    # quantize to bin grid, then histogram
    bins = 24
    quantized = (opaque[..., :3].astype(np.uint16) // bins) * bins
    unique, counts = np.unique(quantized.reshape(-1, 3), axis=0, return_counts=True)
    total = unique.shape[0] if unique.size else 0
    if total == 0:
        return []

    weights = counts / counts.sum()
    # representative color = bin center
    rgb_list = [tuple(int(c + bins // 2) for c in u) for u in unique]

    scored = sorted(
        zip(rgb_list, weights),
        key=lambda item: (item[1] * (0.4 + _saturation(item[0]))),
        reverse=True,
    )

    result: list[tuple[int, int, int]] = []
    for rgb, weight in scored:
        # drop near-gray colors (unhelpful for kits) but keep if nothing else
        if _saturation(rgb) < 0.08 and len(result) > 0:
            continue
        if all(_distance(rgb, existing) > DEDUP_DISTANCE for existing in result):
            result.append(rgb)
        if len(result) >= max_colors:
            break
    return result


def build_palette(
    profile_colors: list[str] | None,
    logo_path: str | Path | None,
    max_colors: int = 8,
) -> list[str]:
    """Ordered palette: profile colors, then logo-derived, then neutrals (always present)."""
    palette: list[tuple[int, int, int]] = []

    def add(rgb: tuple[int, int, int]) -> None:
        if all(_distance(rgb, e) > DEDUP_DISTANCE for e in palette):
            palette.append(rgb)

    for hex_color in profile_colors or []:
        try:
            add(hex_to_rgb(hex_color))
        except (ValueError, IndexError):
            continue

    if logo_path and Path(logo_path).exists():
        for rgb in extract_logo_palette(logo_path):
            add(rgb)

    # cap profile/logo colors; neutrals below are always kept
    palette = palette[:max(max_colors - 2, 0)]

    # neutrals as fallback roles (dedup only against exact duplicates)
    for neutral in (NEUTRAL_WHITE, NEUTRAL_BLACK):
        rgb = hex_to_rgb(neutral)
        if rgb not in palette:
            palette.append(rgb)

    return [rgb_to_hex(rgb) for rgb in palette]


def load_clubs(clubs_json: str | Path) -> list[dict]:
    """Flatten full/clubs.json (countries -> leagues -> clubs) into a club list.

    Each club gets `_country`, `_league_id`, `_league` keys from its parents.
    """
    with open(clubs_json, encoding="utf-8") as f:
        countries = json.load(f)
    clubs = []
    for country in countries:
        for league in country.get("leagues", []):
            for club in league.get("clubs", []):
                club["_country"] = country.get("name")
                club["_league_id"] = league.get("id")
                club["_league"] = league.get("name")
                clubs.append(club)
    return clubs


def profile_colors(club: dict) -> list[str]:
    raw = club.get("colors")
    if not raw:
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, str) and c.strip().startswith("#")]
    return [c for c in str(raw).split() if c.strip().startswith("#")]