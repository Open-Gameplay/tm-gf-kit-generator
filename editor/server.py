"""Web editor: review and adjust kit specs club by club.

Shows the club's logo and palette, lets the user assign palette colors to parts of the
kit (shirt/shorts/socks) and pick a shirt pattern for each kit (home/away/gk), with a
live preview. Changes are saved back to specs.json; PNGs are re-rendered on demand and
by generate_kits.py --specs.

Usage:
    python editor/server.py --specs <out/specs.json> --logos <logos_dir> \
        --template <template_kit.png> [--port 9001]
"""

import argparse
import io
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kits.regions import build_region_map
from kits.render import render_kit
from kits.render import PATTERNS
from kits.spec import KIT_NAMES

HOST = "127.0.0.1"

STATIC_DIR = Path(__file__).parent


class KitEditorServer:
    def __init__(self, specs_path: Path, logos_dir: Path, template_path: Path):
        self.specs_path = specs_path
        self.logos_dir = logos_dir
        self.region_map = build_region_map(template_path)
        self.specs = json.loads(specs_path.read_text(encoding="utf-8"))
        self.by_id = {str(s["id"]): s for s in self.specs}
        self._preview_cache = {}

    def group_members(self, club_id: str) -> list[dict]:
        """All clubs in the linked group of `club_id` (including itself)."""
        root_id = (self.by_id.get(club_id) or {}).get("linked_root") or club_id
        return [s for s in self.specs if (s.get("linked_root") or s["id"]) == root_id]

    def save_specs(self):
        self.specs_path.write_text(
            json.dumps(self.specs, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def find_club(self, club_id: str) -> dict | None:
        return self.by_id.get(club_id)

    def preview(self, club_id: str, kit: str, refresh: bool = False):
        club = self.by_id.get(club_id)
        if not club or kit not in KIT_NAMES:
            return None
        cache_key = (club_id, kit, json.dumps(club[kit], sort_keys=True))
        if refresh or cache_key not in self._preview_cache:
            img = render_kit(self.region_map, club["palette"], club[kit])
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self._preview_cache[cache_key] = buf.getvalue()
        return self._preview_cache[cache_key]


class Handler(BaseHTTPRequestHandler):
    server: KitEditorServer

    def _send(self, code: int, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, (STATIC_DIR / "viewer.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/clubs":
            body = json.dumps(self.server.specs, ensure_ascii=False).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        elif path == "/api/patterns":
            self._send(200, json.dumps(list(PATTERNS)).encode(), "application/json")
        elif path.startswith("/api/preview/"):
            parts = path.split("/")
            if len(parts) >= 5:
                club_id, kit = parts[3], parts[4]
                data = self.server.preview(club_id, kit)
                if data:
                    self._send(200, data, "image/png")
                    return
            self._send(404, b"not found", "text/plain")
        elif path.startswith("/api/logo/"):
            club_id = path.split("/")[-1]
            logo = self.server.logos_dir / f"{club_id}.png"
            if logo.exists():
                self._send(200, logo.read_bytes(), "image/png")
            else:
                self._send(404, b"no logo", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        m = re.fullmatch(r"/api/spec/(.+)", path)
        if not m:
            self._send(404, b"not found", "text/plain")
            return
        club_id = m.group(1)
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        club = self.server.find_club(club_id)
        if not club:
            self._send(404, b"no club", "text/plain")
            return
        for kit in KIT_NAMES:
            if kit in payload:
                new = payload[kit]
                club[kit] = {k: new.get(k, club[kit].get(k)) for k in club[kit]}
        club["edited"] = True
        # propagate to the linked group (academy / second team)
        for member in self.server.group_members(club_id):
            member["palette"] = club["palette"]
            for kit in KIT_NAMES:
                member[kit] = dict(club[kit])
            member["edited"] = True
        self.server.save_specs()
        for member in self.server.group_members(club_id):
            for kit in KIT_NAMES:
                self.server.preview(member["id"], kit, refresh=True)
        self._send(200, json.dumps(club, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", required=True)
    ap.add_argument("--logos", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--port", type=int, default=9001)
    args = ap.parse_args()

    server = KitEditorServer(Path(args.specs), Path(args.logos), Path(args.template))
    httpd = ThreadingHTTPServer((HOST, args.port), Handler)
    httpd.specs = server.specs
    httpd.by_id = server.by_id
    httpd.find_club = server.find_club
    httpd.group_members = server.group_members
    httpd.save_specs = server.save_specs
    httpd.preview = server.preview
    httpd.logos_dir = server.logos_dir
    print(f"kit editor: http://{HOST}:{args.port}  ({len(server.specs)} clubs)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()