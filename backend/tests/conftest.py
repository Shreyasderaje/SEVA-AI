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
from sqlalchemy import text  # noqa: E402

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
from app.models.donation import DonationCategory, DonationCompatibility, DonationSubcategory  # noqa: E402
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
        # Compatibility map for the matching engine: self-exact + the documented
        # related-category allowances (docs/AI_ML_METHODOLOGY.md).
        related_pairs = [
            ("packaged_food", "grains_rice"),
            ("grains_rice", "packaged_food"),
            ("clothing", "other"),
            ("other", "clothing"),
            ("utensils", "other"),
            ("other", "utensils"),
        ]
        for code, row in categories.items():
            db.add(
                DonationCompatibility(
                    donation_category_id=row.id, need_category_id=row.id, factor="exact"
                )
            )
        for donation_code, need_code in related_pairs:
            db.add(
                DonationCompatibility(
                    donation_category_id=categories[donation_code].id,
                    need_category_id=categories[need_code].id,
                    factor="related",
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
def clean_orgs():
    """Empty the organization/need/donation tables before a test so matching
    and listing assertions are deterministic. Users, categories, and settings
    are preserved."""
    db = SessionLocal()
    try:
        for table in (
            "donation_offers",
            "donation_status_history",
            "donation_images",
            "donations",
            "organization_needs",
            "organization_documents",
            "organizations",
        ):
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
    finally:
        db.close()
    yield


def make_pdf_bytes() -> bytes:
    """A minimal, magic-byte-valid PDF."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF"


def apply_organization(
    client: TestClient,
    token: str,
    *,
    name: str = "Hope Charitable Trust",
    document: bytes | None = None,
    lat: str | None = None,
    lng: str | None = None,
    consent: str = "false",
    doc_bytes: bytes | None = None,
    doc_type: str = "application/pdf",
    filename: str = "registration.pdf",
):
    payload = doc_bytes if doc_bytes is not None else make_pdf_bytes()
    data = {
        "name": name,
        "org_type": "ngo",
        "description": "We serve the local community.",
        "address": "12 Seva Road, Springfield",
        "contact_email": "contact@example.org",
        "contact_phone": "0000000000",
        "representative_name": "Rep Person",
        "location_consent": consent,
    }
    if lat is not None:
        data["latitude"] = lat
    if lng is not None:
        data["longitude"] = lng
    return client.post(
        "/api/organizations/apply",
        data=data,
        files=[("document", (filename, payload, doc_type))],
        headers={"Authorization": f"Bearer {token}"},
    )


def get_org_id(client: TestClient, token: str) -> str:
    response = client.get(
        "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def admin_verify(client: TestClient, admin_token: str, organization_id: str):
    return client.post(
        f"/api/organizations/admin/{organization_id}/verify",
        headers={"Authorization": f"Bearer {admin_token}"},
    )


def verified_org_token(client: TestClient, admin_token: str, email: str, name: str) -> str:
    """Register + apply + verify an organization in one step."""
    register_response = get_or_register(
        client, email, "OrgPass12345", "organization", f"{name} Owner"
    )
    applied = apply_organization(client, register_response, name=name)
    assert applied.status_code in (201, 409), applied.text
    organization_id = get_org_id(client, register_response)
    verified = admin_verify(client, admin_token, organization_id)
    assert verified.status_code == 200, verified.text
    return register_response


def create_need(
    client: TestClient,
    token: str,
    *,
    title: str = "Warm blankets needed",
    category_code: str = "clothing",
    quantity_required: str = "20",
    unit: str = "pieces",
    urgency: str = "high",
    required_by: str | None = None,
    lat: str | None = None,
    lng: str | None = None,
    consent: str = "false",
    status: str | None = None,
):
    categories = category_ids(client)
    payload = {
        "category_id": categories[category_code],
        "title": title,
        "unit": unit,
        "quantity_required": quantity_required,
        "urgency": urgency,
        "location_consent": consent,
    }
    if required_by:
        payload["required_by"] = required_by
    if lat:
        payload["latitude"] = lat
    if lng:
        payload["longitude"] = lng
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/needs", json=payload, headers=headers)
    if response.status_code == 201 and status is not None and status != "active":
        need_id = response.json()["id"]
        response = client.post(
            f"/api/needs/{need_id}/status", json={"status": status}, headers=headers
        )
    return response


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
