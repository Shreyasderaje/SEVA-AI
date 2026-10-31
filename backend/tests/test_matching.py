"""Eligibility and matching engine tests (authorization cases 19-33).

All expectations follow the approved formula: compatibility 0.30, urgency
0.25, distance 0.20, quantity_fit 0.15, timeliness 0.10; Haversine distance
with the 50 km service radius; neutral distance factor 0.5 when coordinates
are missing.
"""

import math
from datetime import date, timedelta

from app.services.matching import haversine_km, timeliness_score
from tests.conftest import (
    admin_verify,
    apply_organization,
    create_donation,
    create_need,
    get_org_id,
    get_or_register,
)


def _verified_org(client, admin_token, email, name, *, lat=None, lng=None):
    token = get_or_register(
        client, email, "OrgPass12345", "organization", f"{name} Owner"
    )
    applied = apply_organization(
        client, token, name=name, lat=lat, lng=lng, consent="true" if lat else "false"
    )
    assert applied.status_code in (201, 409), applied.text
    admin_verify(client, admin_token, get_org_id(client, token))
    return token


def _matches(client, donor_token, donation_id):
    response = client.get(
        f"/api/donations/{donation_id}/matches",
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------- haversine


def test_haversine_known_distance():
    # Bengaluru (12.9716, 77.5946) to Chennai (13.0827, 80.2707) ≈ 292 km.
    distance = haversine_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert math.isclose(distance, 292, rel_tol=0.02)


# ------------------------------------------------------------- eligibility


def test_unverified_organizations_excluded(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor1@example.com", "DonorPass123", "donor", "M Donor One"
    )
    unverified_token = get_or_register(
        client, "m.org.unverified@example.com", "OrgPass12345", "organization", "Unverified Org"
    )
    apply_organization(client, unverified_token, name="Unverified Match Org")

    donation = create_donation(client, donor_token, category_code="clothing")
    result = _matches(client, donor_token, donation.json()["id"])
    assert result["eligible"] == []
    reasons = {e["reason_code"] for e in result["excluded"]}
    assert "organization_not_verified" in reasons


def test_incompatible_category_excluded(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor2@example.com", "DonorPass123", "donor", "M Donor Two"
    )
    token = _verified_org(client, admin_token, "m.org.incompat@example.com", "Incompat Org")
    create_need(client, token, title="Only clothing needed", category_code="clothing")

    donation = create_donation(client, donor_token, category_code="packaged_food")
    result = _matches(client, donor_token, donation.json()["id"])
    org_ids = [m["organization_id"] for m in result["eligible"]]
    assert get_org_id(client, token) not in org_ids
    reasons = {e["reason_code"] for e in result["excluded"]}
    assert "category_incompatible" in reasons


def test_related_category_is_eligible_with_lower_score(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor3@example.com", "DonorPass123", "donor", "M Donor Three"
    )
    token = _verified_org(client, admin_token, "m.org.related@example.com", "Related Org")
    create_need(
        client, token, title="Rice or packaged food", category_code="grains_rice"
    )

    # packaged_food is related to grains_rice -> eligible with compatibility 0.5.
    donation = create_donation(client, donor_token, category_code="packaged_food")
    result = _matches(client, donor_token, donation.json()["id"])
    assert len(result["eligible"]) == 1
    match = result["eligible"][0]
    assert match["factors"]["compatibility"]["score"] == 0.5
    assert "(related category)" in " ".join(match["reasons"])


def test_no_remaining_need_excluded(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor4@example.com", "DonorPass123", "donor", "M Donor Four"
    )
    token = _verified_org(client, admin_token, "m.org.fulfilled@example.com", "Fulfilled Org")
    need = create_need(
        client, token, title="Will be fulfilled", category_code="utensils"
    )
    need_id = need.json()["id"]
    headers = {"Authorization": f"Bearer {token}"}
    fulfilled = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 50}, headers=headers
    )
    assert fulfilled.status_code == 422  # cannot exceed the required 20
    exact = client.post(
        f"/api/needs/{need_id}/fulfilment", json={"quantity": 20}, headers=headers
    )
    assert exact.status_code == 200, exact.text

    donation = create_donation(client, donor_token, category_code="utensils")
    result = _matches(client, donor_token, donation.json()["id"])
    assert result["eligible"] == []
    reasons = {e["reason_code"] for e in result["excluded"]}
    # The need auto-transitions to "fulfilled", so it is excluded as inactive;
    # both codes are truthful depending on timing.
    assert reasons & {"need_fully_funded", "need_not_active"}


# ------------------------------------------------------- ranking + formula


