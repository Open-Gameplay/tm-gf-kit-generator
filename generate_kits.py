"""Batch kit generation for all clubs in the TM data.

Usage:
    python generate_kits.py --clubs <clubs.json> --logos <logos_dir> \
        --template <template_kit.png> --out <out_dir> [--league <id>] [--specs <existing.json>]

Without --specs, palettes and specs are built automatically and specs.json is written.
With --specs, specs are loaded from the given JSON and only PNGs are re-rendered
(the flow after manual editing).
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from kits.linked import find_linked
from kits.palette import build_palette, load_clubs, profile_colors
from kits.regions import build_region_map
from kits.render import render_kit
from kits.spec import auto_specs, KIT_NAMES

OUT_SPECS = "specs.json"
KITS = {"main": "main.png", "white": "white.png", "black": "black.png",
        "reserve": "reserve.png", "gk1": "gk1.png", "gk2": "gk2.png"}


def club_record(club: dict) -> dict:
    colors = profile_colors(club)
    return {
        "id": str(club["id"]),
        "name": club["name"],
        "country": club.get("_country"),
        "league_id": club.get("_league_id"),
        "league": club.get("_league"),
        "colors": colors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clubs", required=True)
    ap.add_argument("--logos", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--league", default=None, help="filter by league id")
    ap.add_argument("--specs", default=None, help="existing specs.json to re-render")
    ap.add_argument("--limit", type=int, default=0, help="max clubs to process (debug)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    logos_dir = Path(args.logos)

    clubs = load_clubs(args.clubs)
    if args.league:
        clubs = [c for c in clubs if c.get("_league_id") == args.league]
    if args.limit:
        clubs = clubs[: args.limit]

    region_map = build_region_map(args.template)

    existing_specs = {}
    if args.specs:
        data = json.loads(Path(args.specs).read_text(encoding="utf-8"))
        existing_specs = {str(r["id"]): r for r in data} if isinstance(data, list) else {str(k): v for k, v in data.items()}
    else:
        # without --specs, keep clubs the editor marked as edited
        auto_path = out_dir / OUT_SPECS
        if auto_path.exists():
            saved = json.loads(auto_path.read_text(encoding="utf-8"))
            existing_specs = {str(r["id"]): r for r in saved if r.get("edited")}

    records = []
    for club in clubs:
        cid = str(club["id"])
        rec = club_record(club)

        if existing_specs and cid in existing_specs:
            rec.update(existing_specs[cid])
        else:
            rec["colors"] = profile_colors(club)
            logo = logos_dir / f"{cid}.png"
            rec["palette"] = build_palette(profile_colors(club), logo)
            rec.update(auto_specs(rec["palette"]))

        records.append(rec)
        print(f"{cid} {rec['name']} palette={len(rec['palette'])}")

    # linked clubs (academy / second team) share the root's kit spec
    linked_root = find_linked(clubs)
    by_id = {rec["id"]: rec for rec in records}
    for rec in records:
        root_id = linked_root.get(rec["id"], rec["id"])
        rec["linked_root"] = root_id
        if root_id != rec["id"] and root_id in by_id:
            root = by_id[root_id]
            rec["palette"] = root["palette"]
            for kit_name in KIT_NAMES:
                rec[kit_name] = root[kit_name]

    # render PNGs
    for rec in records:
        club_out = out_dir / rec["id"]
        club_out.mkdir(parents=True, exist_ok=True)
        for kit_name, filename in KITS.items():
            spec = rec.get(kit_name)
            if not spec:
                continue
            img = render_kit(region_map, rec["palette"], spec)
            img.save(club_out / filename)

    specs_path = out_dir / OUT_SPECS
    specs_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {len(records)} specs to {specs_path}")
    print(f"rendered PNGs to {out_dir}")


if __name__ == "__main__":
    main()