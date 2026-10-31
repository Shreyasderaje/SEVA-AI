"""Pytest configuration for SEVA-AI backend tests.

Environment variables are set BEFORE any app import so settings are built for
the test database. Schema is created with `Base.metadata.create_all` (fast);
the same models are verified against real Alembic migrations in development.
"""

import json
import os
import shutil
from pathlib import Path

os.environ["SEVA_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite:///./test_seva.db"
os.environ["JWT_SECRET"] = "test-secret-key-not-for-production"
os.environ["JWT_EXPIRE_MINUTES"] = "60"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["RATE_LIMIT_LOGIN"] = "5/minute"
os.environ["STORAGE_DIR"] = "./test_storage"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.core import rate_limit as rate_limit_module  # noqa: E402
from app.core.config import BACKEND_DIR  # noqa: E402
from app.core.constants import (  # noqa: E402
    CLASSIFIER_CLASSES,
    DEFAULT_MATCHING_WEIGHTS,
    ROLE_ADMIN,
    SUBCATEGORY_EXAMPLES,
)
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.app_settings import Setting  # noqa: E402
from app.models.donation import DonationCategory, DonationSubcategory  # noqa: E402
from app.models.user import User  # noqa: E402

ADMIN_EMAIL = "admin@seva.example"
ADMIN_PASSWORD = "admin-test-password"
TEST_STORAGE = BACKEND_DIR / "test_storage"


def make_jpeg_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    """A real, valid JPEG produced in-memory (no fixture files needed)."""
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", size, color=(120, 160, 90)).save(buffer, "JPEG")
    return buffer.getvalue()


def make_png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", size, color=(10, 20, 30)).save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture(scope="session", autouse=True)
def database():
    """Fresh schema + empty test storage for the whole session."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(TEST_STORAGE, ignore_errors=True)
    TEST_STORAGE.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        categories: dict[str, DonationCategory] = {}
        for code, display in CLASSIFIER_CLASSES:
            category = DonationCategory(code=code, display_name=display, is_active=True)
            db.add(category)
            db.flush()
            categories[code] = category
        for code, names in SUBCATEGORY_EXAMPLES.items():
            for order, name in enumerate(names):
                db.add(
                    DonationSubcategory(
                        category_id=categories[code].id,
                        display_name=name,
                        sort_order=order,
                        is_active=True,
                    )
                )
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
    shutil.rmtree(TEST_STORAGE, ignore_errors=True)


def storage_file_count() -> int:
    return sum(1 for _ in TEST_STORAGE.rglob("*.jpg"))


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
def donor2_token(client: TestClient) -> str:
    return get_or_register(
        client, "donor2@example.com", "Donor2Pass123", "donor", "Second Donor"
    )


@pytest.fixture()
def org_token(client: TestClient) -> str:
    return get_or_register(
        client, "org1@example.com", "OrgPass12345", "organization", "Demo Org"
    )


def category_ids(client: TestClient) -> dict[str, str]:
    """code -> category id, fetched through the public endpoint."""
    response = client.get("/api/categories")
    assert response.status_code == 200
    return {c["code"]: c["id"] for c in response.json()}


def create_donation(
    client: TestClient,
    token: str,
    *,
    title: str = "Winter clothes for donation",
    category_code: str = "clothing",
    subcategory: str | None = None,
    quantity: str = "5",
    unit: str = "pieces",
    condition: str | None = "good",
    description: str = "Gently used winter jackets.",
    pickup_area: str = "Green Park area",
    lat: str | None = None,
    lng: str | None = None,
    consent: str = "false",
    ai_predicted: str | None = None,
    ai_confidence: str | None = None,
    image_count: int = 1,
    image_bytes: bytes | None = None,
    extra_fields: dict[str, str] | None = None,
):
    categories = category_ids(client)
    data = {
        "title": title,
        "description": description,
        "category_id": categories[category_code],
        "quantity": quantity,
        "unit": unit,
        "pickup_area": pickup_area,
        "location_consent": consent,
    }
    if condition is not None:
        data["condition"] = condition
    if subcategory is not None:
        data["subcategory_id"] = subcategory
    if lat is not None:
        data["pickup_latitude"] = lat
    if lng is not None:
        data["pickup_longitude"] = lng
    if ai_predicted is not None:
        data["ai_predicted_category"] = ai_predicted
    if ai_confidence is not None:
        data["ai_confidence"] = ai_confidence
    if extra_fields:
        data.update(extra_fields)

    payload = image_bytes if image_bytes is not None else make_jpeg_bytes()
    files = [
        ("images", (f"photo{i}.jpg", payload, "image/jpeg"))
        for i in range(1, image_count + 1)
    ]
    return client.post(
        "/api/donations",
        data=data,
        files=files,
        headers={"Authorization": f"Bearer {token}"},
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
