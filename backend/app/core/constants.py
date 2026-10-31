"""Fixed vocabulary shared by models, schemas, and services.

The five classifier classes are fixed (addendum correction #3): admin users may
manage display subcategories, never these codes. Donation statuses exclude
`expired` (addendum correction #7 — no automatic expiry in this release).
"""

ROLE_DONOR = "donor"
ROLE_ORGANIZATION = "organization"
ROLE_ADMIN = "admin"
USER_ROLES = (ROLE_DONOR, ROLE_ORGANIZATION, ROLE_ADMIN)

ACCOUNT_ACTIVE = "active"
ACCOUNT_INACTIVE = "inactive"
ACCOUNT_SUSPENDED = "suspended"
ACCOUNT_STATUSES = (ACCOUNT_ACTIVE, ACCOUNT_INACTIVE, ACCOUNT_SUSPENDED)

DONATION_PENDING = "pending"
DONATION_OFFERED = "offered"
DONATION_ACCEPTED = "accepted"
DONATION_PICKUP_SCHEDULED = "pickup_scheduled"
DONATION_PICKED_UP = "picked_up"
DONATION_COMPLETED = "completed"
DONATION_CANCELLED = "cancelled"
DONATION_STATUSES = (
    DONATION_PENDING,
    DONATION_OFFERED,
    DONATION_ACCEPTED,
    DONATION_PICKUP_SCHEDULED,
    DONATION_PICKED_UP,
    DONATION_COMPLETED,
    DONATION_CANCELLED,
)

OFFER_SENT = "sent"
OFFER_ACCEPTED = "accepted"
OFFER_DECLINED = "declined"
OFFER_WITHDRAWN = "withdrawn"
OFFER_STATUSES = (OFFER_SENT, OFFER_ACCEPTED, OFFER_DECLINED, OFFER_WITHDRAWN)

NEED_ACTIVE = "active"
NEED_PAUSED = "paused"
NEED_CLOSED = "closed"
NEED_FULFILLED = "fulfilled"
NEED_STATUSES = (NEED_ACTIVE, NEED_PAUSED, NEED_CLOSED, NEED_FULFILLED)

URGENCY_LOW = "low"
URGENCY_MEDIUM = "medium"
URGENCY_HIGH = "high"
URGENCY_CRITICAL = "critical"
URGENCIES = (URGENCY_LOW, URGENCY_MEDIUM, URGENCY_HIGH, URGENCY_CRITICAL)

UNITS = ("kg", "pieces", "packets", "sets", "litres")
CONDITIONS = ("new", "good", "fair")

VERIFICATION_PENDING = "pending_verification"
VERIFICATION_VERIFIED = "verified"
VERIFICATION_REJECTED = "rejected"
VERIFICATION_SUSPENDED = "suspended"
VERIFICATION_STATUSES = (
    VERIFICATION_PENDING,
    VERIFICATION_VERIFIED,
    VERIFICATION_REJECTED,
    VERIFICATION_SUSPENDED,
)

UPI_STATUSES = ("none", "pending_approval", "approved", "rejected")

PAYMENT_SUBMITTED = "submitted_unverified"
PAYMENT_VERIFIED = "verified"
PAYMENT_REJECTED = "rejected"
PAYMENT_STATUSES = (PAYMENT_SUBMITTED, PAYMENT_VERIFIED, PAYMENT_REJECTED)

MODEL_KIND_IMAGE = "image_classifier"
MODEL_KIND_ACCEPTANCE = "acceptance_model"
MODEL_KINDS = (MODEL_KIND_IMAGE, MODEL_KIND_ACCEPTANCE)

# (code, display name) — fixed classifier output classes.
CLASSIFIER_CLASSES: tuple[tuple[str, str], ...] = (
    ("clothing", "Clothing"),
    ("grains_rice", "Grains/Rice"),
    ("packaged_food", "Packaged Food"),
    ("utensils", "Utensils"),
    ("other", "Other"),
)

# Example display subcategories seeded as base data (addendum §3).
SUBCATEGORY_EXAMPLES: dict[str, tuple[str, ...]] = {
    "clothing": ("Men's", "Women's", "Children's"),
    "grains_rice": ("Rice", "Wheat", "Pulses"),
    "packaged_food": ("Biscuits", "Canned Food", "Packaged Items"),
    "utensils": ("Plates", "Bowls", "Cooking Vessels"),
    "other": ("Miscellaneous",),
}

# Explainable matching weights (settings-table defaults, §6.4).
DEFAULT_MATCHING_WEIGHTS: dict[str, float] = {
    "compatibility": 0.30,
    "urgency": 0.25,
    "distance": 0.20,
    "quantity_fit": 0.15,
    "timeliness": 0.10,
}
