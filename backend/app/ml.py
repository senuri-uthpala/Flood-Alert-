"""Optional ML layer. Loads a RandomForest trained by ml/train.py and returns a flood probability.

Features (in this order): rain_24h, rain_72h, forecast_24h, terrain_risk, verified_reports
If no model file exists the functions return None and the rule-based score is used alone.
"""
import logging

from .config import MODEL_PATH

log = logging.getLogger("floodalert.ml")
_model = None
_tried = False


def _load():
    global _model, _tried
    if _tried:
        return _model
    _tried = True
    if MODEL_PATH.exists():
        try:
            import joblib
            _model = joblib.load(MODEL_PATH)
            log.info("Loaded ML model from %s", MODEL_PATH)
        except Exception as exc:
            log.warning("Could not load ML model: %s", exc)
    return _model


def reload_model():
    global _tried
    _tried = False
    return _load() is not None


def predict_probability(rain_24h: float, rain_72h: float, forecast_24h: float,
                        terrain: float, verified_reports: int) -> float | None:
    model = _load()
    if model is None:
        return None
    try:
        return round(float(model.predict_proba([[rain_24h, rain_72h, forecast_24h, terrain, verified_reports]])[0][1]), 3)
    except Exception as exc:
        log.warning("ML prediction failed: %s", exc)
        return None