def test_ranking_order_and_formula(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor5@example.com", "DonorPass123", "donor", "M Donor Five"
    )
    # Org A: critical urgency, close, exact category.
    token_a = _verified_org(
        client, admin_token, "m.org.a@example.com", "Alpha Org", lat="12.9716", lng="77.5946"
    )
    create_need(
        client, token_a, title="Critical need", category_code="clothing",
        urgency="critical", required_by=(date.today() + timedelta(days=3)).isoformat(),
    )
    # Org B: low urgency, far, exact category.
    token_b = _verified_org(
        client, admin_token, "m.org.b@example.com", "Beta Org", lat="13.0500", lng="77.6000"
    )
    create_need(
        client, token_b, title="Low urgency need", category_code="clothing",
        urgency="low", required_by=(date.today() + timedelta(days=55)).isoformat(),
    )

    donation = create_donation(
        client, donor_token, category_code="clothing", quantity="10",
        lat="12.9716", lng="77.5946", consent="true",
    )
    result = _matches(client, donor_token, donation.json()["id"])
    assert len(result["eligible"]) == 2
    first, second = result["eligible"]
    assert first["organization_name"] == "Alpha Org"
    assert first["rank"] == 1 and second["rank"] == 2
    assert first["score"] > second["score"]

    # Formula check for the runner-up (Beta): all factors computable by hand.
    distance_b = haversine_km(12.9716, 77.5946, 13.05, 77.6)
    factors = second["factors"]
    assert factors["compatibility"]["score"] == 1.0
    assert factors["urgency"]["score"] == 0.25
    assert math.isclose(
        factors["distance"]["score"], max(0.0, 1 - distance_b / 50.0), abs_tol=1e-3
    )
    assert factors["quantity_fit"]["score"] == 0.5  # min(10,20)/max(10,20)
    expected_total = (
        factors["compatibility"]["weighted"]
        + factors["urgency"]["weighted"]
        + factors["distance"]["weighted"]
        + factors["quantity_fit"]["weighted"]
        + factors["timeliness"]["weighted"]
    )
    assert math.isclose(second["score"], round(expected_total * 100, 1), abs_tol=0.05)


def test_matching_explanations_correspond_to_factors(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor6@example.com", "DonorPass123", "donor", "M Donor Six"
    )
    token = _verified_org(client, admin_token, "m.org.exp@example.com", "Explain Org")
    create_need(
        client, token, title="Explained need", category_code="clothing", urgency="critical"
    )
    donation = create_donation(client, donor_token, category_code="clothing")
    match = _matches(client, donor_token, donation.json()["id"])["eligible"][0]
    joined = " ".join(match["reasons"])
    assert "critical" in joined
    assert "Distance could not be calculated." in joined
    assert "about" not in joined.lower() or "km" not in joined  # no fabricated distance


def test_missing_coordinates_use_neutral_distance_and_explanation(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor7@example.com", "DonorPass123", "donor", "M Donor Seven"
    )
    token = _verified_org(client, admin_token, "m.org.neutral@example.com", "Neutral Org")
    create_need(client, token, title="Neutral distance need", category_code="clothing")
    # Donation WITHOUT coordinates.
    donation = create_donation(client, donor_token, category_code="clothing")
    match = _matches(client, donor_token, donation.json()["id"])["eligible"][0]
    assert match["distance_km"] is None
    assert match["factors"]["distance"]["score"] == 0.5
    assert match["factors"]["distance"]["weighted"] == 0.1
    assert "Distance could not be calculated." in match["reasons"]

    # Org without coordinates, donation WITH coordinates -> still neutral.
    donation2 = create_donation(
        client, donor_token, category_code="clothing",
        lat="12.9716", lng="77.5946", consent="true",
    )
    match2 = _matches(client, donor_token, donation2.json()["id"])["eligible"][0]
    assert match2["distance_km"] is None
    assert match2["factors"]["distance"]["score"] == 0.5


def test_valid_coordinates_use_haversine_distance(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor8@example.com", "DonorPass123", "donor", "M Donor Eight"
    )
    token = _verified_org(
        client, admin_token, "m.org.haver@example.com", "Haversine Org",
        lat="12.9716", lng="77.5946",
    )
    create_need(client, token, title="Haversine need", category_code="clothing")
    donation = create_donation(
        client, donor_token, category_code="clothing",
        lat="13.0500", lng="77.6000", consent="true",
    )
    match = _matches(client, donor_token, donation.json()["id"])["eligible"][0]
    expected = haversine_km(12.9716, 77.5946, 13.05, 77.6)
    assert match["distance_km"] is not None
    assert math.isclose(match["distance_km"], expected, abs_tol=0.05)
    assert match["factors"]["distance"]["score"] > 0.8  # ~8.7 km of a 50 km radius


def test_outside_radius_excluded(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor9@example.com", "DonorPass123", "donor", "M Donor Nine"
    )
    token = _verified_org(
        client, admin_token, "m.org.far@example.com", "Far Org", lat="13.5000", lng="80.2000"
    )
    create_need(client, token, title="Far away need", category_code="clothing")
    donation = create_donation(
        client, donor_token, category_code="clothing",
        lat="12.9716", lng="77.5946", consent="true",
    )
    result = _matches(client, donor_token, donation.json()["id"])
    org_ids = [m["organization_id"] for m in result["eligible"]]
    assert get_org_id(client, token) not in org_ids
    reasons = {e["reason_code"] for e in result["excluded"]}
    assert "outside_service_radius" in reasons


