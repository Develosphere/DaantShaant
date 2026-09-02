"""Make ``diagnosis`` importable when pytest runs from any venv/cwd.

The Diagnosis package lives under ``services/diagnosis/src``. This shim adds that
path so the focused triage tests run without a dedicated install (same pattern as
the Teeth Analyzer suite).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# The shared schema package lives under packages/dantshaant_common/src.
_COMMON = Path(__file__).resolve().parents[3] / "packages" / "dantshaant_common" / "src"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))
