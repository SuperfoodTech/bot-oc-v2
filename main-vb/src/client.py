"""
main-bot/src/client.py
======================
Re-exports Shopee Partner client from central core module (src/core/client.py).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.client import *  # noqa: F401, F403
