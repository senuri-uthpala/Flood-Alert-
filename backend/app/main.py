import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

import threading

from . import config, osm, scheduler
from .database import Base, SessionLocal, engine
from .routers import admin, areas, auth, reports, subscriptions
from .seed import seed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    if not config.DISABLE_SCHEDULER:
        scheduler.start()
        if not config.OFFLINE_MODE:   # real safe zones from OpenStreetMap, once per district
            threading.Thread(target=osm.import_missing, daemon=True).start()
    yield
    scheduler.stop()


app = FastAPI(title="FloodAlert LK API", version="1.0.0", lifespan=lifespan,
              description="Community flood & landslide early warning system for Sri Lanka")

for module in (auth, areas, reports, subscriptions, admin):
    app.include_router(module.router)


@app.middleware("http")
async def security_headers(request, call_next):
    response: Response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


# user-uploaded photos, then the web app (mounted last so /api/* wins)
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
if config.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
