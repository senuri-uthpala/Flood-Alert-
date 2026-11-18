"""Train the optional flood-probability model (RandomForest).

Usage (from the backend/ folder):
    python ml/train.py                       # DEMO model on synthetic data
    python ml/train.py --csv history.csv     # real model from historical records

CSV columns (header required):
    rain_24h, rain_72h, forecast_24h, terrain, verified_reports, flooded
`flooded` is 1 if a flood/landslide was recorded in that area within ~24h after the reading, else 0.
Good sources for real labels: Disaster Management Centre (DMC) incident reports, Irrigation Dept. gauge
records, NBRO landslide records, joined with historical rainfall from Open-Meteo's archive API.

IMPORTANT: without --csv the model is trained on SYNTHETIC data generated from a hand-written formula.
It only demonstrates the pipeline - it has NO real predictive value. Say so in your report/demo.
"""
import argparse
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

FEATURES = ["rain_24h", "rain_72h", "forecast_24h", "terrain", "verified_reports"]
OUT = Path(__file__).resolve().parent.parent / "models" / "flood_rf.joblib"


def synthetic(n: int = 6000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r24 = rng.gamma(1.5, 25, n)
    r72 = r24 + rng.gamma(2.0, 45, n)
    fc = rng.gamma(1.5, 20, n)
    terrain = rng.uniform(0.2, 0.95, n)
    reports = rng.poisson(0.6, n)
    z = 0.02 * r24 + 0.012 * r72 + 0.015 * fc + 2.5 * terrain + 0.4 * reports - 6.0
    flooded = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    return pd.DataFrame(dict(rain_24h=r24, rain_72h=r72, forecast_24h=fc, terrain=terrain,
                             verified_reports=reports, flooded=flooded))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="historical dataset (see module docstring)")
    args = ap.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv)
        missing = set(FEATURES + ["flooded"]) - set(df.columns)
        if missing:
            sys.exit(f"CSV is missing columns: {sorted(missing)}")
        print(f"Training on {len(df)} real records")
    else:
        df = synthetic()
        print("WARNING: no --csv given -> training a DEMO model on SYNTHETIC data")

    X_train, X_test, y_train, y_test = train_test_split(
        df[FEATURES], df["flooded"], test_size=0.25, random_state=1, stratify=df["flooded"])
    model = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=10,
                                   class_weight="balanced", random_state=1, n_jobs=-1)
    model.fit(X_train.values, y_train.values)

    proba = model.predict_proba(X_test.values)[:, 1]
    print(classification_report(y_test, proba > 0.5, digits=3))
    print(f"ROC-AUC: {roc_auc_score(y_test, proba):.3f}")
    print("Feature importance:", dict(zip(FEATURES, model.feature_importances_.round(3))))

    OUT.parent.mkdir(exist_ok=True)
    joblib.dump(model, OUT)
    print(f"Saved -> {OUT}")


if __name__ == "__main__":
    main()
