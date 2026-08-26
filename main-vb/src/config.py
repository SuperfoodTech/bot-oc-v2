"""Runtime configuration for main-vb.

The copied core remains unchanged. This module supplies VB-specific paths and
credentials at the service boundary.
"""

import os
import json
from pathlib import Path

VB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = VB_ROOT.parent.parent
# Runtime data follows the copied core layout under main-vb/src/data.
DATA_DIR = VB_ROOT / "src" / "data"
SESSION_FILE = Path(os.getenv("VB_SESSION_FILE", str(DATA_DIR / "session.json")))
CREDENTIALS_FILE = Path(os.getenv("VB_CREDENTIALS_FILE", str(DATA_DIR / "credentials.json")))


def _read_credentials() -> tuple[str, str]:
    if not CREDENTIALS_FILE.exists():
        return os.getenv("VB_SHOPEE_USERNAME", "allvbadmin"), ""
    data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("username"):
        return str(data["username"]), str(data.get("password") or "")
    for key, item in data.items():
        if isinstance(item, dict) and item.get("password"):
            username = item.get("username") or key
            return str(username), str(item["password"])
    return os.getenv("VB_SHOPEE_USERNAME", "allvbadmin"), ""


USERNAME, PASSWORD = _read_credentials()
PATROL_INTERVAL_SECONDS = int(os.getenv("VB_PATROL_INTERVAL_SECONDS", "30"))
MAX_RETRIES = int(os.getenv("VB_MAX_RETRIES", "2"))
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://foodmaster:change-me-in-env@localhost:5435/foodmaster")


def validate_runtime_paths() -> None:
    if not SESSION_FILE.exists():
        raise FileNotFoundError(f"VB session file tidak ditemukan: {SESSION_FILE}")
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"VB credential tidak ditemukan: {CREDENTIALS_FILE}")
