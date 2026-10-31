"""All SQLAlchemy models. Importing this package registers every table on
`Base.metadata` (required by Alembic autogenerate and test fixtures)."""

from app.models.user import DonorProfile, User
from app.models.organization import Organization, OrganizationDocument
from app.models.donation import (
    Donation,
    DonationCategory,
    DonationCompatibility,
    DonationImage,
    DonationSubcategory,
)
from app.models.need import OrganizationNeed
from app.models.offer import DonationOffer, DonationStatusHistory
from app.models.support import AuditLog, Notification, PaymentRecord
from app.models.ml import ModelEvaluation, ModelVersion
from app.models.app_settings import Setting

__all__ = [
    "User",
    "DonorProfile",
    "Organization",
    "OrganizationDocument",
    "DonationCategory",
    "DonationSubcategory",
    "DonationCompatibility",
    "Donation",
    "DonationImage",
    "OrganizationNeed",
    "DonationOffer",
    "DonationStatusHistory",
    "Notification",
    "PaymentRecord",
    "AuditLog",
    "ModelVersion",
    "ModelEvaluation",
    "Setting",
]
