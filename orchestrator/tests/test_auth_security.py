"""Focused security tests that require no remote services."""

from pathlib import Path
from uuid import uuid4

from orchestrator.config import settings
from orchestrator.dentist_portal.auth import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from orchestrator.dentist_portal.routes_auth import router as auth_router


def test_passwords_use_argon2id():
    password_hash = hash_password("CorrectHorse123")
    assert password_hash.startswith("$argon2id$")
    assert verify_password("CorrectHorse123", password_hash)
    assert not verify_password("wrong", password_hash)


def test_refresh_tokens_are_opaque_and_only_hash_is_stable():
    first = generate_refresh_token()
    second = generate_refresh_token()
    assert first != second
    assert len(first) >= 64
    assert len(hash_refresh_token(first)) == 64
    assert first not in hash_refresh_token(first)


def test_access_token_uses_configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "unit-test-secret-with-sufficient-entropy")
    user_id = uuid4()
    token = create_access_token(user_id, "patient@example.test", "patient")
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["role"] == "patient"
    assert payload["type"] == "access"


def test_public_admin_registration_is_rejected():
    paths = {
        (route.path, method)
        for route in auth_router.routes
        for method in (route.methods or set())
    }
    assert ("/portal/auth/admin/register", "POST") not in paths


def test_runtime_has_no_legacy_database_imports():
    source_root = Path(__file__).resolve().parents[1] / "src" / "orchestrator"
    forbidden = ("motor", "pymongo", "mongodb", "objectid", "from bson", "import bson")
    matches = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        if any(term in text for term in forbidden):
            matches.append(path.relative_to(source_root).as_posix())
    assert matches == []


def test_frontend_has_no_random_clinical_identity():
    repository_root = Path(__file__).resolve().parents[2]
    source = (repository_root / "apps" / "web" / "lib" / "user-id.ts").read_text(
        encoding="utf-8"
    )
    assert "randomUUID" not in source
    assert "clinical_user" not in source
