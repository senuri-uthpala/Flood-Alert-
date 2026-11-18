"""Central configuration. Everything can be overridden with environment variables."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'floodalert.db'}")
FRONTEND_DIR = Path(os.getenv("FRONTEND_DIR", ROOT_DIR / "frontend"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", BASE_DIR / "models" / "flood_rf.joblib"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret() -> str:
    """JWT signing key: env var, else a random key persisted next to the DB (never committed)."""
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(48)
    key_file.write_text(key)
    return key


SECRET_KEY = _load_secret()
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "24"))

# First admin account (created on startup if it doesn't exist). CHANGE THESE.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@floodalert.lk")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")

REFRESH_MINUTES = int(os.getenv("REFRESH_MINUTES", "30"))
DISABLE_SCHEDULER = os.getenv("DISABLE_SCHEDULER", "0") == "1"
OFFLINE_MODE = os.getenv("FLOODALERT_OFFLINE", "0") == "1"  # force mock rainfall (demo / tests)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
REPORTS_PER_HOUR = int(os.getenv("REPORTS_PER_HOUR", "5"))
AUTO_VERIFY_THRESHOLD = int(os.getenv("AUTO_VERIFY_THRESHOLD", "3"))  # distinct users, same area+type, 6h
ENABLE_ML_DEMO = os.getenv("ENABLE_ML_DEMO", "0") == "1"  # off by default: the model is trained on synthetic data
USE_ML_BLEND = os.getenv("USE_ML_BLEND", "0") == "1"  # blend ML probability into the risk score

# Notification providers (all optional; without them alerts are logged to the console)
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", "alerts@floodalert.lk")
FIREBASE_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # service-account json for FCM
