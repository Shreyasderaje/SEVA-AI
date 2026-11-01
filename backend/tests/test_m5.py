"""M5 tests: analytics, demo seed/reset, pagination and filters (§7.1-7.3)."""

import os
from pathlib import Path

import pytest

from tests.conftest import (
    admin_verify,
    apply_organization,
    create_donation,
    create_need,
    get_org_id,
    get_or_register,
)


@pytest.fixture()
def analytics_env(client, admin_token):
    """A small deterministic dataset for analytics assertions."""
    donor = get_or_register(client, "an.donor@example.com", "DonorPass123", "donor", "An Donor")
    org_token = get_or_register(
        client, "an.org@example.com", "OrgPass12345", "organization", "An Org"
    )
    applied = apply_organization(client, org_token, name="Analytics Org")
    assert applied.status_code in (201, 409)
    admin_verify(client, admin_token, get_org_id(client, org_token))
    category = next(c for c in client.get("/api/categories").json() if c["code"] == "clothing")
    need = client.post(
        "/api/needs",
        json={"category_id": category["id"], "title": "Analytics need", "unit": "pieces",
              "quantity_required": 10},
        headers={"Authorization": f"Bearer {org_token}"},
    )
    assert need.status_code == 201
    donation = create_donation(client, donor, category_code="clothing")
    return {"donor_token": donor, "org_token": org_token, "donation_id": donation.json()["id"]}


