"""
main-bot/src/browser.py
=======================
Re-exports browser automation routines from the central core module (src/core/browser.py).
This maintains 100% single source of truth for browser logic while supporting main-bot execution.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from core.browser import *  # noqa: F401, F403