def test_invalid_coordinates_rejected_on_donation(client, donor_token):
    from tests.conftest import get_or_register as gr
    response = create_donation(
        client, donor_token, category_code="clothing",
        lat="999", lng="77.5946", consent="true",
    )
    assert response.status_code == 422


def test_matching_deterministic_across_runs(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor10@example.com", "DonorPass123", "donor", "M Donor Ten"
    )
    for i in range(3):
        token = _verified_org(
            client, admin_token, f"m.org.det{i}@example.com", f"Det Org {i}"
        )
        create_need(
            client, token, title=f"Det need {i}", category_code="clothing",
            urgency=["low", "high", "critical"][i],
        )
    donation = create_donation(client, donor_token, category_code="clothing")
    run1 = _matches(client, donor_token, donation.json()["id"])
    run2 = _matches(client, donor_token, donation.json()["id"])
    assert run1 == run2  # identical inputs -> identical ranking


def test_tie_breaking_deterministic(client, admin_token):
    """Two IDENTICAL needs (same urgency, distance, quantity, timeliness) ->
    same score; tie broken by need created_at (earlier first)."""
    donor_token = get_or_register(
        client, "m.donor11@example.com", "DonorPass123", "donor", "M Donor Eleven"
    )
    token_a = _verified_org(client, admin_token, "m.org.tie1@example.com", "Tie Org A")
    token_b = _verified_org(client, admin_token, "m.org.tie2@example.com", "Tie Org B")
    create_need(client, token_a, title="Tie need A", category_code="clothing", urgency="high")
    create_need(client, token_b, title="Tie need B", category_code="clothing", urgency="high")
    donation = create_donation(client, donor_token, category_code="clothing")
    result = _matches(client, donor_token, donation.json()["id"])
    assert len(result["eligible"]) == 2
    first, second = result["eligible"]
    assert first["score"] == second["score"]
    # Deterministic order by need creation time; rerun to prove stability.
    again = _matches(client, donor_token, donation.json()["id"])
    assert [m["need_id"] for m in result["eligible"]] == [m["need_id"] for m in again["eligible"]]


def test_client_ai_fields_do_not_influence_matching(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor12@example.com", "DonorPass123", "donor", "M Donor Twelve"
    )
    token = _verified_org(client, admin_token, "m.org.ai@example.com", "AI Org")
    create_need(client, token, title="AI-independent need", category_code="grains_rice")
    # Donation created with a forged AI suggestion of a DIFFERENT category.
    donation = create_donation(
        client, donor_token, category_code="grains_rice",
        ai_predicted="clothing", ai_confidence="0.99",
    )
    result = _matches(client, donor_token, donation.json()["id"])
    # Matching used the donor-confirmed category (grains_rice) -> AI org eligible.
    assert len(result["eligible"]) == 1
    assert result["eligible"][0]["need_category_code"] == "grains_rice"


def test_no_eligible_organizations_empty_result(client, donor_token):
    donation = create_donation(client, donor_token, category_code="clothing")
    result = _matches(client, donor_token, donation.json()["id"])
    assert result["eligible"] == []
    assert all(e["count"] > 0 for e in result["excluded"])
    assert result["service_radius_km"] == 50.0


def test_donor_cannot_view_other_donations_matches(client, admin_token):
    donor_token = get_or_register(
        client, "m.donor13@example.com", "DonorPass123", "donor", "M Donor Thirteen"
    )
    other = get_or_register(
        client, "m.donor14@example.com", "DonorPass123", "donor", "M Donor Fourteen"
    )
    token = _verified_org(client, admin_token, "m.org.priv@example.com", "Privacy Org")
    create_need(client, token, title="Privacy need", category_code="clothing")
    donation = create_donation(client, donor_token, category_code="clothing")
    response = client.get(
        f"/api/donations/{donation.json()['id']}/matches",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert response.status_code == 404


def test_timeliness_score_boundaries():
    today = date.today()
    assert timeliness_score(None, today) == 0.5
    assert timeliness_score(today + timedelta(days=14), today) == 1.0
    assert timeliness_score(today - timedelta(days=5), today) == 1.0  # overdue = urgent
    assert timeliness_score(today + timedelta(days=60), today) == 0.2
    assert timeliness_score(today + timedelta(days=80), today) == 0.2
    midpoint = timeliness_score(today + timedelta(days=37), today)  # halfway 14..60
    assert midpoint == round(1.0 - 0.5 * 0.8, 4)


import pytest

pytestmark = pytest.mark.usefixtures("clean_orgs")
