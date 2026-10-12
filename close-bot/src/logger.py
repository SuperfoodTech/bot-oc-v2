"""
main-bot/src/logger.py
======================
Re-exports logger utility from central core module (src/core/logger.py).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.logger import *  # noqa: F401, F403
