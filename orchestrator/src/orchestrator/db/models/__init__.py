"""PostgreSQL models for DaantShaant.

Importing this module ensures all models are registered with Base.metadata.
"""

from orchestrator.db.models.identity import User, AuthSession, PatientProfile
from orchestrator.db.models.dentists import Dentist
from orchestrator.db.models.dental import Scan, ScanFinding, ClinicalReport
from orchestrator.db.models.chat import Conversation, Message
from orchestrator.db.models.commerce import (
    Product,
    ProductRecommendation,
    Order,
    DentistRecommendation,
    AppointmentRequest,
    CommissionRecord,
)

__all__ = [
    "User",
    "AuthSession",
    "PatientProfile",
    "Dentist",
    "Scan",
    "ScanFinding",
    "ClinicalReport",
    "Conversation",
    "Message",
    "Product",
    "ProductRecommendation",
    "Order",
    "DentistRecommendation",
    "AppointmentRequest",
    "CommissionRecord",
]
