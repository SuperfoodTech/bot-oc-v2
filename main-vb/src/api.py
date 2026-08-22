"""Protected admin API for the VB control surface."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

import db

app = FastAPI(title="FoodMaster Virtual Brand")
ADMIN_TOKEN = os.getenv("VB_ADMIN_API_TOKEN", "")
LEGACY_API_ENABLED = os.getenv("VB_LEGACY_API_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def require_admin(token: str | None) -> None:
    if not LEGACY_API_ENABLED:
        raise HTTPException(status_code=410, detail="Legacy VB API dinonaktifkan. Gunakan backend admin utama.")
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Admin authentication is not configured or invalid")


class StatusRequest(BaseModel):
    status: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "main-vb"}


@app.get("/api/vb/brands")
def brands(x_admin_token: str | None = Header(default=None)) -> list[dict[str, Any]]:
    require_admin(x_admin_token)
    with db.connection() as conn:
        rows = db.list_brands(conn)
        for row in rows:
            row["outlet_count"] = conn.execute("SELECT count(*) FROM vb_brand_outlets WHERE vb_brand_id=%s", (row["id"],)).fetchone()["count"]
            row["merchant_count"] = conn.execute(
                """SELECT count(DISTINCT p.id) FROM vb_brand_outlets bo
                   JOIN outlets o ON o.id=bo.outlet_id JOIN portals p ON p.id=o.portal_id
                   WHERE bo.vb_brand_id=%s""", (row["id"],)
            ).fetchone()["count"]
        return rows


@app.patch("/api/vb/brands/{brand_id}/status")
def request_status(brand_id: str, payload: StatusRequest, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    status = payload.status.upper().strip()
    if status not in {"ON", "PAUSED"}:
        raise HTTPException(status_code=422, detail="status harus ON atau PAUSED")
    with db.connection() as conn:
        with conn.transaction():
            row = conn.execute(
                """UPDATE vb_brands SET requested_status=%s, requested_at=now(), updated_at=now()
                   WHERE id=%s AND is_active=true
                   RETURNING id, name, applied_status, requested_status, requested_at""", (status, brand_id)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Brand tidak ditemukan")
            return row
