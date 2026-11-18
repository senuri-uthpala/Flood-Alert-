from app.geo import haversine_km
from app.risk import alert_messages, calculate_risk, effective_rain, level_for


def test_zero_inputs_is_low():
    assert calculate_risk(0, None, 0, 0) == (0.0, "Low")


def test_extreme_inputs_is_critical():
    score, level = calculate_risk(400, 1.0, 5, 1.0)
    assert score == 100.0 and level == "Critical"


def test_score_increases_with_rain():
    low, _ = calculate_risk(50, None, 0, 0.5)
    high, _ = calculate_risk(200, None, 0, 0.5)
    assert high > low


def test_verified_reports_raise_score():
    base, _ = calculate_risk(100, None, 0, 0.5)
    with_reports, _ = calculate_risk(100, None, 3, 0.5)
    assert with_reports > base


def test_inputs_are_clamped():
    assert calculate_risk(10_000, 5.0, 99, 9.0)[0] == 100.0
    assert calculate_risk(-10, -1.0, -3, -1.0)[0] == 0.0


def test_level_boundaries():
    assert level_for(24.9) == "Low"
    assert level_for(25) == "Medium"
    assert level_for(50) == "High"
    assert level_for(75) == "Critical"


def test_forecast_counts_half():
    assert effective_rain(100, 40) == 120


def test_alert_messages_in_three_languages():
    m = alert_messages("High", "Kandy")
    assert set(m) == {"si", "ta", "en"}
    assert all("Kandy" in text for text in m.values())


def test_haversine_colombo_kandy():
    d = haversine_km(6.9271, 79.8612, 7.2906, 80.6337)
    assert 85 < d < 100  # ~94 km straight line
