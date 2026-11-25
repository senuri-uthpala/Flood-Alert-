"""Core business logic shared by the API routes and the background scheduler."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import config, ml
from .models import Alert, Area, Report, Subscription, WeatherReading, utcnow
from .notifier import notify
from .risk import LEVEL_ORDER, alert_messages, calculate_risk, effective_rain, level_for
from .weather import fetch_rainfall_bulk, fetch_river_bulk

log = logging.getLogger("floodalert.services")
FORECASTS: dict[int, list[dict]] = {}   # area_id -> next 3 days; rebuilt on every refresh (in memory)


def project_forecast(area: Area, w, river: float | None, reports: int) -> list[dict]:
    """Rain and projected risk for each of the next 3 days, from the hourly series Open-Meteo returned.
    Day 0 = the next 24 hours. Risk uses the same formula as the live score (rain already fallen + still to come)."""
    h, now = w.series, w.now
    if not h:   # offline demo: spread the 24h forecast over 3 days
        h = [w.last_72h / 72] * 72 + [w.forecast_24h / 24] * 24 + [w.forecast_24h * 0.8 / 24] * 24 + [w.forecast_24h * 0.6 / 24] * 24
        now = 72
    today = datetime.now(ZoneInfo("Asia/Colombo")).date()
    out = []
    for k in range(3):
        i = now + 24 * k
        if i + 24 > len(h):
            break
        past72, ahead = sum(h[max(0, i - 72):i]), sum(h[i:i + 24])
        score, level = calculate_risk(effective_rain(past72, ahead), river, reports if k == 0 else 0, area.terrain_risk)
        out.append({"date": (today + timedelta(days=k)).isoformat(), "rain_mm": round(ahead, 1),
                    "risk_score": score, "risk_level": level})
    return out




def verified_report_count(db: Session, area_id: int, hours: int = 48) -> int:
    since = utcnow() - timedelta(hours=hours)
    return db.scalar(
        select(func.count()).select_from(Report).where(
            Report.area_id == area_id, Report.status == "verified", Report.created_at >= since
        )
    ) or 0


def dispatch_alert(db: Session, area: Area, level: str, manual: bool = False, custom: str | None = None) -> Alert:
    """Store one alert for the area and notify every subscriber in their own language."""
    msgs = {lang: custom for lang in ("si", "ta", "en")} if custom else alert_messages(level, area.name)
    alert = Alert(area_id=area.id, level=level, message_si=msgs["si"], message_ta=msgs["ta"],
                  message_en=msgs["en"], manual=manual)
    db.add(alert)
    subs = db.scalars(select(Subscription).where(Subscription.area_id == area.id)).all()
    seen = set()  # the same phone/email may be subscribed by several accounts - message it once
    for s in subs:
        if (s.channel, s.contact) in seen:
            continue
        seen.add((s.channel, s.contact))
        notify(s.channel, s.contact, msgs.get(s.language, msgs["en"]))
    alert.recipients = len(seen)
    return alert


def backfill_history(db: Session, area: Area, w) -> None:
    """First run for an area: rebuild the last 72h of readings (every 6h) from Open-Meteo's hourly data,
    so the chart is useful immediately instead of after days of 30-minute refreshes."""
    if not w.series or w.source != "open-meteo":
        return
    if (db.scalar(select(func.count()).select_from(WeatherReading).where(WeatherReading.area_id == area.id)) or 0) >= 3:
        return
    h, now = w.series, w.now
    for back in range(72, 0, -6):
        i = now - back
        if i < 24:
            continue
        r24, r72, fc = sum(h[i - 24:i]), sum(h[max(0, i - 72):i]), sum(h[i:i + 24])
        score, _ = calculate_risk(effective_rain(r72, fc), None, 0, area.terrain_risk)
        db.add(WeatherReading(area_id=area.id, rainfall_24h=round(r24, 1), rainfall_72h=round(r72, 1),
                              forecast_24h=round(fc, 1), risk_score=score, source="open-meteo",
                              recorded_at=utcnow() - timedelta(hours=back)))


def refresh_all(db: Session) -> list[dict]:
    """Fetch rainfall for every area, recompute risk, store readings, fire alerts on escalation."""
    areas = db.scalars(select(Area).order_by(Area.id)).all()
    coords = [(a.lat, a.lng) for a in areas]
    rainfall = fetch_rainfall_bulk(coords)
    rivers = fetch_river_bulk(coords)
    summary = []
    for area, w, river in zip(areas, rainfall, rivers):
        reports = verified_report_count(db, area.id)
        score, level = calculate_risk(effective_rain(w.last_72h, w.forecast_24h), river, reports, area.terrain_risk)
        prob = (ml.predict_probability(w.last_24h, w.last_72h, w.forecast_24h, area.terrain_risk, reports)
                if config.ENABLE_ML_DEMO else None)
        if config.USE_ML_BLEND and prob is not None:
            score = round(0.5 * score + 0.5 * prob * 100, 1)
            level = level_for(score)

        backfill_history(db, area, w)
        FORECASTS[area.id] = project_forecast(area, w, river, reports)
        previous = area.risk_level
        db.add(WeatherReading(area_id=area.id, rainfall_24h=w.last_24h, rainfall_72h=w.last_72h,
                              forecast_24h=w.forecast_24h, river_level=river, risk_score=score, source=w.source))
        area.risk_score, area.risk_level, area.ml_probability, area.updated_at = score, level, prob, utcnow()

        if LEVEL_ORDER[level] >= 1 and LEVEL_ORDER[level] > LEVEL_ORDER[previous]:
            dispatch_alert(db, area, level)
        summary.append({"area": area.name, "rain_72h": w.last_72h, "forecast_24h": w.forecast_24h,
                        "score": score, "level": level, "source": w.source})

    db.execute(delete(WeatherReading).where(WeatherReading.recorded_at < utcnow() - timedelta(days=30)))
    db.commit()
    log.info("Refreshed %d areas", len(summary))
    return summary


def maybe_auto_verify(db: Session, report: Report) -> bool:
    """Mark a report verified when enough DIFFERENT users reported the same thing in the same area."""
    since = utcnow() - timedelta(hours=6)
    distinct = db.scalar(
        select(func.count(func.distinct(Report.user_id))).where(
            Report.area_id == report.area_id, Report.type == report.type,
            Report.status != "rejected", Report.created_at >= since, Report.user_id.is_not(None),
        )
    ) or 0
    if distinct >= config.AUTO_VERIFY_THRESHOLD:
        pending = db.scalars(select(Report).where(
            Report.area_id == report.area_id, Report.type == report.type,
            Report.status == "pending", Report.created_at >= since)).all()
        for r in pending:
            r.status, r.auto_verified = "verified", True
        return True
    return False
