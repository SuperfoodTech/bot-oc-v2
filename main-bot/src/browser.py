"""
main-bot/src/browser.py
=======================
Re-exports browser automation routines from the central core module (src/core/browser.py).
This maintains 100% single source of truth for browser logic while supporting main-bot execution.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.browser import *  # noqa: F401, F403
