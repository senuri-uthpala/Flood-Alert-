"""Initial data. Safe to run repeatedly (only inserts what is missing)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config
from .models import Area, SafeZone, User
from .security import hash_password

# name, district, lat, lng, terrain_risk (0-1).
# terrain_risk values are ILLUSTRATIVE estimates - replace with NBRO landslide-hazard / DMC flood-zone data.
DISTRICTS = [
    ("Colombo", 6.9271, 79.8612, 0.60), ("Gampaha", 7.0873, 79.9925, 0.55),
    ("Kalutara", 6.5854, 79.9607, 0.65), ("Kandy", 7.2906, 80.6337, 0.75),
    ("Matale", 7.4675, 80.6234, 0.65), ("Nuwara Eliya", 6.9497, 80.7891, 0.85),
    ("Galle", 6.0535, 80.2210, 0.50), ("Matara", 5.9549, 80.5550, 0.50),
    ("Hambantota", 6.1241, 81.1185, 0.30), ("Jaffna", 9.6615, 80.0255, 0.25),
    ("Kilinochchi", 9.3803, 80.3770, 0.30), ("Mannar", 8.9810, 79.9044, 0.25),
    ("Vavuniya", 8.7542, 80.4982, 0.30), ("Mullaitivu", 9.2671, 80.8142, 0.30),
    ("Batticaloa", 7.7102, 81.6924, 0.45), ("Ampara", 7.2975, 81.6820, 0.40),
    ("Trincomalee", 8.5874, 81.2152, 0.30), ("Kurunegala", 7.4863, 80.3647, 0.40),
    ("Puttalam", 8.0408, 79.8394, 0.35), ("Anuradhapura", 8.3114, 80.4037, 0.30),
    ("Polonnaruwa", 7.9403, 81.0188, 0.35), ("Badulla", 6.9934, 81.0550, 0.85),
    ("Monaragala", 6.8728, 81.3507, 0.45), ("Ratnapura", 6.6828, 80.3992, 0.85),
    ("Kegalle", 7.2513, 80.3464, 0.90),
]


def seed(db: Session) -> None:
    if not db.scalar(select(func.count()).select_from(Area)):
        for name, lat, lng, terrain in DISTRICTS:
            db.add(Area(name=name, district=name, lat=lat, lng=lng, terrain_risk=terrain))
        db.flush()
        # One placeholder safe zone per district so the evacuation feature works out of the box.
        # They are flagged is_sample - admins should replace them with official DMC shelter data.
        for area in (db.scalars(select(Area)).all() if config.OFFLINE_MODE else []):
            db.add(SafeZone(area_id=area.id, name=f"{area.name} District Secretariat (sample)",
                            kind="shelter", lat=area.lat + 0.01, lng=area.lng + 0.01, is_sample=True))
    if not db.scalar(select(User).where(User.email == config.ADMIN_EMAIL)):
        db.add(User(name="Administrator", email=config.ADMIN_EMAIL, role="admin",
                    password_hash=hash_password(config.ADMIN_PASSWORD)))
    db.commit()
