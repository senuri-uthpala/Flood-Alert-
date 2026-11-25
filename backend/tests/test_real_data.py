"""Real-data helpers, tested with canned API responses (no network)."""
from app import osm
from app.weather import river_index


def test_river_index_flat_river_is_zero():
    assert river_index([100.0] * 63) == 0.0


def test_river_index_flood_wave_is_high():
    series = [50.0] * 60 + [50.0, 400.0, 300.0]   # 8x the average coming
    assert river_index(series) == 1.0


def test_river_index_moderate_rise():
    series = [100.0] * 60 + [100.0, 150.0, 200.0]   # 2x average -> 0.5
    assert river_index(series) == 0.5


def test_river_index_no_data_returns_none():
    assert river_index([None] * 63) is None
    assert river_index([]) is None


def test_osm_parse_maps_kinds_dedupes_and_prefers_english():
    els = [
        {"type": "node", "lat": 7.30, "lon": 80.64, "tags": {"amenity": "hospital", "name": "ආයුර්වේද", "name:en": "Kandy Hospital", "phone": "+94812222261"}},
        {"type": "way", "center": {"lat": 7.31, "lon": 80.65}, "tags": {"amenity": "school", "name": "Trinity College"}},
        {"type": "way", "center": {"lat": 7.31, "lon": 80.65}, "tags": {"amenity": "school", "name": "Trinity College"}},  # duplicate
        {"type": "node", "lat": 7.29, "lon": 80.63, "tags": {"amenity": "community_centre", "name": "Town Hall Hall"}},
        {"type": "node", "lat": 7.29, "lon": 80.63, "tags": {"amenity": "pharmacy", "name": "ignored"}},
        {"type": "node", "lat": 7.29, "lon": 80.63, "tags": {"amenity": "school"}},  # no name -> skipped
    ]
    out = osm.parse(els, 7.29, 80.63)
    names = sorted(p["name"] for p in out)
    assert names == ["Kandy Hospital", "Town Hall Hall", "Trinity College"]
    kinds = {p["name"]: p["kind"] for p in out}
    assert kinds == {"Kandy Hospital": "hospital", "Trinity College": "school", "Town Hall Hall": "shelter"}


def test_osm_parse_keeps_only_nearest_per_kind():
    els = [{"type": "node", "lat": 7.0 + i * 0.01, "lon": 80.0, "tags": {"amenity": "hospital", "name": f"H{i}"}} for i in range(10)]
    out = osm.parse(els, 7.0, 80.0)
    assert len(out) == 4 and [p["name"] for p in out] == ["H0", "H1", "H2", "H3"]


def test_osm_query_has_all_kinds():
    q = osm.build_query(7.29, 80.63)
    for tag in ("hospital", "school", "community_centre", "townhall", "place_of_worship"):
        assert f"[amenity={tag}]" in q


def test_forecast_endpoint_has_three_days_per_district(client, admin_headers):
    assert client.post("/api/admin/refresh", headers=admin_headers).status_code == 200
    data = client.get("/api/forecast").json()
    assert len(data) == 25
    for days in data.values():
        assert len(days) == 3
        assert [d["date"] for d in days] == sorted(d["date"] for d in days)
        for d in days:
            assert d["risk_level"] in ("Low", "Medium", "High", "Critical")
            assert 0 <= d["risk_score"] <= 100 and d["rain_mm"] >= 0


def test_project_forecast_uses_real_series():
    from app import models, services, weather
    area = models.Area(name="T", district="T", lat=7, lng=80, terrain_risk=0.5)
    dry = weather.Rainfall(0, 0, 0, "open-meteo", [0.0] * 150, 72)
    wet = weather.Rainfall(0, 0, 0, "open-meteo", [0.0] * 72 + [0.0] * 24 + [10.0] * 24 + [0.0] * 30, 72)
    d, w_ = services.project_forecast(area, dry, None, 0), services.project_forecast(area, wet, None, 0)
    assert [x["rain_mm"] for x in d] == [0, 0, 0]
    assert [x["rain_mm"] for x in w_] == [0.0, 240.0, 0.0]          # the wet day is day 2
    assert w_[1]["risk_score"] > d[1]["risk_score"]
