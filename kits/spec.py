"""Kit spec schema and automatic assignment heuristics.

A kit spec is a dict with per-part palette indexes:
    {"shirt": idx, "shorts": idx, "socks": idx, "pattern": name, "pattern_color": idx|None}
A club spec groups six of them plus the palette:
    {"id": ..., "name": ..., "palette": [...],
     "main": {...}, "white": {...}, "black": {...}, "reserve": {...}, "gk1": {...}, "gk2": {...}}

Field kits: main (club colors), white, black, reserve.
GK kits: gk1, gk2 — two bright solid kits; the match-day logic picks one per game
(see pick_match_kits).
"""

from __future__ import annotations

import numpy as np

from .palette import hex_to_rgb, NEUTRAL_WHITE, NEUTRAL_BLACK

PATTERN_PLAIN = "plain"

# kit names in order
KIT_NAMES = ("main", "white", "black", "reserve", "gk1", "gk2")
OUTFIELD_KITS = ("main", "white", "black", "reserve")
GK_KITS = ("gk1", "gk2")

# bright standard GK kit colors
GK_BRIGHT_POOL = ["#32CD32", "#FF8C00", "#FFD700", "#00BFFF", "#EE82EE"]

# minimum shirt contrast (Euclidean RGB) to consider two kits non-clashing
CLASH_THRESHOLD = 60.0


def _rgb(hex_color: str) -> tuple[int, int, int]:
    try:
        return hex_to_rgb(hex_color)
    except (ValueError, IndexError):
        return (255, 255, 255)


def luminance(hex_color: str) -> float:
    r, g, b = (c / 255.0 for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_dark(hex_color: str) -> bool:
    return luminance(hex_color) < 0.35


def saturation(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return (max(r, g, b) - min(r, g, b)) / 255.0


def is_neutral(hex_color: str) -> bool:
    """Gray-ish (white/black/silver): shorts/socks may use it."""
    r, g, b = _rgb(hex_color)
    return (max(r, g, b) - min(r, g, b)) <= 26


def contrast(a: str, b: str) -> float:
    """Euclidean RGB distance, used as a coarse distinguishability proxy."""
    return float(np.sqrt(sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b)))))


def _neutral_for(hex_color: str) -> str:
    return NEUTRAL_BLACK if not is_dark(hex_color) else NEUTRAL_WHITE


def _pick_far(targets: list[str], candidates: list[str], prefer_light: bool = False) -> str:
    """Best candidate: maximizes min contrast to all targets; prefer light on ties."""
    best = candidates[0]
    best_score = -1.0
    for c in candidates:
        min_c = min(contrast(c, t) for t in targets)
        score = min_c
        if prefer_light:
            score += luminance(c) * 80.0
        if score > best_score:
            best_score = score
            best = c
    return best


def _solid(shirt: str) -> dict:
    """Solid kit: all parts the same color, no pattern."""
    return {
        "shirt": shirt,
        "shorts": shirt,
        "socks": shirt,
        "pattern": PATTERN_PLAIN,
        "pattern_color": None,
    }


def auto_specs(palette: list[str]) -> dict:
    """Assign the six kits from the club palette.

    Rules:
    - main: primary shirt; shorts/socks = secondary if it is neutral, else shirt color;
    - white/black: solid neutral kits;
    - reserve: a chromatic palette color distinct from main/white/black, else a neutral;
    - gk1/gk2: two bright solid colors from the standard GK pool, most distinct from the
      club's field kits.
    """
    p = list(palette or [NEUTRAL_WHITE, NEUTRAL_BLACK])

    def ensure(color: str) -> int:
        if color not in p:
            p.append(color)
        return p.index(color)

    def idx(color: str) -> int:
        return ensure(color)

    def kit(shirt: str, shorts: str | None = None) -> dict:
        shorts = shorts or shirt
        return {
            "shirt": idx(shirt),
            "shorts": idx(shorts),
            "socks": idx(shorts),
            "pattern": PATTERN_PLAIN,
            "pattern_color": None,
        }

    primary = p[0]
    secondary = p[1] if len(p) > 1 else _neutral_for(primary)

    # ---- main: club colors ----
    main_shorts = secondary if is_neutral(secondary) else primary
    main = kit(primary, main_shorts)

    # ---- white / black: solid neutrals ----
    white = NEUTRAL_WHITE
    black = NEUTRAL_BLACK
    white_kit = kit(white)
    black_kit = kit(black)

    # ---- reserve: chromatic color distinct from the neutral + main kits ----
    others = [main["shirt"], white, black]
    reserve_candidates = [c for c in p if c not in others and saturation(c) > 0.10]
    if not reserve_candidates:
        reserve_candidates = [c for c in p if c not in others]
    if not reserve_candidates:
        reserve_candidates = [_neutral_for(primary)]
    reserve_shirt = _pick_far([primary, white, black], reserve_candidates)
    # shorts/socks: neutral secondary or shirt color, per the field-kit rule
    reserve_shorts = secondary if is_neutral(secondary) else reserve_shirt
    reserve = kit(reserve_shirt, reserve_shorts)

    # ---- gk1/gk2: two bright solid colors most distinct from the field kits ----
    field_shirts = [primary, white, black, reserve_shirt]
    gk_pool = list(dict.fromkeys([*GK_BRIGHT_POOL, *p]))
    gk1_color = _pick_far(field_shirts, gk_pool, prefer_light=True)
    remaining = [c for c in gk_pool if c != gk1_color]
    gk2_color = _pick_far(field_shirts, remaining, prefer_light=True)
    gk1 = _solid(idx(gk1_color))
    gk2 = _solid(idx(gk2_color))

    return {
        "palette": p,
        "main": main,
        "white": white_kit,
        "black": black_kit,
        "reserve": reserve,
        "gk1": gk1,
        "gk2": gk2,
    }


