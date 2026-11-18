from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# A light regex instead of EmailStr keeps the dependency list small.
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=150)
    password: str = Field(min_length=8, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    language: str = Field(default="si", pattern="^(si|ta|en)$")


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: int
    name: str
    email: str
    phone: str | None
    role: str
    language: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AreaOut(ORM):
    id: int
    name: str
    district: str
    lat: float
    lng: float
    terrain_risk: float
    risk_score: float
    risk_level: str
    ml_probability: float | None
    updated_at: datetime | None


class ReadingOut(ORM):
    rainfall_24h: float
    rainfall_72h: float
    forecast_24h: float
    risk_score: float
    source: str
    recorded_at: datetime


class SafeZoneIn(BaseModel):
    area_id: int
    name: str = Field(min_length=2, max_length=150)
    kind: str = Field(default="shelter", pattern="^(shelter|hospital|school|temple)$")
    lat: float = Field(ge=5.5, le=10.2)
    lng: float = Field(ge=79.3, le=82.1)
    capacity: int | None = Field(default=None, ge=0)
    phone: str | None = Field(default=None, max_length=30)


class SafeZoneOut(ORM):
    id: int
    area_id: int
    name: str
    kind: str
    lat: float
    lng: float
    capacity: int | None
    phone: str | None
    is_sample: bool
    distance_km: float | None = None


class ReportOut(ORM):
    id: int
    area_id: int
    area_name: str | None = None
    type: str
    description: str | None
    lat: float | None
    lng: float | None
    photo_url: str | None = None
    status: str
    auto_verified: bool
    created_at: datetime


class SubscriptionIn(BaseModel):
    area_id: int
    channel: str = Field(pattern="^(sms|email|push)$")
    contact: str = Field(min_length=3, max_length=150)
    language: str = Field(default="si", pattern="^(si|ta|en)$")


class SubscriptionOut(ORM):
    id: int
    area_id: int
    channel: str
    contact: str
    language: str


class AlertOut(ORM):
    id: int
    area_id: int
    area_name: str | None = None
    level: str
    message_si: str
    message_ta: str
    message_en: str
    manual: bool
    recipients: int
    sent_at: datetime


class BroadcastIn(BaseModel):
    area_id: int
    level: str = Field(pattern="^(Medium|High|Critical)$")
    message: str | None = Field(default=None, max_length=300)  # custom text (sent as-is in all languages)
