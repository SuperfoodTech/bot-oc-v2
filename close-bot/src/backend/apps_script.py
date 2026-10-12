"""Client for the Google Apps Script Sheet write-back Web App."""

import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

WEB_APP_URL = os.getenv("GOOGLE_SHEETS_APPS_SCRIPT_URL", "").strip()
WEBHOOK_TOKEN = os.getenv("GOOGLE_SHEETS_APPS_SCRIPT_TOKEN", "").strip()


def set_store_import_status(store_id: str, status: str = "Nonaktif") -> dict[str, Any]:
    if not WEB_APP_URL:
        raise RuntimeError("GOOGLE_SHEETS_APPS_SCRIPT_URL belum dikonfigurasi.")
    if not WEBHOOK_TOKEN:
        raise RuntimeError("GOOGLE_SHEETS_APPS_SCRIPT_TOKEN belum dikonfigurasi.")

    response = requests.post(
        WEB_APP_URL,
        json={
            "action": "deactivate",
            "store_id": str(store_id),
            "token": WEBHOOK_TOKEN,
        },
        timeout=20,
    )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Apps Script mengembalikan response tidak valid (HTTP {response.status_code}).") from exc

    if response.status_code >= 400 or not data.get("success"):
        raise RuntimeError(data.get("error") or f"Apps Script gagal (HTTP {response.status_code}).")
    return data