def kit_shirt_color(spec: dict, kit_name: str) -> str:
    """Hex shirt color of a kit in a club spec."""
    kit = spec.get(kit_name) or {}
    shirt_idx = kit.get("shirt")
    palette = spec.get("palette") or []
    if shirt_idx is None or not 0 <= shirt_idx < len(palette):
        return NEUTRAL_WHITE
    return palette[shirt_idx]


def pick_match_kits(a: dict, b: dict, manual: dict | None = None) -> dict:
    """Choose kits for a match, by convention with manual override.

    Convention: team A (home) wears main; team B (away) also wears main unless its main
    clashes with A's chosen shirt, in which case B switches to its best contrasting field
    kit. If even then the pair clashes, A also switches. `manual` overrides either side:
        {"a": kit_name, "b": kit_name}.

    GKs are chosen per match: each team's GK (gk1/gk2) is the one maximizing min contrast
    to both chosen field shirts.

    Returns {"a_out", "b_out", "a_gk", "b_gk"} kit names.
    """
    manual = manual or {}

    a_out = manual.get("a") or "main"
    if a_out not in OUTFIELD_KITS:
        a_out = "main"

    a_shirt = kit_shirt_color(a, a_out)

    if manual.get("b"):
        b_out = manual["b"]
        if b_out not in OUTFIELD_KITS:
            b_out = "main"
    else:
        b_main = "main"
        if contrast(a_shirt, kit_shirt_color(b, b_main)) >= CLASH_THRESHOLD:
            b_out = b_main
        else:
            candidates = [k for k in OUTFIELD_KITS if k != "main"]
            b_out = _pick_far([a_shirt], [kit_shirt_color(b, k) for k in candidates], prefer_light=False)
            b_out = _kit_by_shirt(b, b_out)

    b_shirt = kit_shirt_color(b, b_out)

    # if the pair still clashes, let A switch too
    if not manual.get("a") and contrast(a_shirt, b_shirt) < CLASH_THRESHOLD:
        candidates = [k for k in OUTFIELD_KITS if k != "main"]
        a_out = _kit_by_shirt(a, _pick_far([b_shirt], [kit_shirt_color(a, k) for k in candidates], prefer_light=False))
        a_shirt = kit_shirt_color(a, a_out)

    # GKs: contrast with both field shirts
    def pick_gk(club: dict) -> str:
        pool = [kit_shirt_color(club, k) for k in GK_KITS]
        best_color = _pick_far([a_shirt, b_shirt], pool, prefer_light=True)
        for k in GK_KITS:
            if kit_shirt_color(club, k) == best_color:
                return k
        return GK_KITS[0]

    return {"a_out": a_out, "b_out": b_out, "a_gk": pick_gk(a), "b_gk": pick_gk(b)}


def _kit_by_shirt(club: dict, shirt_color: str) -> str:
    for k in OUTFIELD_KITS:
        if kit_shirt_color(club, k) == shirt_color:
            return k
    return OUTFIELD_KITS[0]


def merge_club_spec(base: dict, overrides: dict | None) -> dict:
    """Deep-merge editor overrides onto a club spec (overrides win, keys preserved)."""
    if not overrides:
        return base
    result = dict(base)
    for kit in KIT_NAMES:
        src = base.get(kit, {})
        ov = overrides.get(kit, {})
        merged = dict(src)
        for key, value in ov.items():
            merged[key] = value
        result[kit] = merged
    return result