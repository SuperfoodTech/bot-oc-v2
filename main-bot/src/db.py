"""
main-bot/src/db.py
==================
Re-exports PostgreSQL database layer from central backend module (src/backend/db.py).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from backend.db import *  # noqa: F401, F403
