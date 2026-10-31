"""Pickup scheduling and completion tests (M4 §12 cases 21-30)."""

import pytest

from tests.conftest import (
    admin_verify,
    apply_organization,
    create_donation,
    create_need,
    get_or_register,
)


@pytest.mark.usefixtures("clean_orgs")
class TestPickupAndCompletion:
    def _org(self, client, admin_token, email, name):
        token = get_or_register(
            client, email, "OrgPass12345", "organization", f"{name} Owner"
        )
        apply_organization(client, token, name=name)
        admin_verify(client, admin_token, self._org_id(client, token))
        create_need(client, token, title=f"{name} need", quantity_required="20")
        return token

    @staticmethod
    def _org_id(client, token):
        return client.get(
            "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
        ).json()["id"]

    def _donor(self, client, email):
        return get_or_register(client, email, "DonorPass123", "donor", "P4 Donor")

    def _accepted_offer(self, client, admin_token, tag):
        donor = self._donor(client, f"p4.donor.{tag}@example.com")
        org_token = self._org(client, admin_token, f"p4.org.{tag}@example.com", f"Pickup Org {tag}")
        donation_id = create_donation(
            client, donor, category_code="clothing", quantity="10"
        ).json()["id"]
        offer_id = client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()["offer"]["id"]
        accepted = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert accepted.status_code == 200
        return donor, org_token, donation_id, offer_id

    def test_valid_pickup_scheduling(self, client, admin_token):
        donor, org_token, donation_id, offer_id = self._accepted_offer(client, admin_token, "a")
        response = client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
                "instructions": "Ring the bell at the side gate.",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["pickup_date"] == "2026-11-15"
        assert body["pickup_instructions"] == "Ring the bell at the side gate."
        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert donation["status"] == "pickup_scheduled"

    def test_invalid_pickup_window_rejected(self, client, admin_token):
        _, org_token, _, offer_id = self._accepted_offer(client, admin_token, "b")
        response = client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T14:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 422

    def test_pickup_notifications_reach_donor(self, client, admin_token):
        donor, org_token, _, offer_id = self._accepted_offer(client, admin_token, "c")
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        donor_notifications = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert "pickup_scheduled" in [n["type"] for n in donor_notifications["items"]]

    def test_invalid_status_transition_rejected(self, client, admin_token):
        donor, org_token, _, offer_id = self._accepted_offer(client, admin_token, "d")
        # picked_up before scheduling is invalid.
        response = client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 409
        # completion before pickup also invalid.
        response = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 5},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 409

    def test_completion_updates_need_and_history(self, client, admin_token):
        donor, org_token, donation_id, offer_id = self._accepted_offer(
            client, admin_token, "e"
        )
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        response = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 8},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["quantity_received"] == 8
        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert donation["status"] == "completed"
        assert body["need"]["quantity_fulfilled"] == 8
        assert body["need"]["remaining_quantity"] == 12
        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        statuses = [h["to_status"] for h in donation["timeline"]]
        assert statuses == ["pending", "offered", "accepted", "pickup_scheduled", "picked_up", "completed"]
        picked_up = client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert picked_up.status_code == 409  # completed is terminal

    def test_received_quantity_validation(self, client, admin_token):
        _, org_token, _, offer_id = self._accepted_offer(client, admin_token, "f")
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        zero = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 0},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert zero.status_code == 422
        over = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 11},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert over.status_code == 422
        assert "cannot exceed" in over.json()["detail"]

    def test_completion_caps_need_and_auto_fulfils(self, client, admin_token):
        # Need requires 20; donation is 10; received 10 -> need at 10/20 (not fulfilled).
        donor, org_token, _, offer_id = self._accepted_offer(client, admin_token, "g")
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        completed = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 10},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        need = completed.json()["need"]
        assert need["quantity_fulfilled"] == 10
        assert need["status"] == "active"  # 10 of 20 — not yet fulfilled

    def test_repeated_completion_does_not_double_count(self, client, admin_token):
        _, org_token, _, offer_id = self._accepted_offer(client, admin_token, "h")
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        first = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 6},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 6},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert second.status_code == 409
        assert first.json()["need"]["quantity_fulfilled"] == 6

    def test_audit_records_for_offer_actions(self, client, admin_token):
        from app.core.database import SessionLocal
        from sqlalchemy import select
        from app.models.support import AuditLog

        donor, org_token, _, offer_id = self._accepted_offer(client, admin_token, "i")
        client.post(
            f"/api/offers/{offer_id}/pickup",
            json={
                "pickup_date": "2026-11-15",
                "pickup_window_start": "2026-11-15T10:00:00",
                "pickup_window_end": "2026-11-15T12:00:00",
            },
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/picked-up",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        client.post(
            f"/api/offers/{offer_id}/complete",
            json={"quantity_received": 9},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        db = SessionLocal()
        try:
            actions = {
                row.action
                for row in db.scalars(
                    select(AuditLog).where(
                        AuditLog.target_type == "offer", AuditLog.target_id == offer_id
                    )
                ).all()
            }
            assert {"offer.accepted", "offer.pickup_scheduled", "offer.picked_up", "offer.completed"} <= actions
        finally:
            db.close()
