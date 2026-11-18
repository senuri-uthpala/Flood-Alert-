"""Risk scoring + alert wording.

Rule-based score (0-100):
    40% rainfall (72h observed + half of the next-24h forecast)
  + 30% river level   (falls back to the rainfall signal when no gauge feed exists)
  + 20% verified community reports (last 48h)
  + 10% terrain risk  (slope / low-lying / landslide-prone, 0-1 per area)

Each input is normalised to 0-1 first. The weights are a starting point — calibrate them with
real flood event data (see ml/train.py).
"""

MAX_RAIN = 300.0   # mm treated as "extreme" over the window
MAX_REPORTS = 5    # verified reports that saturate the community signal
WEIGHTS = {"rain": 0.4, "river": 0.3, "reports": 0.2, "terrain": 0.1}
LEVELS = [(75, "Critical"), (50, "High"), (25, "Medium"), (0, "Low")]
LEVEL_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def effective_rain(rain_72h: float, forecast_24h: float) -> float:
    return rain_72h + 0.5 * forecast_24h


def level_for(score: float) -> str:
    for threshold, label in LEVELS:
        if score >= threshold:
            return label
    return "Low"


def calculate_risk(rainfall: float, river_level: float | None, verified_reports: int,
                   terrain_risk: float) -> tuple[float, str]:
    rain = _clamp(rainfall / MAX_RAIN)
    river = _clamp(river_level) if river_level is not None else rain
    reports = _clamp(verified_reports / MAX_REPORTS)
    score = 100 * (
        WEIGHTS["rain"] * rain
        + WEIGHTS["river"] * river
        + WEIGHTS["reports"] * reports
        + WEIGHTS["terrain"] * _clamp(terrain_risk)
    )
    score = round(score, 1)
    return score, level_for(score)


# NOTE: Sinhala and Tamil wording should be reviewed by native speakers / DMC before real use.
MESSAGES = {
    "si": {
        "Medium": "අවවාදයයි: {area} ප්‍රදේශයේ ගංවතුර අවදානම මධ්‍යස්ථයි. ප්‍රවේශම් වන්න.",
        "High": "අවවාදයයි: {area} ප්‍රදේශයේ ගංවතුර/නායයාමේ අවදානම ඉහළයි. සූදානම් වන්න.",
        "Critical": "හදිසි: {area} ප්‍රදේශයේ දැඩි අවදානමක්! ආරක්ෂිත ස්ථානයකට යන්න.",
    },
    "ta": {
        "Medium": "எச்சரிக்கை: {area} பகுதியில் வெள்ள அபாயம் மிதமாக உள்ளது. கவனமாக இருங்கள்.",
        "High": "எச்சரிக்கை: {area} பகுதியில் வெள்ளம்/மண்சரிவு அபாயம் அதிகமாக உள்ளது. தயாராக இருங்கள்.",
        "Critical": "அவசரம்: {area} பகுதியில் கடுமையான அபாயம்! உடனடியாக பாதுகாப்பான இடத்திற்குச் செல்லுங்கள்.",
    },
    "en": {
        "Medium": "Advisory: Moderate flood risk in {area}. Stay alert.",
        "High": "Warning: High flood/landslide risk in {area}. Be prepared to move.",
        "Critical": "EMERGENCY: Critical risk in {area}. Move to a safe zone now.",
    },
}


def alert_messages(level: str, area: str) -> dict[str, str]:
    return {lang: MESSAGES[lang][level].format(area=area) for lang in MESSAGES}
