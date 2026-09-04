"""Pydantic models for Dentist Portal."""

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator
from enum import Enum


class UserRole(str, Enum):
    DENTIST = "dentist"
    PATIENT = "patient"
    ADMIN = "admin"


class ProductCategory(str, Enum):
    TOOTHBRUSH = "toothbrush"
    TOOTHPASTE = "toothpaste"
    MOUTHWASH = "mouthwash"
    FLOSS = "floss"
    WHITENING = "whitening"
    ORTHODONTIC = "orthodontic"
    OTHER = "other"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


_PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")


class _PasswordMixin(BaseModel):
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class _ProfileMixin(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    location: str = Field(min_length=2, max_length=200)
    profile_image: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.strip()
        if not _PHONE_RE.match(cleaned):
            raise ValueError("Invalid phone number format")
        return cleaned

    @field_validator("first_name", "last_name", "location")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


class PatientRegisterRequest(_ProfileMixin, _PasswordMixin):
    """Patient registration payload."""


class AdminRegisterRequest(_ProfileMixin, _PasswordMixin):
    """Admin registration payload."""


class DentistRegisterRequest(_ProfileMixin, _PasswordMixin):
    """Dentist registration payload."""
    degree: str = Field(min_length=2, max_length=120)
    degree_year: int = Field(ge=1950, le=2030)
    institution: str = Field(min_length=2, max_length=200)
    specialized_training: Optional[str] = Field(default=None, max_length=500)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    user_id: str
    name: str
    email: str
    first_name: str
    last_name: str
    profile_image: str


class UserProfileResponse(BaseModel):
    user_id: str
    email: str
    role: UserRole
    first_name: str
    last_name: str
    name: str
    phone: str
    location: str
    profile_image: str
    degree: Optional[str] = None
    degree_year: Optional[int] = None
    institution: Optional[str] = None
    specialized_training: Optional[str] = None
    is_verified: bool = False
    created_at: Optional[datetime] = None


# --- Legacy auth (backward compatible with /portal page) ---

class LegacyRegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    role: UserRole = UserRole.PATIENT
    clinic_name: Optional[str] = None
    license_number: Optional[str] = None


# --- Product Models ---

class ProductUpload(BaseModel):
    name: str
    category: ProductCategory
    price: float
    raw_description: str
    images: list[str] = []


class ProductOut(BaseModel):
    product_id: str
    name: str
    category: str
    price: float
    ai_description: str
    problems_solved: list[str]
    images: list[str]
    dentist_id: str
    status: str
    view_count: int = 0
    recommendation_count: int = 0
    created_at: datetime


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    raw_description: Optional[str] = None
    status: Optional[ProductStatus] = None


# --- Recommendation Models ---

class RecommendRequest(BaseModel):
    issue: str
    session_id: Optional[str] = None


class RecommendResponse(BaseModel):
    session_id: str
    recommendations: str


# --- Dentist recommendation (map) ---

class DentistRecommendRequest(BaseModel):
    issue: str = Field(min_length=1, max_length=200)
    lat: Optional[float] = None
    lng: Optional[float] = None
    severity: Optional[str] = "moderate"
    scan_id: Optional[str] = None
    session_id: Optional[str] = None
    radius_km: Optional[float] = Field(default=25.0, ge=1.0, le=100.0)
    location_label: Optional[str] = None


class DentistPin(BaseModel):
    tier: str  # "platform" | "general"
    source: Optional[str] = "platform"  # "platform" | "osm" | "curated" | "foursquare" | "geoapify"
    dentist_id: Optional[str] = None
    place_id: Optional[str] = None
    name: str
    lat: float
    lng: float
    address: str = ""
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    whatsapp: Optional[str] = None
    linkedin: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None
    distance_km: float = 0.0
    specialties: list[str] = []
    is_partner: bool = False
    is_verified: bool = False
    is_registered: bool = False
    is_best: bool = False
    rank: int = 0
    clinic_name: str = ""
    degree: Optional[str] = None
    profile_image: Optional[str] = None
    recommendation_reason: str = ""
    sources: list[str] = []
    source_count: int = 1


class DentistRecommendResponse(BaseModel):
    session_id: str
    issue: str
    patient_lat: float
    patient_lng: float
    dentists: list[DentistPin]
    search_radius_km: Optional[float] = None


class BookConsultationRequest(BaseModel):
    dentist_id: str
    issue: str = Field(min_length=1, max_length=200)
    scan_id: Optional[str] = None
    session_id: Optional[str] = None
    message: Optional[str] = Field(default=None, max_length=1000)


class BookConsultationResponse(BaseModel):
    appointment_id: str
    status: str
    message: str
