"""Metadata-level tests for PostgreSQL models.

These tests make ZERO remote database connections.
They validate model definitions, table names, column types, indexes,
and foreign keys at the SQLAlchemy metadata level only.
"""

import uuid

import pytest
from sqlalchemy import inspect, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import Numeric

# Import models — this also registers them with Base.metadata
from orchestrator.db.base import Base
from orchestrator.db.models import (
    User,
    AuthSession,
    PatientProfile,
    Dentist,
    Scan,
    ScanFinding,
    ClinicalReport,
    Conversation,
    Message,
    Product,
    ProductRecommendation,
    Order,
    DentistRecommendation,
    AppointmentRequest,
    CommissionRecord,
)


EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "patient_profiles",
    "dentists",
    "scans",
    "scan_findings",
    "clinical_reports",
    "conversations",
    "messages",
    "products",
    "product_recommendations",
    "orders",
    "dentist_recommendations",
    "appointment_requests",
    "commission_records",
}


class TestModelImports:
    """Verify all models are importable and registered."""

    def test_all_15_tables_in_metadata(self):
        actual = set(Base.metadata.tables.keys())
        assert actual == EXPECTED_TABLES, f"Missing tables: {EXPECTED_TABLES - actual}"

    def test_table_count(self):
        assert len(Base.metadata.tables) == 15


class TestUUIDPrimaryKeys:
    """Verify all tables use UUID primary keys."""

    @pytest.mark.parametrize(
        "model",
        [User, AuthSession, Dentist, Scan, ScanFinding, ClinicalReport,
         Conversation, Message, Product, ProductRecommendation, Order,
         DentistRecommendation, AppointmentRequest, CommissionRecord],
    )
    def test_uuid_pk(self, model):
        mapper = inspect(model)
        pk_cols = mapper.primary_key
        assert len(pk_cols) == 1
        pk = pk_cols[0]
        assert isinstance(pk.type, UUID), f"{model.__name__}.id should be UUID, got {type(pk.type)}"

    def test_patient_profile_pk_is_fk(self):
        """PatientProfile uses user_id as PK (1:1 with users)."""
        mapper = inspect(PatientProfile)
        pk_cols = mapper.primary_key
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "user_id"
        assert isinstance(pk_cols[0].type, UUID)


class TestUsersModel:
    """Verify users table specifics."""

    def test_email_unique(self):
        mapper = inspect(User)
        email_col = mapper.columns["email"]
        assert email_col.unique is True

    def test_role_column_exists(self):
        mapper = inspect(User)
        assert "role" in mapper.columns

    def test_password_hash_exists(self):
        mapper = inspect(User)
        assert "password_hash" in mapper.columns

    def test_profile_image_url_is_text_unbounded(self):
        """profile_image_url must be TEXT to hold base64 data-URIs (~60 KB+)."""
        mapper = inspect(User)
        col = mapper.columns["profile_image_url"]
        assert isinstance(col.type, Text), (
            f"profile_image_url should be Text, got {type(col.type)}"
        )

    def test_profile_image_url_accepts_long_data_uri(self):
        """Simulate assigning a realistic base64 data-URI to the model."""
        # ~70 KB synthetic data-URI — well beyond old VARCHAR(500) limit
        fake_data_uri = "data:image/jpeg;base64," + "A" * 70_000
        user = User(
            email="img-test@example.com",
            password_hash="hash",
            role="patient",
            profile_image_url=fake_data_uri,
        )
        assert user.profile_image_url == fake_data_uri
        assert len(user.profile_image_url) > 500


class TestDentistModel:
    """Verify dentist table specifics."""

    def test_owner_user_id_unique_index(self):
        table = Base.metadata.tables["dentists"]
        index_names = [idx.name for idx in table.indexes]
        assert "ix_dentists_owner_user_id" in index_names
        # Verify it's unique
        for idx in table.indexes:
            if idx.name == "ix_dentists_owner_user_id":
                assert idx.unique is True

    def test_source_external_index(self):
        table = Base.metadata.tables["dentists"]
        index_names = [idx.name for idx in table.indexes]
        assert "ix_dentists_source_external" in index_names


