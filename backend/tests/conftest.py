"""Pytest configuration for SEVA-AI backend tests.

Environment variables are set BEFORE any app import so settings are built for
the test database. Schema is created with `Base.metadata.create_all` (fast);
the same models are verified against real Alembic migrations in development.
"""

import json
import os

os.environ["SEVA_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite:///./test_seva.db"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["RATE_LIMIT_LOGIN"] = "5/minute"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import rate_limit as rate_limit_module  # noqa: E402
from app.core.constants import (  # noqa: E402
    CLASSIFIER_CLASSES,
    DEFAULT_MATCHING_WEIGHTS,
    ROLE_ADMIN,
)
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.app_settings import Setting  # noqa: E402
from app.models.donation import DonationCategory  # noqa: E402
from app.models.user import User  # noqa: E402

ADMIN_EMAIL = "admin@seva.example"
ADMIN_PASSWORD = "admin-test-password"


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh schema for the whole session, with base reference data seeded."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for code, display in CLASSIFIER_CLASSES:
            db.add(DonationCategory(code=code, display_name=display, is_active=True))
        db.add(
            Setting(key="matching_weights", value_json=json.dumps(DEFAULT_MATCHING_WEIGHTS))
        )
        db.add(Setting(key="service_radius_km", value_json="50.0"))
        db.add(
            User(
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                full_name="Seva Admin",
                role=ROLE_ADMIN,
                status="active",
            )
        )
        db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client
    rate_limit_module.reset_rate_limiter()


def register(client: TestClient, email: str, password: str, role: str, full_name: str = "Test User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name, "role": role},
    )


def login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def donor_token(client: TestClient) -> str:
    return get_or_register(
        client, "donor1@example.com", "DonorPass123", "donor", "Demo Donor"
    )


@pytest.fixture()
def org_token(client: TestClient) -> str:
    return get_or_register(
        client, "org1@example.com", "OrgPass12345", "organization", "Demo Org"
    )


def get_or_register(
    client: TestClient, email: str, password: str, role: str, full_name: str
) -> str:
    """Register a helper user, or log in if an earlier test in this session
    already created it (the test database persists for the whole session)."""
    response = register(client, email, password, role, full_name)
    if response.status_code == 409:
        response = login(client, email, password)
    assert response.status_code in (200, 201), response.text
    return response.json()["access_token"]


@pytest.fixture()
def admin_token(client: TestClient) -> str:
    response = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
