from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..geo import haversine_km
from ..models import Alert, Area, Report, SafeZone, User, WeatherReading
from ..schemas import AlertOut, AreaOut, ReadingOut, SafeZoneIn, SafeZoneOut
from ..security import require_admin

router = APIRouter(prefix="/api", tags=["areas"])


@router.get("/areas", response_model=list[AreaOut])
def list_areas(db: Session = Depends(get_db)):
    return db.scalars(select(Area).order_by(Area.risk_score.desc())).all()


@router.get("/areas/{area_id}", response_model=AreaOut)
def get_area(area_id: int, db: Session = Depends(get_db)):
    area = db.get(Area, area_id)
    if not area:
        raise HTTPException(404, "Area not found")
    return area


@router.get("/areas/{area_id}/history", response_model=list[ReadingOut])
def area_history(area_id: int, hours: int = Query(72, ge=1, le=720), db: Session = Depends(get_db)):
    """Readings oldest -> newest (ready for charts)."""
    from datetime import timedelta

    from ..models import utcnow
    rows = db.scalars(
        select(WeatherReading).where(WeatherReading.area_id == area_id,
                                     WeatherReading.recorded_at >= utcnow() - timedelta(hours=hours))
        .order_by(WeatherReading.recorded_at)
    ).all()
    return rows


@router.get("/areas/{area_id}/safe-zones", response_model=list[SafeZoneOut])
def area_safe_zones(area_id: int, db: Session = Depends(get_db)):
    area = db.get(Area, area_id)
    zones = db.scalars(select(SafeZone).where(SafeZone.area_id == area_id)).all()
    rank = {"shelter": 0, "school": 1, "hospital": 2, "temple": 3}
    if area:
        zones.sort(key=lambda z: (rank.get(z.kind, 9), haversine_km(area.lat, area.lng, z.lat, z.lng)))
    return zones


@router.get("/safe-zones/nearest", response_model=list[SafeZoneOut])
def nearest_safe_zones(lat: float = Query(ge=5.5, le=10.2), lng: float = Query(ge=79.3, le=82.1),
                       limit: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)):
    """Closest safe zones to a position (straight-line distance; the map links to routing)."""
    zones = db.scalars(select(SafeZone)).all()
    ranked = sorted(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng))[:limit]
    out = []
    for z in ranked:
        item = SafeZoneOut.model_validate(z)
        item.distance_km = round(haversine_km(lat, lng, z.lat, z.lng), 1)
        out.append(item)
    return out


@router.post("/safe-zones", response_model=SafeZoneOut, status_code=201)
def add_safe_zone(body: SafeZoneIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if not db.get(Area, body.area_id):
        raise HTTPException(404, "Area not found")
    zone = SafeZone(**body.model_dump(), is_sample=False)
    db.add(zone)
    db.commit()
    return zone


@router.delete("/safe-zones/{zone_id}", status_code=204)
def delete_safe_zone(zone_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    zone = db.get(SafeZone, zone_id)
    if not zone:
        raise HTTPException(404, "Safe zone not found")
    db.delete(zone)
    db.commit()


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(limit: int = Query(30, ge=1, le=100), since_id: int = Query(0, ge=0),
                db: Session = Depends(get_db)):
    """`since_id` lets the web app poll cheaply for new alerts."""
    rows = db.execute(
        select(Alert, Area.name).join(Area, Area.id == Alert.area_id)
        .where(Alert.id > since_id).order_by(Alert.id.desc()).limit(limit)
    ).all()
    return [AlertOut.model_validate(a).model_copy(update={"area_name": n}) for a, n in rows]


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    levels = dict(db.execute(select(Area.risk_level, func.count()).group_by(Area.risk_level)).all())
    return {
        "areas": sum(levels.values()),
        "by_level": {k: levels.get(k, 0) for k in ("Low", "Medium", "High", "Critical")},
        "verified_reports": db.scalar(select(func.count()).select_from(Report).where(Report.status == "verified")),
        "last_update": db.scalar(select(func.max(Area.updated_at))),
    }
