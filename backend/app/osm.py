"""Real safe-zone data from OpenStreetMap (Overpass API) - hospitals, schools, community centres,
town halls and places of worship near each district centre.

These are PUBLIC BUILDINGS that are commonly used as shelters, not an official list of designated
evacuation centres. Admins should confirm with the Disaster Management Centre (DMC) before relying on them.
Data (c) OpenStreetMap contributors, ODbL.
"""
import logging
import time

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .geo import haversine_km
from .models import Area, SafeZone

log = logging.getLogger("floodalert.osm")
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
RADIUS_M = 15000
# (osm tag, our kind, how many to keep per district)
WANTED = [("townhall", "shelter", 2), ("community_centre", "shelter", 4),
          ("hospital", "hospital", 4), ("school", "school", 6), ("place_of_worship", "temple", 3)]


def build_query(lat: float, lng: float) -> str:
    parts = [f'nwr(around:{RADIUS_M},{lat},{lng})[amenity={tag}][name]->.s{i}; .s{i} out center {keep * 4};'
             for i, (tag, _, keep) in enumerate(WANTED)]
    return "[out:json][timeout:60];\n" + "\n".join(parts)


def parse(elements: list[dict], lat: float, lng: float) -> list[dict]:
    """Overpass elements -> up to `keep` nearest places per kind, de-duplicated by name."""
    by_kind: dict[str, list[dict]] = {}
    kind_of = {tag: kind for tag, kind, _ in WANTED}
    seen = set()
    for el in elements:
        tags = el.get("tags") or {}
        kind = kind_of.get(tags.get("amenity"))
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        c = el if "lat" in el else el.get("center") or {}
        if not kind or not name or "lat" not in c:
            continue
        key = (name.lower(), round(c["lat"], 3), round(c["lon"], 3))
        if key in seen:
            continue
        seen.add(key)
        phone = (tags.get("phone") or tags.get("contact:phone") or "")[:30] or None
        by_kind.setdefault(kind, []).append({
            "name": name[:150], "kind": kind, "lat": c["lat"], "lng": c["lon"], "phone": phone,
            "d": haversine_km(lat, lng, c["lat"], c["lon"])})
    keep_for: dict[str, int] = {}
    for _, kind, keep in WANTED:
        keep_for[kind] = keep_for.get(kind, 0) + keep
    out = []
    for kind, items in by_kind.items():
        items.sort(key=lambda x: x["d"])
        out += items[:keep_for[kind]]
    return out


def fetch_places(lat: float, lng: float) -> list[dict] | None:
    for url in ENDPOINTS:
        try:
            r = httpx.post(url, data={"data": build_query(lat, lng)}, timeout=90,
                           headers={"User-Agent": "FloodAlertLK/1.0 (student project)"})
            r.raise_for_status()
            return parse(r.json().get("elements", []), lat, lng)
        except Exception as exc:
            log.warning("Overpass %s failed: %s", url, exc)
    return None


def import_area(db: Session, area: Area) -> int:
    places = fetch_places(area.lat, area.lng)
    if not places:
        return 0
    db.execute(delete(SafeZone).where(SafeZone.area_id == area.id))   # drops placeholders / earlier import
    for p in places:
        db.add(SafeZone(area_id=area.id, name=p["name"], kind=p["kind"], lat=p["lat"], lng=p["lng"],
                        phone=p["phone"], is_sample=False))
    db.commit()
    return len(places)


def import_missing(force: bool = False) -> None:
    """Import for every district that has no real zones yet (runs in a background thread at start-up)."""
    db = SessionLocal()
    try:
        for area in db.scalars(select(Area).order_by(Area.id)).all():
            has_real = db.scalar(select(SafeZone.id).where(SafeZone.area_id == area.id, SafeZone.is_sample.is_(False)).limit(1))
            if has_real and not force:
                continue
            n = import_area(db, area)
            log.info("OpenStreetMap: %s -> %d safe zones", area.name, n)
            time.sleep(2)   # be polite to the free Overpass servers
    except Exception:
        log.exception("OpenStreetMap import failed")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import_missing(force=True)
