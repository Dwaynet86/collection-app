"""Offline place search over bundled data: ~34,000 cities (GeoNames, CC BY 4.0) plus country names.

Everything is local; nothing is sent to an outside service. Data: app/data/places.json
(rebuilt with scripts/build_geodata.py).
"""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "places.json"
MAX_QUERY = 60


def _norm(text: str) -> str:
    """Lowercase and strip accents so 'Sao Paulo' finds 'São Paulo'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold().strip()


@lru_cache(maxsize=1)
def _entries() -> list[tuple]:
    """(search keys, label, lat, lon, population, kind) for every city and country."""
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    countries, admins = data["country_names"], data["admins"]
    out = []
    for name, lat, lon, pop in data["countries"]:
        out.append(((_norm(name),), name, lat, lon, pop * 10, "country"))   # countries rank above same-named towns
    for name, cc, admin, lat, lon, pop, *alts in data["cities"]:
        country = countries.get(cc, cc)
        region = admins.get(cc, {}).get(admin)
        label = ", ".join(p for p in (name, region, country) if p)
        keys = tuple(dict.fromkeys(_norm(n) for n in (name, *alts)))
        out.append((keys, label, lat, lon, pop, "city"))
    return out


def search(query: str, limit: int = 8) -> list[dict]:
    """Best matches for 'lisbon', 'sao paulo', 'springfield, illinois' (prefix and word-start matching)."""
    parts = [_norm(p) for p in query[:MAX_QUERY].split(",")]
    q, extra = parts[0], [p for p in parts[1:] if p]
    if len(q) < 2:
        return []
    scored = []
    for keys, label, lat, lon, pop, kind in _entries():
        best = None
        for key in keys:
            if key.startswith(q):
                rank = 0
            elif f" {q}" in key:
                rank = 1
            else:
                continue
            best = rank if best is None else min(best, rank)
        if best is None:
            continue
        if extra:
            norm_label = _norm(label)
            if not all(e in norm_label for e in extra):
                continue
        scored.append((best, -pop, label, lat, lon, kind))
    scored.sort()
    seen, results = set(), []
    for _, _, label, lat, lon, kind in scored:
        if label in seen:
            continue
        seen.add(label)
        results.append({"label": label, "lat": lat, "lon": lon, "kind": kind})
        if len(results) == limit:
            break
    return results