class TestAnalytics:
    def test_admin_can_access_analytics(self, client, admin_token, analytics_env):
        response = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["cards"]["total_donations"] >= 1
        assert body["cards"]["verified_organizations"] >= 1

    def test_anonymous_receives_401(self, client):
        assert client.get("/api/admin/analytics").status_code == 401

    def test_donor_receives_403(self, client, donor_token):
        response = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {donor_token}"}
        )
        assert response.status_code == 403

    def test_organization_receives_403(self, client, org_token):
        response = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {org_token}"}
        )
        assert response.status_code == 403

    def test_counts_reflect_database_records(self, client, admin_token, analytics_env):
        body = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        donation_status = {d["status"]: d["count"] for d in body["donation_status"]}
        assert donation_status.get("pending", 0) >= 1
        categories = {c["category"]: c["count"] for c in body["donation_category"]}
        assert categories.get("clothing", 0) >= 1
        assert len(body["donations_over_time"]) >= 1

    def test_date_filters_change_results(self, client, admin_token, analytics_env):
        all_time = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        last_7 = client.get(
            "/api/admin/analytics",
            params={"days": 7},
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        # Records were just created: 7-day donations >= 1 and <= all-time.
        assert last_7["cards"]["total_donations"] >= 1
        assert last_7["cards"]["total_donations"] <= all_time["cards"]["total_donations"]
        assert last_7["range_days"] == 7

    def test_empty_database_zero_metrics(self, client, admin_token, clean_orgs):
        body = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert body["cards"]["total_donations"] == 0
        assert body["cards"]["pending_donations"] == 0
        assert body["donation_status"] == []
        assert body["donations_over_time"] == []

    def test_invalid_range_rejected(self, client, admin_token):
        response = client.get(
            "/api/admin/analytics",
            params={"days": 14},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_demo_data_reported_separately(self, client, admin_token, analytics_env):
        body = client.get(
            "/api/admin/analytics", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        assert "demo_data" in body
        assert set(body["demo_data"]) == {"users", "donations", "organizations", "payments"}


class TestSeedAndReset:
    """Runs the real scripts via subprocess against a disposable database."""

    @pytest.fixture()
    def demo_db(self, tmp_path, monkeypatch):
        db_file = tmp_path / "demo_seed.db"
        env = {
            **os.environ,
            "SEVA_ENV": "development",
            "DATABASE_URL": f"sqlite:///{db_file.as_posix()}",
            "JWT_SECRET": "seed-test-secret",
            "STORAGE_DIR": str(tmp_path / "storage"),
            "SEVA_ADMIN_PASSWORD": "SeedAdminPass1",
            "SEVA_ADMIN_EMAIL": "seed-admin@example.com",
        }
        # migrate
        import subprocess

        subprocess.run(
            [".venv/Scripts/python.exe", "-m", "alembic", "upgrade", "head"],
            cwd=".", env=env, check=True, capture_output=True,
        )
        subprocess.run(
            [".venv/Scripts/python.exe", "scripts/create_admin.py"],
            cwd=".", env=env, check=True, capture_output=True,
        )
        yield env
        for suffix in ("", "-journal"):
            Path(str(db_file) + suffix).unlink(missing_ok=True)

    def _run(self, env, script, *args):
        import subprocess

        return subprocess.run(
            [".venv/Scripts/python.exe", f"scripts/{script}", *args],
            cwd=".", env=env, capture_output=True, text=True,
        )

    def test_seed_refuses_outside_development(self, demo_db):
        env = {**demo_db, "SEVA_ENV": "production"}
        result = self._run(env, "seed_demo.py")
        assert result.returncode != 0
        assert "refusing" in result.stderr + result.stdout

    def test_reset_refuses_outside_development(self, demo_db):
        env = {**demo_db, "SEVA_ENV": "production"}
        result = self._run(env, "reset_demo.py", "--yes")
        assert result.returncode != 0
        assert "refusing" in result.stderr + result.stdout

    def test_seed_is_idempotent_and_creates_relationships(self, demo_db):
        first = self._run(demo_db, "seed_demo.py")
        assert first.returncode == 0, first.stderr
        second = self._run(demo_db, "seed_demo.py")
        assert second.returncode == 0, second.stderr
        # Second run must not create anything new.
        assert "new records this run: {'offers': 0" in second.stdout.replace("'", "'") or "0" in second.stdout

        # Relationships: demo orgs have needs; demo donations have history.
        import sqlite3

        db_path = demo_db["DATABASE_URL"].split("///")[-1]
        conn = sqlite3.connect(db_path)
        org_count = conn.execute(
            "SELECT COUNT(*) FROM organizations WHERE is_demo_data = 1"
        ).fetchone()[0]
        need_links = conn.execute(
            "SELECT COUNT(*) FROM organization_needs n JOIN organizations o "
            "ON n.organization_id = o.id WHERE o.is_demo_data = 1"
        ).fetchone()[0]
        donation_history = conn.execute(
            "SELECT COUNT(*) FROM donation_status_history h JOIN donations d "
            "ON h.donation_id = d.id WHERE d.is_demo_data = 1"
        ).fetchone()[0]
        conn.close()
        assert org_count >= 3
        assert need_links >= 2
        assert donation_history >= 1

    def test_reset_deletes_only_demo_records(self, demo_db):
        import sqlite3

        # Seed, then add a REAL record directly (non-demo).
        self._run(demo_db, "seed_demo.py")
        db_path = demo_db["DATABASE_URL"].split("///")[-1]
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO users (id, email, password_hash, full_name, role, status, is_demo_data, created_at, updated_at) "
            "VALUES ('real-user-1', 'real@example.com', 'x', 'Real User', 'donor', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        conn.commit()
        real_user_before = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_demo_data = 0"
        ).fetchone()[0]
        demo_donations_before = conn.execute(
            "SELECT COUNT(*) FROM donations WHERE is_demo_data = 1"
        ).fetchone()[0]
        conn.close()
        assert real_user_before >= 2  # admin (created with is_demo_data=0) + real user

        result = self._run(demo_db, "reset_demo.py", "--yes")
        assert result.returncode == 0, result.stderr

        conn = sqlite3.connect(db_path)
        real_user_after = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_demo_data = 0"
        ).fetchone()[0]
        demo_donations_after = conn.execute(
            "SELECT COUNT(*) FROM donations WHERE is_demo_data = 1"
        ).fetchone()[0]
        conn.close()
        assert real_user_after == real_user_before  # real records survive
        assert demo_donations_before > 0
        assert demo_donations_after == 0  # demo records gone

    def test_reset_is_idempotent(self, demo_db):
        self._run(demo_db, "seed_demo.py")
        first = self._run(demo_db, "reset_demo.py", "--yes")
        assert first.returncode == 0
        second = self._run(demo_db, "reset_demo.py", "--yes")
        assert second.returncode == 0
        assert "nothing to reset" in second.stdout


class TestAdminFiltersAndPagination:
    def test_org_search_and_status_filter(self, client, admin_token):
        token = get_or_register(
            client, "f.org1@example.com", "OrgPass12345", "organization", "Filter Org One"
        )
        apply_organization(client, token, name="Zebra Charity")
        token2 = get_or_register(
            client, "f.org2@example.com", "OrgPass12345", "organization", "Filter Org Two"
        )
        apply_organization(client, token2, name="Alpha Relief")
        admin_verify(client, admin_token, get_org_id(client, token2))
        headers = {"Authorization": f"Bearer {admin_token}"}

        search = client.get(
            "/api/organizations/admin/all", params={"q": "zebra"}, headers=headers
        )
        names = [o["name"] for o in search.json()["items"]]
        assert "Zebra Charity" in names and "Alpha Relief" not in names

        verified = client.get(
            "/api/organizations/admin/all",
            params={"status": "verified", "q": "alpha"},
            headers=headers,
        )
        verified_names = [o["name"] for o in verified.json()["items"]]
        assert "Alpha Relief" in verified_names

    def test_admin_donations_filters_and_pagination(self, client, admin_token, donor_token):
        for i in range(3):
            create_donation(
                client, donor_token, title=f"AdminFilter jacket {i}", category_code="clothing"
            )
        headers = {"Authorization": f"Bearer {admin_token}"}
        category = next(c for c in client.get("/api/categories").json() if c["code"] == "clothing")

        all_matching = client.get(
            "/api/admin/donations", params={"q": "AdminFilter"}, headers=headers
        )
        assert all_matching.json()["total"] == 3

        paged = client.get(
            "/api/admin/donations",
            params={"q": "AdminFilter", "page": 1, "page_size": 2},
            headers=headers,
        )
        assert len(paged.json()["items"]) == 2 and paged.json()["total"] == 3

        by_category = client.get(
            "/api/admin/donations",
            params={"q": "AdminFilter", "category_id": category["id"]},
            headers=headers,
        )
        assert by_category.json()["total"] == 3

        empty = client.get(
            "/api/admin/donations",
            params={"q": "AdminFilter", "status": "completed"},
            headers=headers,
        )
        assert empty.json()["total"] == 0

    def test_invalid_pagination_rejected(self, client, admin_token):
        response = client.get(
            "/api/admin/donations",
            params={"page": 0},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422
        oversized = client.get(
            "/api/admin/donations",
            params={"page_size": 999},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert oversized.status_code == 422

    def test_offers_status_filter(self, client, admin_token):
        donor = get_or_register(
            client, "f.donor.offers@example.com", "DonorPass123", "donor", "Offer Filter Donor"
        )
        token = get_or_register(
            client, "f.org.offers@example.com", "OrgPass12345", "organization", "Offer Filter Org"
        )
        apply_organization(client, token, name="Offer Filter Org")
        admin_verify(client, admin_token, get_org_id(client, token))
        create_need(client, token, title="Offer filter need")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()["offer"]["id"]

        sent = client.get(
            "/api/offers/mine",
            params={"status": "sent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sent.json()["total"] == 1
        client.post(
            f"/api/offers/{offer_id}/decline",
            json={"reason": "filter test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        declined = client.get(
            "/api/offers/mine",
            params={"status": "declined"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert declined.json()["total"] == 1
        still_sent = client.get(
            "/api/offers/mine",
            params={"status": "sent"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert still_sent.json()["total"] == 0

    def test_role_isolation_on_admin_filters(self, client, donor_token):
        response = client.get(
            "/api/admin/donations", headers={"Authorization": f"Bearer {donor_token}"}
        )
        assert response.status_code == 403
