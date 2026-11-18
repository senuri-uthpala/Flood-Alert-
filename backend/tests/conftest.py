import os
import tempfile
from pathlib import Path

# Configure BEFORE the app is imported: temp DB + uploads, no scheduler, no real network calls.
_tmp = Path(tempfile.mkdtemp(prefix="floodalert-test-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp / 'test.db'}",
    "UPLOAD_DIR": str(_tmp / "uploads"),
    "DISABLE_SCHEDULER": "1",
    "FLOODALERT_OFFLINE": "1",
    "SECRET_KEY": "test-secret-key-for-pytest-only-0123456789",
    "ADMIN_EMAIL": "admin@test.lk",
    "ADMIN_PASSWORD": "AdminPass123!",
    "REPORTS_PER_HOUR": "50",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/auth/login", json={"email": "admin@test.lk", "password": "AdminPass123!"})
    assert r.status_code == 200
    return _auth(r.json()["access_token"])


@pytest.fixture
def make_user(client):
    counter = {"n": 0}

    def _make(language="en"):
        counter["n"] += 1
        email = f"user{counter['n']}_{os.urandom(3).hex()}@test.lk"
        r = client.post("/api/auth/register", json={
            "name": "Test User", "email": email, "password": "Password123", "language": language})
        assert r.status_code == 201, r.text
        return _auth(r.json()["access_token"]), r.json()["user"]

    return _make
