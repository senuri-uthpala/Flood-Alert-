# 🌧️ FloodAlert LK

Community flood & landslide early-warning system for Sri Lanka. It combines live rainfall data and forecasts with
verified community reports, shows a risk map for all 25 districts, and alerts subscribers (SMS / e-mail / push /
browser) in Sinhala, Tamil or English.

> Advisory tool. It does **not** replace official warnings from the Disaster Management Centre (hotline **117**).

## Features
- **Risk map** of 25 districts (Low / Medium / High / Critical) with rainfall, 24 h forecast and 72 h charts
- **Live data** from Open-Meteo (free, no API key), refreshed automatically every 30 minutes
- **Early warning**: forecast rain counts toward the score; alerts fire only when a level *rises*
- **Accounts** (JWT) with citizen and admin roles
- **Community reports** with GPS + photo, rate limiting, admin moderation and auto-verification (3 different users)
- **Alerts** via SMS (Twilio), e-mail (SMTP), push (Firebase) and in-browser notifications, in the subscriber's language
- **Safe zones**: nearest shelters from your GPS position with OpenStreetMap directions
- **Trilingual UI** (සිංහල / தமிழ் / English), mobile-first, **installable PWA with offline mode**
- **Optional ML** flood-probability model (RandomForest) next to the rule-based score
- **Admin tools**: moderation queue, manual alerts, manual refresh, statistics
- 39 automated backend tests + 23-step browser end-to-end test

## Quick start (no database setup needed)

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows   (Linux/Mac: source venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open <http://localhost:8000> · API docs: <http://localhost:8000/docs>

First login: `admin@floodalert.lk` / `ChangeMe123!` (**change it** with `ADMIN_PASSWORD`, see `.env.example`).
Without internet use `FLOODALERT_OFFLINE=1` (mock rainfall, clearly labelled in the UI).

## Run with Docker + PostgreSQL
```bash
cp .env.example .env        # then edit passwords
docker compose up --build
```
(The Docker setup was written carefully but has not been run in the environment where this project was generated - if it
fails, tell me the error.)

## Project structure
```
backend/
  app/
    main.py            app + lifespan (tables, seed, scheduler)
    config.py          environment-based settings
    models.py          SQLAlchemy models        database.py   engine/session
    security.py        PBKDF2 + JWT + role guards
    risk.py            risk formula + si/ta/en alert text
    weather.py         Open-Meteo client (bulk) + mock fallback
    services.py        refresh job, alert dispatch, auto-verify
    notifier.py        Twilio / SMTP / FCM senders
    ml.py              optional RandomForest predictor
    scheduler.py       APScheduler job
    seed.py            25 districts, sample safe zones, admin user
    routers/           auth · areas(+alerts, safe zones) · reports · subscriptions · admin
  ml/train.py          train the model (synthetic demo or your CSV)
  tests/               pytest suite + e2e/browser_e2e.py (Playwright)
frontend/              index.html · css/ · js/app.js · js/i18n.js · sw.js · manifest.json
docs/                  ER_DIAGRAM · ARCHITECTURE · USER_STORIES · TEST_CASES
Dockerfile · docker-compose.yml · .env.example
```

## API overview (full interactive docs at `/docs`)
| Method & path | Who | Purpose |
|---|---|---|
| `POST /api/auth/register`, `/login`, `GET /me` | public / user | accounts |
| `GET /api/areas`, `/areas/{id}`, `/areas/{id}/history` | public | risk map + chart data |
| `GET /api/areas/{id}/safe-zones`, `/safe-zones/nearest?lat&lng` | public | evacuation help |
| `GET /api/alerts?since_id=` | public | alert feed (polled by the app) |
| `POST /api/reports` (multipart) | user | report with photo |
| `GET /api/reports`, `/reports/mine` | public (verified only) / user | |
| `POST /api/reports/{id}/verify\|reject` | admin | moderation |
| `POST/GET/DELETE /api/subscriptions` | user | manage own alert subscriptions |
| `POST /api/admin/refresh`, `/broadcast`, `/reload-model`; `GET /api/admin/stats` | admin | operations |
| `POST/DELETE /api/safe-zones` | admin | official shelter data |

## Enabling real alerts
Set the matching variables from `.env.example`: **Twilio** for SMS, **SMTP** for e-mail, a **Firebase** service account
for push. Missing credentials never break anything - the alert is just logged.

## Training the ML model
```bash
cd backend
python ml/train.py                    # DEMO model on SYNTHETIC data (pipeline demo only)
python ml/train.py --csv history.csv  # real model: rain_24h,rain_72h,forecast_24h,terrain,verified_reports,flooded
```
The model shipped in `backend/models/` is the synthetic demo model and is labelled "demo" in the UI.

## Limitations - please read
See `docs/ARCHITECTURE.md`. In short: no live river-gauge feed exists, terrain values and safe zones are placeholders
until you add official NBRO/DMC data, areas are district circles not polygons, the shipped ML model is synthetic,
SMS/e-mail contacts are not OTP-verified, and the Sinhala/Tamil wording needs native review. Run a **single** server
worker (the scheduler lives in the app process).

## Ideas for next steps
Real district polygons (GeoJSON / PostGIS) · gauge data from the Irrigation Department · OTP verification for SMS ·
Web Push (VAPID) instead of polling · evacuation routing with OSRM · historical event replay mode (replay a past major flood with archived rainfall).

## Data sources (real data)
| What | Source |
|---|---|
| Rainfall (24h, 72h, 24h forecast) | Open-Meteo Forecast API, per district centre |
| River flow index | Open-Meteo Flood API (GloFAS modelled discharge): current flow vs the river's own 60-day average |
| Safe zones | OpenStreetMap via Overpass: town halls, community centres, schools, hospitals, places of worship near each district. Imported in the background on first start (about a minute); re-import with `python -m app.osm` |
| Risk score | Our rule-based formula (see `app/risk.py`) - not an official forecast |

Not real / still estimates: the per-district `terrain_risk` values in `app/seed.py` (replace with NBRO hazard-zone data) and the optional ML model (synthetic training data, disabled unless `ENABLE_ML_DEMO=1`). Safe zones are public buildings, not an official list of designated evacuation centres - confirm with the DMC (117).
