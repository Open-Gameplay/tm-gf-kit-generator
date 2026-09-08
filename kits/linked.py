"""Linked clubs: a club, its academy and second team share one kit spec.

Detection is name-based (same as the ratings generator): a club whose normalized name is
<parent> + reserve suffix (II, B, U19, Castilla, Mestalla, ...) links to the parent within
the same country. Editing any member propagates to the whole group.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

# longer first so "atleticob" is tried before "b"
RESERVE_SUFFIXES = [
    "nextgen", "mestalla", "castilla", "atleticob", "atletico", "atletic", "filial",
    "primavera", "sub23", "sub21", "sub20", "sub19", "sub18", "sub17",
    "u23", "u21", "u20", "u19", "u18", "u17",
    "under23", "under21", "under20", "under19", "under18", "under17",
    "iii", "ii", "b", "c", "2", "3",
]
SHORT_SUFFIXES = ("b", "c", "2", "3")
# suffixes that unambiguously mark a youth/reserve team (not "b"/"c"/"2"/"3",
# which collide with "FC"/"BC"/"AC" tails of main-club names)
RESERVE_PARENT_SUFFIXES = [s for s in RESERVE_SUFFIXES if s not in SHORT_SUFFIXES]


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _is_reserve_name(norm: str) -> bool:
    return any(norm.endswith(s) and len(norm) > len(s) + 3 for s in RESERVE_PARENT_SUFFIXES)


def _parent_of(norm_name: str, norm2id: dict, cid: str) -> str | None:
    for suf in sorted(RESERVE_SUFFIXES, key=len, reverse=True):
        if norm_name.endswith(suf) and len(norm_name) > len(suf) + 3:
            base = norm_name[: -len(suf)]
            if base in norm2id and norm2id[base] != cid:
                return norm2id[base]
            # Parent candidates are main clubs only (never another youth team),
            # preferring the closest name: exact/prefix match first, then substring
            # (e.g. "acffiorentina" for base "fiorentina"). Shortest wins.
            def _pick(match):
                cands = [(n2, c2) for n2, c2 in norm2id.items()
                         if c2 != cid and not _is_reserve_name(n2)
                         and norm_name not in n2 and match(n2)]
                if cands:
                    return min(cands, key=lambda t: len(t[0]))[1]
                return None
            parent = _pick(lambda n2: n2.startswith(base))
            if parent is None:
                parent = _pick(lambda n2: base in n2)
            if parent:
                return parent
            break
    return None


def find_linked(clubs: list[dict]) -> dict:
    """club_id -> root club_id (self for roots). Children inherit the root's kit spec."""
    norm2id_by_country = defaultdict(dict)
    for club in clubs:
        country = club.get("_country") or ""
        norm2id_by_country[country][normalize(club["name"])] = str(club["id"])

    parent: dict[str, str] = {}
    for club in clubs:
        cid = str(club["id"])
        n = normalize(club["name"])
        country = club.get("_country") or ""
        p = _parent_of(n, norm2id_by_country[country], cid)
        if p:
            parent[cid] = p

    def root_of(cid: str, seen: set | None = None) -> str:
        seen = seen or set()
        while cid in parent and parent[cid] not in seen:
            seen.add(cid)
            cid = parent[cid]
        return cid

    return {str(c["id"]): root_of(str(c["id"])) for c in clubs}