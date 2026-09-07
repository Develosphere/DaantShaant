"""Repository-level regression test: Complete Hugging Face Removal (Phase 12A Final).

Verifies that the chatbot request path and all orchestrator runtime modules
have ZERO dependency on:
- transformers
- sentence_transformers
- sentence-transformers
- huggingface_hub
- hf_hub_download
- snapshot_download
- AutoTokenizer
- AutoModel
"""

import ast
import os
import sys
from pathlib import Path

import pytest

ORCHESTRATOR_SRC = Path(__file__).resolve().parents[1] / "src" / "orchestrator"

BANNED_MODULE_NAMES = {
    "transformers",
    "sentence_transformers",
    "sentence-transformers",
    "huggingface_hub",
}

BANNED_SYMBOLS = {
    "AutoTokenizer",
    "AutoModel",
    "AutoModelForCausalLM",
    "AutoModelForSequenceClassification",
    "SentenceTransformer",
    "hf_hub_download",
    "snapshot_download",
}


def test_chatbot_runtime_does_not_import_huggingface():
    """Verify that importing chat and orchestrator modules does not pull in Hugging Face."""
    # Ensure Hugging Face packages are not loaded into sys.modules
    for mod in list(sys.modules.keys()):
        if any(banned in mod for banned in ("transformers", "sentence_transformers", "huggingface_hub")):
            sys.modules.pop(mod, None)

    # Import Central Dentist modules
    from orchestrator.central_dentist import (
        CentralDentistIntent,
        CentralDentistState,
        analyze_message,
        central_dentist_graph,
    )
    from orchestrator.central_dentist.fast_path import format_fast_path_response
    from orchestrator.central_dentist.knowledge import lookup_dental_knowledge
    from orchestrator.central_dentist.prompts import clean_response
    from orchestrator.central_dentist.retrieval import retrieve_latest_screening
    from orchestrator.chat_service import send_message
    from orchestrator.conversation_engine import ConversationEngine

    # Check sys.modules after importing (top-level or child package of banned libraries)
    banned_prefixes = ("transformers", "sentence_transformers", "huggingface_hub")
    loaded_banned = [
        mod for mod in sys.modules
        if any(mod == b or mod.startswith(f"{b}.") for b in banned_prefixes)
    ]
    assert not loaded_banned, f"Banned Hugging Face modules loaded at runtime: {loaded_banned}"


def test_static_ast_scan_for_banned_imports():
    """Static AST scan of all python files in orchestrator/src/orchestrator."""
    violations = []

    for root, _, files in os.walk(ORCHESTRATOR_SRC):
        for file in files:
            if not file.endswith(".py"):
                continue
            file_path = Path(root) / file
            rel_path = file_path.relative_to(ORCHESTRATOR_SRC)

            try:
                content = file_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(file_path))
            except Exception as e:
                pytest.fail(f"Failed to parse {rel_path}: {e}")

            for node in ast.walk(tree):
                # import foo
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top_pkg = alias.name.split(".")[0]
                        if top_pkg in BANNED_MODULE_NAMES:
                            violations.append(f"{rel_path}:{node.lineno}: import {alias.name}")

                # from foo import bar
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        top_pkg = node.module.split(".")[0]
                        if top_pkg in BANNED_MODULE_NAMES:
                            violations.append(f"{rel_path}:{node.lineno}: from {node.module} import ...")
                    for alias in node.names:
                        if alias.name in BANNED_SYMBOLS:
                            violations.append(f"{rel_path}:{node.lineno}: imported symbol {alias.name}")

                # calls like hf_hub_download(...)
                elif isinstance(node, ast.Call):
                    func = node.func
                    func_name = None
                    if isinstance(func, ast.Name):
                        func_name = func.id
                    elif isinstance(func, ast.Attribute):
                        func_name = func.attr
                    if func_name in BANNED_SYMBOLS:
                        violations.append(f"{rel_path}:{node.lineno}: call to {func_name}()")

    assert not violations, "Found Hugging Face / sentence-transformers references:\n" + "\n".join(violations)


def test_pyproject_dependencies_have_no_sentence_transformers_or_faiss():
    """Ensure orchestrator pyproject.toml does not list sentence-transformers or faiss-cpu."""
    pyproject_path = ORCHESTRATOR_SRC.parents[1] / "pyproject.toml"
    assert pyproject_path.is_file(), f"Missing pyproject.toml at {pyproject_path}"

    text = pyproject_path.read_text(encoding="utf-8")
    for banned in ("sentence-transformers", "transformers", "huggingface-hub", "faiss-cpu"):
        assert banned not in text, f"pyproject.toml still contains banned dependency: {banned}"


def test_old_rag_directory_and_faiss_files_deleted():
    """Ensure obsolete rag directory and faiss indices are completely deleted."""
    old_rag_dir = ORCHESTRATOR_SRC / "rag"
    assert not old_rag_dir.exists(), f"Old RAG directory still exists: {old_rag_dir}"

    repo_root = ORCHESTRATOR_SRC.parents[2]
    faiss_file = repo_root / "data" / "rag" / "faiss_index.faiss"
    assert not faiss_file.exists(), f"Old FAISS index file still exists: {faiss_file}"
