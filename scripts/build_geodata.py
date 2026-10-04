"""Rebuild the bundled map data. Only needed if you want to refresh it; the results are committed.

    pip install geonamescache
    curl -O https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson
    python scripts/build_geodata.py ne_50m_admin_0_countries.geojson

Writes:
  app/static/geo/countries.json  country outlines (Natural Earth, public domain), simplified
  app/data/places.json           cities (GeoNames, CC BY 4.0) and country label points, for place search
"""
import json
import sys
import unicodedata
from pathlib import Path

import geonamescache

ROOT = Path(__file__).resolve().parent.parent
MIN_CITY_POPULATION = 1000
DECIMALS = 2   # ~1 km; plenty for a country-and-city-level map

# GeoNames "admin1" codes that aren't already readable names.
ADMINS = {
    "CA": {"01": "Alberta", "02": "British Columbia", "03": "Manitoba", "04": "New Brunswick",
           "05": "Newfoundland and Labrador", "07": "Nova Scotia", "08": "Ontario",
           "09": "Prince Edward Island", "10": "Quebec", "11": "Saskatchewan", "12": "Yukon",
           "13": "Northwest Territories", "14": "Nunavut"},
    "GB": {"ENG": "England", "SCT": "Scotland", "WLS": "Wales", "NIR": "Northern Ireland"},
    "AU": {"01": "Australian Capital Territory", "02": "New South Wales", "03": "Northern Territory",
           "04": "Queensland", "05": "South Australia", "06": "Tasmania", "07": "Victoria",
           "08": "Western Australia"},
}


def ascii_key(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold().strip()


def good_alternate(alt: str, name: str) -> bool:
    """Latin-script alternative spellings only; skips airport codes and vowel-less transliterations."""
    key = ascii_key(alt)
    return (bool(alt) and len(alt) <= 40 and not alt.isupper() and key != ascii_key(name)
            and alt == alt.encode("latin-1", "ignore").decode("latin-1")
            and any(v in key for v in "aeiouy"))


def simplify_ring(ring):
    out = []
    for x, y in ring:
        pt = [round(x, DECIMALS), round(y, DECIMALS)]
        if not out or pt != out[-1]:
            out.append(pt)
    return out if len(out) >= 4 else None


def simplify_geometry(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    result = []
    for poly in polys:
        rings = [r for r in (simplify_ring(r) for r in poly) if r]
        if rings:
            result.append(rings)
    if not result:
        return None
    return {"type": "MultiPolygon", "coordinates": result}


def main(source: str) -> None:
    data = json.loads(Path(source).read_text())
    features, countries = [], []
    for f in data["features"]:
        props = f["properties"]
        name = props["NAME"]
        geom = simplify_geometry(f["geometry"])
        if geom:
            features.append({"type": "Feature", "properties": {"n": name}, "geometry": geom})
        countries.append([name, round(props["LABEL_Y"], 3), round(props["LABEL_X"], 3), int(props["POP_EST"])])
    out = ROOT / "app/static/geo/countries.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    print(out, out.stat().st_size // 1024, "KB,", len(features), "countries")

    gc = geonamescache.GeonamesCache()
    admins = {"US": {code: s["name"] for code, s in gc.get_us_states().items()}, **ADMINS}
    cities = []
    for c in gc.get_cities().values():
        if c["population"] < MIN_CITY_POPULATION:
            continue
        name = c["name"]
        # extra Latin-script names (Munich/München, Lisbon/Lisboa) so either spelling is found
        base = ascii_key(name)[:3]
        # prefer spellings close to the English name (Munich -> München) over distant transliterations
        alts = sorted({a for a in c["alternatenames"] if good_alternate(a, name)},
                      key=lambda a: (not ascii_key(a).startswith(base), abs(len(a) - len(name)), a))[:6]
        cities.append([name, c["countrycode"], c["admin1code"], round(c["latitude"], 4),
                       round(c["longitude"], 4), c["population"], *alts])
    cities.sort(key=lambda r: -r[5])
    payload = {
        "countries": countries,
        "country_names": {code: v["name"] for code, v in gc.get_countries().items()},
        "admins": admins,
        "cities": cities,
    }
    out = ROOT / "app/data/places.json"
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(out, out.stat().st_size // 1024, "KB,", len(cities), "cities")


if __name__ == "__main__":
    main(sys.argv[1])
