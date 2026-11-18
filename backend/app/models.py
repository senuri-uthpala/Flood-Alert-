from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(10), default="citizen")  # citizen | admin
    language: Mapped[str] = mapped_column(String(2), default="si")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Area(Base):
    __tablename__ = "areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    district: Mapped[str] = mapped_column(String(80))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    terrain_risk: Mapped[float] = mapped_column(Float, default=0.5)  # 0-1 slope/low-lying/landslide proneness
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(10), default="Low")
    ml_probability: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    readings: Mapped[list["WeatherReading"]] = relationship(back_populates="area", cascade="all, delete-orphan")
    safe_zones: Mapped[list["SafeZone"]] = relationship(back_populates="area", cascade="all, delete-orphan")


class WeatherReading(Base):
    __tablename__ = "weather_readings"
    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    rainfall_24h: Mapped[float] = mapped_column(Float)
    rainfall_72h: Mapped[float] = mapped_column(Float)
    forecast_24h: Mapped[float] = mapped_column(Float, default=0)
    river_level: Mapped[float | None] = mapped_column(Float)  # 0-1 of flood stage, if a gauge feed exists
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    area: Mapped[Area] = relationship(back_populates="readings")


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    type: Mapped[str] = mapped_column(String(10))  # flood | landslide
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    photo_path: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | verified | rejected
    auto_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User | None] = relationship()
    area: Mapped[Area] = relationship()


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "area_id", "contact", "channel"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    contact: Mapped[str] = mapped_column(String(150))  # phone, email or FCM token
    channel: Mapped[str] = mapped_column(String(10))  # sms | email | push
    language: Mapped[str] = mapped_column(String(2), default="si")


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    level: Mapped[str] = mapped_column(String(10))
    message_si: Mapped[str] = mapped_column(Text)
    message_ta: Mapped[str] = mapped_column(Text)
    message_en: Mapped[str] = mapped_column(Text)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    area: Mapped[Area] = relationship()


class SafeZone(Base):
    __tablename__ = "safe_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("areas.id"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(20), default="shelter")  # shelter | hospital | school | temple
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    capacity: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(String(30))
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)

    area: Mapped[Area] = relationship(back_populates="safe_zones")
