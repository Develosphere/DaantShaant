"""PostgreSQL baseline — create all Phase 1A relational tables.

Revision ID: 001_baseline
Revises: None
Create Date: 2026-09-01

This is the initial baseline migration that creates all 15 tables
for the DaantShaant PostgreSQL foundation (Phase 1A).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="patient"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("profile_image_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- auth_sessions ---
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_refresh_token_hash", "auth_sessions", ["refresh_token_hash"])

    # --- patient_profiles ---
    op.create_table(
        "patient_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("location_text", sa.String(300), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("preferences", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- dentists ---
    op.create_table(
        "dentists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="platform"),
        sa.Column("external_id", sa.String(200), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("clinic_name", sa.String(200), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("address", sa.String(400), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float, nullable=True),
        sa.Column("longitude", sa.Float, nullable=True),
        sa.Column("specialties", postgresql.JSONB, nullable=True),
        sa.Column("degree", sa.String(100), nullable=True),
        sa.Column("degree_year", sa.Integer, nullable=True),
        sa.Column("institution", sa.String(200), nullable=True),
        sa.Column("specialized_training", sa.String(500), nullable=True),
        sa.Column("qualifications", postgresql.JSONB, nullable=True),
        sa.Column("rating", sa.Float, nullable=True),
        sa.Column("review_count", sa.Integer, nullable=True),
        sa.Column("is_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_partner", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB, nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dentists_owner_user_id", "dentists", ["owner_user_id"], unique=True)
    op.create_index("ix_dentists_source_external", "dentists", ["source", "external_id"])
    op.create_index("ix_dentists_city", "dentists", ["city"])

    # --- scans ---
    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("input_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("media_object_key", sa.String(500), nullable=True),
        sa.Column("mechanical_quality_score", sa.Float, nullable=True),
        sa.Column("mechanical_quality_issues", postgresql.JSONB, nullable=True),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("relevance_result", postgresql.JSONB, nullable=True),
        sa.Column("ai_provider", sa.String(50), nullable=True),
        sa.Column("ai_model", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scans_patient_user_id", "scans", ["patient_user_id"])
    op.create_index("ix_scans_created_at", "scans", ["created_at"])

    # --- scan_findings ---
    op.create_table(
        "scan_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("finding_code", sa.String(50), nullable=False),
        sa.Column("region", sa.String(100), nullable=True),
        sa.Column("tooth_reference", sa.String(20), nullable=True),
        sa.Column("observation", sa.String(500), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("visibility", sa.Float, nullable=True),
        sa.Column("raw_ai_metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scan_findings_scan_id", "scan_findings", ["scan_id"])

    # --- clinical_reports ---
    op.create_table(
        "clinical_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL"), nullable=False),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("verdict", sa.String(50), nullable=False),
        sa.Column("urgency_level", sa.String(20), nullable=True),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("possible_concerns", postgresql.JSONB, nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB, nullable=True),
        sa.Column("recommended_specialist", sa.String(100), nullable=True),
        sa.Column("limitations", postgresql.JSONB, nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=True),
        sa.Column("agent_trace_summary", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_clinical_reports_scan_id", "clinical_reports", ["scan_id"])
    op.create_index("ix_clinical_reports_patient_user_id", "clinical_reports", ["patient_user_id"])

    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("active_scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("active_report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversations_patient_user_id", "conversations", ["patient_user_id"])

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])

    # --- products ---
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dentist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dentists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("raw_description", sa.Text, nullable=True),
        sa.Column("ai_description", sa.Text, nullable=True),
        sa.Column("problems_solved", postgresql.JSONB, nullable=True),
        sa.Column("images", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("view_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("recommendation_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_products_dentist_id", "products", ["dentist_id"])

    # --- product_recommendations ---
    op.create_table(
        "product_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issue", sa.String(200), nullable=True),
        sa.Column("recommendations", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dentist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("items", postgresql.JSONB, nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- dentist_recommendations ---
    op.create_table(
        "dentist_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("specialist", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("patient_lat", sa.Float, nullable=True),
        sa.Column("patient_lng", sa.Float, nullable=True),
        sa.Column("results", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dentist_recommendations_patient_user_id", "dentist_recommendations", ["patient_user_id"])

    # --- appointment_requests ---
    op.create_table(
        "appointment_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("patient_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=False),
        sa.Column("dentist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("scans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinical_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("preferred_time", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointment_requests_patient_user_id", "appointment_requests", ["patient_user_id"])
    op.create_index("ix_appointment_requests_dentist_id", "appointment_requests", ["dentist_id"])

    # --- commission_records ---
    op.create_table(
        "commission_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("appointment_requests.id", ondelete="SET NULL"), nullable=False),
        sa.Column("dentist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("dentists.id", ondelete="SET NULL"), nullable=False),
        sa.Column("commission_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("commission_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("commission_records")
    op.drop_table("appointment_requests")
    op.drop_table("dentist_recommendations")
    op.drop_table("orders")
    op.drop_table("product_recommendations")
    op.drop_table("products")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("clinical_reports")
    op.drop_table("scan_findings")
    op.drop_table("scans")
    op.drop_table("dentists")
    op.drop_table("patient_profiles")
    op.drop_table("auth_sessions")
    op.drop_table("users")
