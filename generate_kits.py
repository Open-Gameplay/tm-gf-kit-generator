"""Batch kit generation for clubs or national teams in the TM data.

Usage:
    # clubs (default)
    python generate_kits.py --clubs <clubs.json> --logos <logos_dir> \
        --template <template_kit.png> --out <out_dir> [--league <id>] [--specs <existing.json>]

    # national teams
    python generate_kits.py --teams <national_teams.json> --logos <emblems_dir> \
        --template <template_kit.png> --out <out_dir> [--specs <existing.json>]

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
from kits.palette import build_palette, load_clubs, load_national_teams, profile_colors
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


def national_team_record(team: dict) -> dict:
    colors = team.get("_colors_cleaned") or profile_colors(team)
    return {
        "id": str(team["id"]),
        "name": team["name"],
        "country": team.get("_country"),
        "league_id": team.get("_league_id"),
        "league": team.get("_league"),
        "colors": colors,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--clubs", help="path to full/clubs.json")
    group.add_argument("--teams", help="path to full/national_teams.json")
    ap.add_argument("--logos", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--league", default=None, help="filter by league id (clubs only)")
    ap.add_argument("--specs", default=None, help="existing specs.json to re-render")
    ap.add_argument("--limit", type=int, default=0, help="max items to process (debug)")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    logos_dir = Path(args.logos)
    is_national = args.teams is not None

    if is_national:
        items = load_national_teams(args.teams)
    else:
        items = load_clubs(args.clubs)
        if args.league:
            items = [c for c in items if c.get("_league_id") == args.league]
    if args.limit:
        items = items[: args.limit]

    region_map = build_region_map(args.template)

    existing_specs = {}
    if args.specs:
        data = json.loads(Path(args.specs).read_text(encoding="utf-8"))
        existing_specs = {str(r["id"]): r for r in data} if isinstance(data, list) else {str(k): v for k, v in data.items()}
    else:
        # without --specs, keep items the editor marked as edited
        auto_path = out_dir / OUT_SPECS
        if auto_path.exists():
            saved = json.loads(auto_path.read_text(encoding="utf-8"))
            existing_specs = {str(r["id"]): r for r in saved if r.get("edited")}

    records = []
    for item in items:
        cid = str(item["id"])
        rec = national_team_record(item) if is_national else club_record(item)

        if existing_specs and cid in existing_specs:
            rec.update(existing_specs[cid])
        else:
            if is_national:
                colors = item.get("_colors_cleaned") or []
                logo = logos_dir / f"{cid}.png"
                rec["palette"] = build_palette(colors if colors else None, logo)
            else:
                rec["colors"] = profile_colors(item)
                logo = logos_dir / f"{cid}.png"
                rec["palette"] = build_palette(profile_colors(item), logo)
            rec.update(auto_specs(rec["palette"]))

        records.append(rec)
        print(f"{cid} {rec['name']} palette={len(rec['palette'])}")

    # linked clubs (academy / second team) share the root's kit spec — clubs only
    if not is_national:
        linked_root = find_linked(items)
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