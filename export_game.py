"""Export rendered kits into the game's images_teams layout.

Game layout (from teamdata.cpp / team.cpp):
    databases/default/images_teams/<league_id>/<club_id>_kit_main.png    (club colors)
    databases/default/images_teams/<league_id>/<club_id>_kit_white.png
    databases/default/images_teams/<league_id>/<club_id>_kit_black.png
    databases/default/images_teams/<league_id>/<club_id>_kit_reserve.png
    databases/default/images_teams/<league_id>/<club_id>_kit_gk1.png
    databases/default/images_teams/<league_id>/<club_id>_kit_gk2.png

The game currently loads only _kit_01/_kit_02 + a shared goalie_kit.png; wiring the
full kit set (and per-match GK selection) is a game-side change (see NOTES.md).

Usage:
    python export_game.py --specs <out/all/specs.json> --kits <out/all> \
        --out <GameplayFootball/data/databases/default/images_teams>
"""

import argparse
import json
import shutil
from pathlib import Path

KIT_FILES = {"main": "_kit_main.png", "white": "_kit_white.png", "black": "_kit_black.png",
             "reserve": "_kit_reserve.png", "gk1": "_kit_gk1.png", "gk2": "_kit_gk2.png"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--kits", required=True, help="dir with <club_id>/home.png|away.png|gk.png")
    ap.add_argument("--out", required=True, help="images_teams dir in the game's data")
    args = ap.parse_args()

    specs = json.loads(Path(args.specs).read_text(encoding="utf-8"))
    kits_root = Path(args.kits)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    count = 0
    for rec in specs:
        league = rec.get("league_id") or "unknown"
        club_dir = out_root / str(league)
        club_dir.mkdir(parents=True, exist_ok=True)
        for kit, filename in KIT_FILES.items():
            src = kits_root / str(rec["id"]) / f"{kit}.png"
            if src.exists():
                shutil.copy2(src, club_dir / f"{rec['id']}{filename}")
        count += 1

    print(f"exported {count} clubs to {out_root}")


if __name__ == "__main__":
    main()