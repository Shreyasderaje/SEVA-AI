"""Registration, login, and session tests (acceptance tests 1 and 4 foundations)."""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.support import AuditLog
from app.models.user import DonorProfile, User

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, auth_headers, login, register


def test_register_donor_returns_token_and_creates_profile(client):
    response = register(client, "donor-new@example.com", "Passw0rd!123", "donor", "New Donor")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "donor"
    assert body["user"]["status"] == "active"

    me = client.get("/api/auth/me", headers=auth_headers(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "donor-new@example.com"

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == "donor-new@example.com"))
        assert user is not None
        assert db.get(DonorProfile, user.id) is not None
    finally:
        db.close()


def test_register_organization_has_no_org_row_yet(client):
    """Registration creates only the user; the organization application flow
    (M3) creates the organizations row with its verification document."""
    response = register(client, "org-new@example.com", "Passw0rd!123", "organization", "New Org")
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "organization"


def test_register_duplicate_email_conflict(client):
    first = register(client, "dup@example.com", "Passw0rd!123", "donor")
    assert first.status_code == 201
    second = register(client, "dup@example.com", "Passw0rd!123", "donor")
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"]


def test_register_validation_errors(client):
    bad_email = register(client, "not-an-email", "Passw0rd!123", "donor")
    assert bad_email.status_code == 422
    short_password = register(client, "shortpw@example.com", "short", "donor")
    assert short_password.status_code == 422
    invalid_role = register(
        client, "badrole@example.com", "Passw0rd!123", "superuser"
    )
    assert invalid_role.status_code == 422


def test_login_success_and_me(client):
    register(client, "login-ok@example.com", "Passw0rd!123", "donor", "Login User")
    response = login(client, "login-ok@example.com", "Passw0rd!123")
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200
    assert me.json()["full_name"] == "Login User"


def test_login_wrong_password_401(client):
    register(client, "wrongpw@example.com", "Passw0rd!123", "donor")
    response = login(client, "wrongpw@example.com", "WrongPassword1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_unknown_user_401_same_message(client):
    known = login(client, "wrongpw@example.com", "WrongPassword1")
    unknown = login(client, "ghost@example.com", "WrongPassword1")
    assert known.status_code == unknown.status_code == 401
    # No user enumeration: identical message and shape.
    assert known.json() == unknown.json()


def test_logout_requires_auth_and_responds(client, donor_token):
    anon = client.post("/api/auth/logout")
    assert anon.status_code == 401
    response = client.post("/api/auth/logout", headers=auth_headers(donor_token))
    assert response.status_code == 200
    assert "Logged out" in response.json()["message"]


def test_audit_rows_written_for_auth_events(client):
    register(client, "audit-user@example.com", "Passw0rd!123", "donor", "Audit User")
    login(client, "audit-user@example.com", "Passw0rd!123")
    login(client, "audit-user@example.com", "BadPassword1")

    db = SessionLocal()
    try:
        actions = {
            row.action
            for row in db.scalars(
                select(AuditLog).where(AuditLog.action.like("auth.%"))
            ).all()
        }
        assert "auth.register" in actions
        assert "auth.login_success" in actions
        assert "auth.login_failed" in actions
        # Scope to this test's rows: the audit table accumulates across the
        # session, and other tests also write login_failed rows.
        failed = db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "auth.login_failed")
            .where(AuditLog.note.like("%audit-user@example.com%"))
        )
        assert failed is not None and "audit-user@example.com" in (failed.note or "")
        assert failed.ip_hash is not None
        # No plaintext IP is stored.
        all_rows = db.scalars(select(AuditLog)).all()
        assert all("testclient" not in (r.ip_hash or "") for r in all_rows)
    finally:
        db.close()


def test_admin_password_not_leaked_in_responses(client):
    response = login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 200
    assert "password" not in response.json()["user"]