class TestJSONBColumns:
    """Verify important JSONB columns exist."""

    @pytest.mark.parametrize(
        "table_name,column_name",
        [
            ("patient_profiles", "preferences"),
            ("dentists", "specialties"),
            ("dentists", "qualifications"),
            ("scans", "mechanical_quality_issues"),
            ("scans", "relevance_result"),
            ("scan_findings", "raw_ai_metadata"),
            ("clinical_reports", "possible_concerns"),
            ("clinical_reports", "recommended_actions"),
            ("clinical_reports", "evidence_refs"),
            ("messages", "evidence_refs"),
            ("products", "problems_solved"),
            ("products", "images"),
            ("orders", "items"),
            ("dentist_recommendations", "results"),
        ],
    )
    def test_jsonb_column(self, table_name, column_name):
        table = Base.metadata.tables[table_name]
        col = table.columns[column_name]
        assert isinstance(col.type, JSONB), f"{table_name}.{column_name} should be JSONB"


class TestNumericMoneyColumns:
    """Verify money columns use Numeric type."""

    @pytest.mark.parametrize(
        "table_name,column_name",
        [
            ("products", "price"),
            ("orders", "total"),
            ("commission_records", "commission_amount"),
            ("commission_records", "commission_rate"),
            ("dentists", "commission_rate"),
        ],
    )
    def test_numeric_column(self, table_name, column_name):
        table = Base.metadata.tables[table_name]
        col = table.columns[column_name]
        assert isinstance(col.type, Numeric), f"{table_name}.{column_name} should be Numeric"


class TestForeignKeys:
    """Verify important foreign key relationships."""

    def test_auth_sessions_fk_users(self):
        table = Base.metadata.tables["auth_sessions"]
        fk_targets = {fk.target_fullname for fk in table.foreign_keys}
        assert "users.id" in fk_targets

    def test_scans_fk_users(self):
        table = Base.metadata.tables["scans"]
        fk_targets = {fk.target_fullname for fk in table.foreign_keys}
        assert "users.id" in fk_targets

    def test_messages_fk_conversations(self):
        table = Base.metadata.tables["messages"]
        fk_targets = {fk.target_fullname for fk in table.foreign_keys}
        assert "conversations.id" in fk_targets

    def test_products_fk_dentists(self):
        table = Base.metadata.tables["products"]
        fk_targets = {fk.target_fullname for fk in table.foreign_keys}
        assert "dentists.id" in fk_targets

    def test_commission_fk_appointment(self):
        table = Base.metadata.tables["commission_records"]
        fk_targets = {fk.target_fullname for fk in table.foreign_keys}
        assert "appointment_requests.id" in fk_targets


class TestImportantIndexes:
    """Verify practical indexes exist."""

    def test_scans_patient_index(self):
        table = Base.metadata.tables["scans"]
        index_names = [idx.name for idx in table.indexes]
        assert "ix_scans_patient_user_id" in index_names

    def test_conversations_patient_index(self):
        table = Base.metadata.tables["conversations"]
        index_names = [idx.name for idx in table.indexes]
        assert "ix_conversations_patient_user_id" in index_names

    def test_messages_conversation_index(self):
        table = Base.metadata.tables["messages"]
        index_names = [idx.name for idx in table.indexes]
        assert "ix_messages_conversation_id" in index_names


class TestEngineConfiguration:
    """Verify engine/session can be constructed without real DB."""

    def test_engine_creation(self):
        from sqlalchemy.ext.asyncio import create_async_engine
        engine = create_async_engine("postgresql+asyncpg://fake:fake@localhost:5432/fake")
        assert engine is not None
        assert engine.url.drivername == "postgresql+asyncpg"

    def test_session_factory_creation(self):
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        engine = create_async_engine("postgresql+asyncpg://fake:fake@localhost:5432/fake")
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        assert factory is not None


class TestConfigDoesNotExposeSecrets:
    """Verify config doesn't hard-code database credentials."""

    def test_no_password_in_default_config(self):
        from orchestrator.config import PostgresSettings
        s = PostgresSettings(_env_file=None)
        assert "password" not in s.database_url.lower() or s.database_url == ""

    def test_migration_url_fallback(self):
        from orchestrator.config import PostgresSettings
        s = PostgresSettings(_env_file=None)
        # When both are empty, get_migration_url returns empty string
        assert s.get_migration_url() == ""


class TestMigrationImport:
    """Verify the baseline migration can be imported."""

    def test_migration_imports(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "001_baseline.py"
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

        spec = importlib.util.spec_from_file_location("001_baseline", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert mod.revision == "001_baseline"


class TestMigration003:
    """Verify the profile_image_text migration can be imported."""

    def test_migration_imports(self):
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parent.parent
            / "alembic"
            / "versions"
            / "003_profile_image_text.py"
        )
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

        spec = importlib.util.spec_from_file_location("003_profile_image_text", migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert mod.revision == "003_profile_image_text"
        assert mod.down_revision == "002_domain_compatibility"
