"""Explainable, deterministic donation-to-organization matching engine.

This is a RULE-BASED weighted scoring algorithm — NOT machine learning — per
§6.4 of the master prompt and the Stage-1 review decisions. All inputs come
from the database; client-supplied fields (including AI predictions) can never
influence eligibility or ranking.

Pipeline:
1. Eligibility filter (addendum §6, §9):
   - organization verified (pending/rejected/suspended excluded);
   - organization not suspended;
   - an ACTIVE need with remaining quantity > 0;
   - need category compatible with the DONOR-CONFIRMED donation category
     (exact = 1.0, related = 0.5 via `donation_compatibility`);
   - Haversine distance within the configured service radius when both
     coordinate pairs are valid; otherwise the neutral distance factor 0.5
     with the explicit explanation "Distance could not be calculated."
2. Weighted scoring (weights from the `settings` table, defaults approved):
   compatibility 0.30, urgency 0.25, distance 0.20, quantity_fit 0.15,
   timeliness 0.10.
3. Deterministic ordering: score desc, then need created_at ascending, then
   organization id ascending. Identical inputs always produce identical
   rankings.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    DONATION_STATUSES,
    NEED_ACTIVE,
    VERIFICATION_VERIFIED,
)
from app.models.donation import Donation, DonationCompatibility
from app.models.need import OrganizationNeed
from app.models.organization import Organization
from app.models.app_settings import Setting

DEFAULT_WEIGHTS = {
    "compatibility": 0.30,
    "urgency": 0.25,
    "distance": 0.20,
    "quantity_fit": 0.15,
    "timeliness": 0.10,
}
DEFAULT_SERVICE_RADIUS_KM = 50.0

URGENCY_SCORES = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
EXACT_SCORE = 1.0
RELATED_SCORE = 0.5
NEUTRAL_DISTANCE_SCORE = 0.5
DISTANCE_COULD_NOT_BE_CALCULATED = "Distance could not be calculated."
EARTH_RADIUS_KM = 6371.0
TIMELINESS_FULL_DAYS = 14
TIMELINESS_FLOOR_DAYS = 60
TIMELINESS_FLOOR_SCORE = 0.2


class MatchingInputError(ValueError):
    """Raised when a donation cannot be matched at all (bad status etc.)."""


@dataclass
class Factor:
    score: float
    weight: float

    @property
    def weighted(self) -> float:
        return round(self.score * self.weight, 4)


@dataclass
class MatchCandidate:
    organization_id: str
    organization_name: str
    verification_status: str
    need_id: str
    need_title: str
    need_category_code: str
    remaining_quantity: float
    unit: str
    distance_km: float | None
    rank: int
    score: float  # 0-100, one decimal
    factors: dict[str, Factor]
    reasons: list[str] = field(default_factory=list)


def load_settings(db: Session) -> tuple[dict[str, float], float]:
    """Matching weights and service radius from the settings table (§6.4)."""
    weights = dict(DEFAULT_WEIGHTS)
    radius = DEFAULT_SERVICE_RADIUS_KM
    for setting in db.scalars(
        select(Setting).where(Setting.key.in_(["matching_weights", "service_radius_km"]))
    ).all():
        if setting.key == "matching_weights" and setting.value_json:
            try:
                stored = json.loads(setting.value_json)
                cleaned = {
                    key: float(value)
                    for key, value in stored.items()
                    if key in DEFAULT_WEIGHTS
                }
                if cleaned and abs(sum(cleaned.values()) - 1.0) < 1e-6:
                    weights = cleaned
            except (ValueError, TypeError):
                pass  # corrupt settings fall back to the approved defaults
        elif setting.key == "service_radius_km" and setting.value_json:
            try:
                value = float(setting.value_json)
                if value > 0:
                    radius = value
            except (ValueError, TypeError):
                pass
    return weights, radius


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres (addendum §6)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def valid_coordinates(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def timeliness_score(required_by: date | None, today: date) -> float:
    """1.0 within 14 days, linear decay to 0.2 at 60+ days, 0.5 without a date."""
    if required_by is None:
        return 0.5
    days = (required_by - today).days
    if days <= TIMELINESS_FULL_DAYS:
        return 1.0
    if days >= TIMELINESS_FLOOR_DAYS:
        return TIMELINESS_FLOOR_SCORE
    span = TIMELINESS_FLOOR_DAYS - TIMELINESS_FULL_DAYS
    fraction = (days - TIMELINESS_FULL_DAYS) / span
    return round(1.0 - fraction * (1.0 - TIMELINESS_FLOOR_SCORE), 4)


def quantity_fit_score(donation_quantity: float, remaining: float) -> float:
    if donation_quantity <= 0 or remaining <= 0:
        return 0.0
    return round(min(donation_quantity, remaining) / max(donation_quantity, remaining), 4)


def _build_reasons(
    *,
    org: Organization,
    need: OrganizationNeed,
    compatibility: Factor,
    urgency: Factor,
    distance: Factor,
    distance_km: float | None,
    quantity_fit: Factor,
    timeliness: Factor,
    required_by: date | None,
    today: date,
) -> list[str]:
    reasons: list[str] = []
    reasons.append(
        f"Verified organization with an active need for {need.category.display_name.lower()}"
        + (" (related category)" if compatibility.score == RELATED_SCORE else "")
        + "."
    )
    reasons.append(f"Need urgency is {need.urgency}.")
    if distance_km is not None:
        reasons.append(f"About {distance_km:.1f} km away from the pickup area.")
    else:
        reasons.append(DISTANCE_COULD_NOT_BE_CALCULATED)
    reasons.append(
        f"Offered quantity fits the remaining need of {need.remaining_quantity:.4g} {need.unit}."
    )
    if required_by is None:
        reasons.append("No required-by date given.")
    elif (required_by - today).days <= TIMELINESS_FULL_DAYS:
        reasons.append(f"Required by {required_by.isoformat()} — within 14 days.")
    else:
        reasons.append(f"Required by {required_by.isoformat()}.")
    return reasons


def compute_matches(db: Session, donation: Donation, today: date | None = None) -> dict:
    """Compute the full eligibility + ranking result for one donation.

    Returns a JSON-ready dict: eligible candidates (ranked, with factors and
    reasons) plus exclusion reason counts for transparency. Creates nothing —
    offers belong to M4.
    """
    if donation.status not in DONATION_STATUSES or donation.status == "cancelled":
        raise MatchingInputError("Cancelled donations cannot be matched.")
    if donation.status in ("accepted", "pickup_scheduled", "picked_up", "completed"):
        raise MatchingInputError(
            "This donation is already matched with an organization."
        )

    today = today or date.today()
    weights, service_radius_km = load_settings(db)

    # Donor-CONFIRMED category is authoritative (client AI fields are ignored).
    category_id = donation.category_id

    exact_ids = {
        row.need_category_id
        for row in db.scalars(
            select(DonationCompatibility).where(
                DonationCompatibility.donation_category_id == category_id,
                DonationCompatibility.factor == "exact",
            )
        ).all()
    }
    related_ids = {
        row.need_category_id
        for row in db.scalars(
            select(DonationCompatibility).where(
                DonationCompatibility.donation_category_id == category_id,
                DonationCompatibility.factor == "related",
            )
        ).all()
    }
    exact_ids.add(category_id)  # self-compatibility always exact

    organizations = db.scalars(select(Organization)).all()
    needs_by_org: dict[str, list[OrganizationNeed]] = {}
    for need in db.scalars(select(OrganizationNeed)).all():
        needs_by_org.setdefault(need.organization_id, []).append(need)

    eligible: list[MatchCandidate] = []
    excluded_counts: dict[str, int] = {}

    def exclude(reason_code: str) -> None:
        excluded_counts[reason_code] = excluded_counts.get(reason_code, 0) + 1

    for org in organizations:
        if org.verification_status != VERIFICATION_VERIFIED:
            exclude("organization_not_verified")
            continue
        org_needs = needs_by_org.get(org.id, [])
        org_candidates = []
        org_rejected_need_reasons: dict[str, int] = {}
        for need in org_needs:
            if need.status != NEED_ACTIVE:
                org_rejected_need_reasons["need_not_active"] = (
                    org_rejected_need_reasons.get("need_not_active", 0) + 1
                )
                continue
            if need.quantity_fulfilled >= need.quantity_required or need.remaining_quantity <= 0:
                org_rejected_need_reasons["need_fully_funded"] = (
                    org_rejected_need_reasons.get("need_fully_funded", 0) + 1
                )
                continue
            if need.category_id == category_id or need.category_id in exact_ids:
                factor = EXACT_SCORE
            elif need.category_id in related_ids:
                factor = RELATED_SCORE
            else:
                org_rejected_need_reasons["category_incompatible"] = (
                    org_rejected_need_reasons.get("category_incompatible", 0) + 1
                )
                continue
            org_candidates.append((need, factor))

        if not org_candidates:
            if org_rejected_need_reasons:
                for reason, count in org_rejected_need_reasons.items():
                    exclude(reason)
            else:
                exclude("no_active_need")
            continue

        for need, compatibility_value in org_candidates:
            # Distance: only exclude when a VALID distance exceeds the radius.
            distance_km: float | None = None
            if valid_coordinates(donation.pickup_latitude, donation.pickup_longitude) and valid_coordinates(
                org.latitude, org.longitude
            ):
                distance_km = round(
                    haversine_km(
                        donation.pickup_latitude,  # type: ignore[arg-type]
                        donation.pickup_longitude,  # type: ignore[arg-type]
                        org.latitude,  # type: ignore[arg-type]
                        org.longitude,  # type: ignore[arg-type]
                    ),
                    2,
                )
                if distance_km > service_radius_km:
                    exclude("outside_service_radius")
                    continue

            compatibility = Factor(compatibility_value, weights["compatibility"])
            urgency = Factor(URGENCY_SCORES.get(need.urgency, 0.5), weights["urgency"])
            if distance_km is not None:
                distance_score = max(0.0, 1.0 - distance_km / service_radius_km)
                distance = Factor(round(distance_score, 4), weights["distance"])
            else:
                distance = Factor(NEUTRAL_DISTANCE_SCORE, weights["distance"])
            quantity_fit = Factor(
                quantity_fit_score(donation.quantity, need.remaining_quantity),
                weights["quantity_fit"],
            )
            timeliness = Factor(
                timeliness_score(need.required_by, today), weights["timeliness"]
            )

            weighted_total = (
                compatibility.weighted
                + urgency.weighted
                + distance.weighted
                + quantity_fit.weighted
                + timeliness.weighted
            )
            reasons = _build_reasons(
                org=org,
                need=need,
                compatibility=compatibility,
                urgency=urgency,
                distance=distance,
                distance_km=distance_km,
                quantity_fit=quantity_fit,
                timeliness=timeliness,
                required_by=need.required_by,
                today=today,
            )
            eligible.append(
                MatchCandidate(
                    organization_id=org.id,
                    organization_name=org.name,
                    verification_status=org.verification_status,
                    need_id=need.id,
                    need_title=need.title,
                    need_category_code=need.category.code,
                    remaining_quantity=need.remaining_quantity,
                    unit=need.unit,
                    distance_km=distance_km,
                    rank=0,
                    score=round(weighted_total * 100, 1),
                    factors={
                        "compatibility": compatibility,
                        "urgency": urgency,
                        "distance": distance,
                        "quantity_fit": quantity_fit,
                        "timeliness": timeliness,
                    },
                    reasons=reasons,
                )
            )

    # Deterministic ordering: score desc, need created_at asc, organization id asc.
    need_created = {need.id: need.created_at for need in db.scalars(select(OrganizationNeed)).all()}
    eligible.sort(
        key=lambda candidate: (
            -candidate.score,
            need_created.get(candidate.need_id, datetime.max),
            candidate.organization_id,
        )
    )
    for rank, candidate in enumerate(eligible, start=1):
        candidate.rank = rank

    return {
        "donation_id": donation.id,
        "service_radius_km": service_radius_km,
        "eligible": [
            {
                "rank": candidate.rank,
                "organization_id": candidate.organization_id,
                "organization_name": candidate.organization_name,
                "verification_status": candidate.verification_status,
                "need_id": candidate.need_id,
                "need_title": candidate.need_title,
                "need_category_code": candidate.need_category_code,
                "remaining_quantity": candidate.remaining_quantity,
                "unit": candidate.unit,
                "distance_km": candidate.distance_km,
                "score": candidate.score,
                "factors": {
                    name: {
                        "score": factor.score,
                        "weight": factor.weight,
                        "weighted": factor.weighted,
                    }
                    for name, factor in candidate.factors.items()
                },
                "reasons": candidate.reasons,
            }
            for candidate in eligible
        ],
        "excluded": [
            {"reason_code": reason, "count": count}
            for reason, count in sorted(excluded_counts.items())
        ],
    }
