"""Make ``teeth_analyzer`` importable when pytest runs from any venv/cwd.

The Teeth Analyzer package lives under ``services/teeth_analyzer/src``. This shim
adds that path so the focused provider tests run without a dedicated install.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
