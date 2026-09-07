"""Make ``teeth_analyzer`` importable when pytest runs from any venv/cwd.

The Teeth Analyzer package lives under ``services/teeth_analyzer/src``. This shim
adds that path so the focused provider tests run without a dedicated install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PATHS = [
    _ROOT / "services" / "teeth_analyzer" / "src",
    _ROOT / "services" / "diagnosis" / "src",
    _ROOT / "packages" / "dantshaant_common" / "src",
    _ROOT / "orchestrator" / "src",
    _ROOT,
]
for p in _PATHS:
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

