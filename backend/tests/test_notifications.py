"""Notification tests (M4 §12 cases 16-20)."""

import pytest

from tests.conftest import (
    admin_verify,
    apply_organization,
    create_donation,
    create_need,
    get_or_register,
)


@pytest.mark.usefixtures("clean_orgs")
class TestNotifications:
    def _org(self, client, admin_token, email, name):
        token = get_or_register(
            client, email, "OrgPass12345", "organization", f"{name} Owner"
        )
        apply_organization(client, token, name=name)
        admin_verify(client, admin_token, self._org_id(client, token))
        create_need(client, token, title=f"{name} need")
        return token

    @staticmethod
    def _org_id(client, token):
        return client.get(
            "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
        ).json()["id"]

    def _donor(self, client, email):
        return get_or_register(client, email, "DonorPass123", "donor", "N4 Donor")

    def test_workflow_events_notify_correct_users(self, client, admin_token):
        donor = self._donor(client, "n4.d1@example.com")
        org_token = self._org(client, admin_token, "n4.org.a@example.com", "Notif Org A")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()["offer"]["id"]

        org_notifications = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {org_token}"}
        ).json()
        org_types = [n["type"] for n in org_notifications["items"]]
        assert "offer_received" in org_types

        donor_notifications = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        donor_types = [n["type"] for n in donor_notifications["items"]]
        assert "offer_sent" in donor_types

        client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        donor_after = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert "offer_accepted" in [n["type"] for n in donor_after["items"]]

    def test_users_cannot_access_others_notifications(self, client, admin_token):
        donor_a = self._donor(client, "n4.d2@example.com")
        donor_b = self._donor(client, "n4.d3@example.com")
        donation_id = create_donation(client, donor_a, category_code="clothing").json()["id"]
        client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor_a}"},
        )
        a_list = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor_a}"}
        ).json()
        target_id = a_list["items"][0]["id"]

        foreign_read = client.post(
            f"/api/notifications/{target_id}/read",
            headers={"Authorization": f"Bearer {donor_b}"},
        )
        assert foreign_read.status_code == 404
        b_list = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor_b}"}
        ).json()
        assert b_list["total"] == 0

    def test_mark_one_and_mark_all_read(self, client, admin_token):
        donor = self._donor(client, "n4.d4@example.com")
        for i in range(3):
            donation_id = create_donation(
                client, donor, category_code="clothing", title=f"Notif batch {i}"
            ).json()["id"]
            client.post(
                f"/api/offers/initiate/{donation_id}",
                headers={"Authorization": f"Bearer {donor}"},
            )
        listed = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert listed["unread"] >= 3

        first_id = listed["items"][0]["id"]
        client.post(
            f"/api/notifications/{first_id}/read",
            headers={"Authorization": f"Bearer {donor}"},
        )
        after_one = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert after_one["unread"] == listed["unread"] - 1

        client.post(
            "/api/notifications/read-all",
            headers={"Authorization": f"Bearer {donor}"},
        )
        after_all = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert after_all["unread"] == 0

    def test_duplicate_accept_does_not_duplicate_notifications(self, client, admin_token):
        donor = self._donor(client, "n4.d5@example.com")
        org_token = self._org(client, admin_token, "n4.org.b@example.com", "Notif Org B")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()["offer"]["id"]

        first = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert second.status_code == 409

        donor_notifications = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        accepted = [
            n for n in donor_notifications["items"] if n["type"] == "offer_accepted"
        ]
        assert len(accepted) == 1  # idempotent via the status guard

    def test_anonymous_notifications_denied(self, client):
        assert client.get("/api/notifications").status_code == 401
