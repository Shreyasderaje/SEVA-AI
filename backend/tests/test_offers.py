"""Sequential offer workflow tests (M4 §12 cases 1-15)."""

import pytest

from tests.conftest import (
    admin_verify,
    apply_organization,
    create_donation,
    create_need,
    get_or_register,
)


@pytest.mark.usefixtures("clean_orgs")
class TestOfferWorkflow:
    def _setup_org(self, client, admin_token, email, name, *, urgency="high"):
        token = get_or_register(
            client, email, "OrgPass12345", "organization", f"{name} Owner"
        )
        applied = apply_organization(client, token, name=name)
        assert applied.status_code in (201, 409)
        admin_verify(client, admin_token, self._org_id(client, token))
        create_need(client, token, title=f"{name} need", urgency=urgency)
        return token

    @staticmethod
    def _org_id(client, token):
        response = client.get(
            "/api/organizations/me", headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()["id"]

    def _donor(self, client, email):
        return get_or_register(client, email, "DonorPass123", "donor", "M4 Donor")

    def _initiate(self, client, donor_token, donation_id):
        return client.post(
            f"/api/offers/initiate/{donation_id}",
            headers={"Authorization": f"Bearer {donor_token}"},
        )

    def test_initiate_creates_offer_for_highest_ranked(self, client, admin_token):
        donor = self._donor(client, "o4.d1@example.com")
        self._setup_org(client, admin_token, "o4.org.a@example.com", "Offer Org A")
        donation = create_donation(client, donor, category_code="clothing")
        response = self._initiate(client, donor, donation.json()["id"])
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "offered"
        offer = body["offer"]
        assert offer["status"] == "sent"
        assert offer["rank_at_offer"] == 1
        assert offer["factor_snapshot"]["factors"]["compatibility"]["score"] == 1.0
        assert offer["reason_text"]
        # Donation status history recorded the transition.
        history = client.get(
            f"/api/donations/{donation.json()['id']}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()["timeline"]
        assert history[-1]["to_status"] == "offered"

    def test_only_one_active_offer_and_no_duplicates(self, client, admin_token):
        donor = self._donor(client, "o4.d2@example.com")
        self._setup_org(client, admin_token, "o4.org.b@example.com", "Offer Org B")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        first = self._initiate(client, donor, donation_id)
        assert first.json()["offer"] is not None
        second = self._initiate(client, donor, donation_id)
        assert second.json()["offer"]["id"] == first.json()["offer"]["id"]
        assert second.json()["message"] == "An offer is already active for this donation."
        offers = client.get(
            f"/api/offers/donation/{donation_id}",
            headers={"Authorization": f"Bearer {donor}"},
        ).json()
        assert offers["total"] == 1

    def test_org_accepts_own_offer_donation_accepted(self, client, admin_token):
        donor = self._donor(client, "o4.d3@example.com")
        org_token = self._setup_org(client, admin_token, "o4.org.c@example.com", "Offer Org C")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]

        response = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"
        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert donation["status"] == "accepted"
        # Matching snapshot preserved.
        assert response.json()["factor_snapshot"] is not None

    def test_org_cannot_accept_another_orgs_offer(self, client, admin_token):
        donor = self._donor(client, "o4.d4@example.com")
        org_a = self._setup_org(client, admin_token, "o4.org.d@example.com", "Offer Org D")
        self._setup_org(client, admin_token, "o4.org.e@example.com", "Offer Org E")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]

        # Only org A has an offer; org E (registered as another org) cannot act on it.
        other = get_or_register(
            client, "o4.org.f@example.com", "OrgPass12345", "organization", "Offer Org F Owner"
        )
        apply_organization(client, other, name="Offer Org F")
        response = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {other}"},
        )
        assert response.status_code == 404  # get_own_offer hides foreign offers
        _ = org_a

    def test_donors_cannot_accept_offers(self, client, admin_token):
        donor = self._donor(client, "o4.d5@example.com")
        self._setup_org(client, admin_token, "o4.org.g@example.com", "Offer Org G")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]
        response = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {donor}"},
        )
        assert response.status_code == 403

    def test_decline_marks_only_the_offer_and_selects_next(self, client, admin_token):
        donor = self._donor(client, "o4.d6@example.com")
        org_a = self._setup_org(client, admin_token, "o4.org.h@example.com", "Decline Org A")
        org_b = self._setup_org(client, admin_token, "o4.org.i@example.com", "Decline Org B")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        first = self._initiate(client, donor, donation_id).json()["offer"]
        # Both needs are identical; the deterministic org-id tie-break decides
        # which ranks first — the test accepts either and asserts the OTHER org
        # receives the next offer.
        first_org_name = first["organization_name"]
        first_org_token = org_a if first_org_name == "Decline Org A" else org_b
        second_org_name = "Decline Org B" if first_org_name == "Decline Org A" else "Decline Org A"

        response = client.post(
            f"/api/offers/{first['id']}/decline",
            json={"reason": "No storage capacity this month"},
            headers={"Authorization": f"Bearer {first_org_token}"},
        )
        assert response.status_code == 200
        body = response.json()
        # Only the OFFER was declined; the donation stays offered.
        assert body["offer"]["status"] == "declined"
        assert body["offer"]["decline_reason"] == "No storage capacity this month"
        assert body["next"]["status"] == "offered"
        second = body["next"]["offer"]
        assert second is not None
        assert second["organization_name"] == second_org_name

        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert donation["status"] == "offered"
        statuses = [h["to_status"] for h in donation["timeline"]]
        assert statuses.count("offered") == 1  # no duplicate history rows

    def test_decliner_never_reoffered_and_no_candidate_returns_pending(self, client, admin_token):
        donor = self._donor(client, "o4.d7@example.com")
        org_a = self._setup_org(client, admin_token, "o4.org.j@example.com", "Only Org J")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]

        decline = client.post(
            f"/api/offers/{offer_id}/decline",
            json={"reason": "closed"},
            headers={"Authorization": f"Bearer {org_a}"},
        )
        assert decline.status_code == 200
        next_outcome = decline.json()["next"]
        assert next_outcome["offer"] is None
        assert next_outcome["status"] == "pending"

        donation = client.get(
            f"/api/donations/{donation_id}", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        assert donation["status"] == "pending"

        # Re-initiating picks nobody (decliner excluded) and stays pending.
        again = self._initiate(client, donor, donation_id)
        assert again.json()["offer"] is None
        assert again.json()["status"] == "pending"

    def test_no_candidate_notifies_donor(self, client, admin_token):
        donor = self._donor(client, "o4.d8@example.com")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        response = self._initiate(client, donor, donation_id)
        assert response.json()["offer"] is None
        notifications = client.get(
            "/api/notifications", headers={"Authorization": f"Bearer {donor}"}
        ).json()
        types = [n["type"] for n in notifications["items"]]
        assert "no_candidate" in types

    def test_invalid_initiation_states_rejected(self, client, admin_token):
        donor = self._donor(client, "o4.d9@example.com")
        org_token = self._setup_org(client, admin_token, "o4.org.k@example.com", "State Org K")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]
        client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        # Donation now accepted -> initiation impossible.
        response = self._initiate(client, donor, donation_id)
        assert response.status_code == 409

    def test_decline_after_accept_conflict(self, client, admin_token):
        donor = self._donor(client, "o4.d10@example.com")
        org_token = self._setup_org(client, admin_token, "o4.org.l@example.com", "Race Org L")
        donation_id = create_donation(client, donor, category_code="clothing").json()["id"]
        offer_id = self._initiate(client, donor, donation_id).json()["offer"]["id"]
        accepted = client.post(
            f"/api/offers/{offer_id}/accept",
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert accepted.status_code == 200
        declined = client.post(
            f"/api/offers/{offer_id}/decline",
            json={"reason": "changed my mind"},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        assert declined.status_code == 409  # acceptance won; decline impossible
