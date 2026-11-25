"""Rainfall data from Open-Meteo (free, no API key), fetched for all areas in ONE request.

If the call fails (no internet / API down / FLOODALERT_OFFLINE=1) we fall back to mock values and the
reading is tagged source="mock" so it is never mistaken for real data.
"""
import logging
import random
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from .config import OFFLINE_MODE

log = logging.getLogger("floodalert.weather")
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TZ = ZoneInfo("Asia/Colombo")


@dataclass
class Rainfall:
    last_24h: float
    last_72h: float
    forecast_24h: float
    source: str
    series: list[float] | None = None   # hourly mm, 3 days back .. 24h ahead, index `now` marks the present
    now: int = 0


def _mock() -> Rainfall:
    r24 = round(random.uniform(0, 120), 1)
    return Rainfall(r24, round(r24 + random.uniform(0, 180), 1), round(random.uniform(0, 80), 1), "mock")


def fetch_rainfall_bulk(coords: list[tuple[float, float]]) -> list[Rainfall]:
    """coords = [(lat, lng), ...] -> one Rainfall per coordinate, same order."""
    if OFFLINE_MODE or not coords:
        return [_mock() for _ in coords]
    try:
        resp = httpx.get(
            OPEN_METEO_URL,
            params={
                "latitude": ",".join(str(c[0]) for c in coords),
                "longitude": ",".join(str(c[1]) for c in coords),
                "hourly": "precipitation",
                "past_days": 3,
                "forecast_days": 4,
                "timezone": "Asia/Colombo",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):  # single location -> dict, several -> list
            data = [data]
        now_idx = 72 + datetime.now(TZ).hour  # hourly series starts 3 days ago at 00:00
        out = []
        for loc in data:
            h = [v or 0 for v in loc["hourly"]["precipitation"]]
            past72 = h[now_idx - 72:now_idx]
            out.append(Rainfall(
                round(sum(past72[-24:]), 1),
                round(sum(past72), 1),
                round(sum(h[now_idx:now_idx + 24]), 1),
                "open-meteo", h, now_idx,
            ))
        return out
    except Exception as exc:
        log.warning("Open-Meteo unavailable (%s) - using mock rainfall", exc)
        return [_mock() for _ in coords]


FLOOD_API_URL = "https://flood-api.open-meteo.com/v1/flood"


def fetch_river_bulk(coords: list[tuple[float, float]]) -> list[float | None]:
    """River-flow index 0-1 per coordinate from Open-Meteo's Flood API (GloFAS modelled river discharge).

    index = how far the current/next-3-days discharge is ABOVE this river's own 60-day average:
    at or below average -> 0, three times the average (or more) -> 1. None if no data (then rain is used).
    """
    if OFFLINE_MODE or not coords:
        return [None for _ in coords]
    try:
        resp = httpx.get(FLOOD_API_URL, params={
            "latitude": ",".join(str(c[0]) for c in coords), "longitude": ",".join(str(c[1]) for c in coords),
            "daily": "river_discharge", "past_days": 60, "forecast_days": 3}, timeout=25)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            data = [data]
        return [river_index(loc.get("daily", {}).get("river_discharge") or []) for loc in data]
    except Exception as exc:
        log.warning("Open-Meteo flood API unavailable (%s) - river level not used", exc)
        return [None for _ in coords]


def river_index(series: list, past_days: int = 60) -> float | None:
    past = [v for v in series[:past_days] if v is not None]
    ahead = [v for v in series[past_days - 1:past_days + 3] if v is not None]
    if len(past) < 20 or not ahead:
        return None
    mean = sum(past) / len(past)
    if mean <= 0:
        return None
    return round(min(1.0, max(0.0, (max(ahead) / mean - 1) / 2)), 3)
