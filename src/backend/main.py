"""
main.py
=======
FastAPI Backend Application serving REST API endpoints, Admin Desktop Dashboard, and Mobile-First User Link Dashboard.
"""

import sys
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse

from backend import db, worker
from backend.models import (
    ToggleRequest,
    StoreStatusResponse,
    SyncResponse,
    AutomationLogResponse,
    AdminGenerateLinkRequest,
    AdminSuspendRequest,
    AdminRenewRequest,
    UserLoginRequest,
    UserPauseRequest
)

# Initialize Database Schema
db.init_db()

app = FastAPI(
    title="FoodMaster ShopeeFood Automation Backend & Web Apps",
    description="Backend Service & Integrated Frontends (Admin Console & Mobile User Link)",
    version="2.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files System
STATIC_DIR = SCRIPT_DIR / "static"
TEMPLATES_DIR = SCRIPT_DIR / "templates"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── FRONTEND HTML ROUTES (Direct Serving on / and /admin and /app) ─────────────

@app.get("/", response_class=HTMLResponse, summary="Admin Console Homepage")
@app.get("/admin", response_class=HTMLResponse, summary="Admin Desktop Console Web Page")
def admin_page():
    admin_html = TEMPLATES_DIR / "admin_dashboard.html"
    if not admin_html.exists():
        raise HTTPException(status_code=404, detail="Admin template not found.")
    return HTMLResponse(content=admin_html.read_text(encoding="utf-8"))


@app.get("/app", response_class=HTMLResponse, summary="User Link Mobile Dashboard Web Page")
@app.get("/mitra/{slug}", response_class=HTMLResponse, summary="User Link Mobile Dashboard Web Page")
def user_page(slug: Optional[str] = None):
    user_html = TEMPLATES_DIR / "user_dashboard.html"
    if not user_html.exists():
        raise HTTPException(status_code=404, detail="User template not found.")
    return HTMLResponse(content=user_html.read_text(encoding="utf-8"))


# ── SERVICE HEALTHCHECK ────────────────────────────────────────────────────────

@app.get("/api/v1/health", summary="Service Health Check")
def health_check():
    return {
        "status": "healthy",
        "service": "FoodMaster Integrated Web App & API",
        "version": "2.2.0",
        "timestamp": datetime.now().isoformat()
    }


# ── ADMIN DASHBOARD ENDPOINTS (Fetches Directly from Google Sheets CSV) ────────

@app.get("/api/v1/admin/users", summary="Admin: List All Users & Outlets Status from Sheets")
def admin_list_users():
    # Sync live data from Google Sheets CSV every time Admin fetches
    try:
        worker.sync_all_stores(execute_actions=False)
    except Exception as e:
        pass
    users_data = db.admin_get_all_users_with_stores()
    return {"success": True, "users": users_data}


@app.post("/api/v1/admin/generate-link", summary="Admin: Generate Unique User Link")
def admin_generate_link(req: AdminGenerateLinkRequest):
    result = db.admin_generate_user_link(req.nama_pemilik, req.passcode)
    db.record_log(
        store_id="ADMIN",
        store_name="ADMIN_SYSTEM",
        action="GENERATE_USER_LINK",
        target_state="CREATED",
        reason=f"Generated Vercel link for '{req.nama_pemilik}' (Passcode: {result['passcode']})"
    )
    return {"success": True, "data": result}


@app.post("/api/v1/admin/suspend", summary="Admin: Toggle User/Store Suspension")
def admin_suspend(req: AdminSuspendRequest):
    penangguhan_upper = req.penangguhan.capitalize()
    if penangguhan_upper not in ("Ya", "Tidak"):
        raise HTTPException(status_code=400, detail="penangguhan must be 'Ya' or 'Tidak'.")

    store = db.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    db.admin_set_suspension(req.store_id, penangguhan_upper, req.alasan_penangguhan or "")
    db.record_log(
        store_id=req.store_id,
        store_name=store["store_name"],
        action="ADMIN_SUSPEND_UPDATE",
        target_state="SUSPENDED" if penangguhan_upper == "Ya" else "ACTIVE",
        reason=f"Admin updated suspension to '{penangguhan_upper}' (Alasan: {req.alasan_penangguhan})"
    )

    return {
        "success": True,
        "store_id": req.store_id,
        "penangguhan": penangguhan_upper,
        "alasan_penangguhan": req.alasan_penangguhan,
        "message": f"Store {req.store_id} suspension set to '{penangguhan_upper}'."
    }


@app.post("/api/v1/admin/renew", summary="Admin: Renew Active Expiry Date")
def admin_renew(req: AdminRenewRequest):
    store = db.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    db.admin_renew_subscription(req.store_id, req.new_expiry_date)
    db.record_log(
        store_id=req.store_id,
        store_name=store["store_name"],
        action="ADMIN_RENEW_SUBSCRIPTION",
        target_state="ACTIVE",
        reason=f"Subscription renewed until {req.new_expiry_date}"
    )

    return {
        "success": True,
        "store_id": req.store_id,
        "new_expiry_date": req.new_expiry_date,
        "message": f"Store {req.store_id} subscription renewed until {req.new_expiry_date}."
    }


# ── USER LINK / DASHBOARD ENDPOINTS ───────────────────────────────────────────

@app.post("/api/v1/user/login", summary="User Link: Login by Passcode")
def user_login(req: UserLoginRequest):
    user_info = db.user_authenticate(req.passcode)
    if not user_info:
        raise HTTPException(status_code=401, detail="Passcode kata sandi Vercel tidak valid.")

    pemilik = user_info.get("nama_pemilik", "Fando")
    outlets = db.user_get_outlets(pemilik)

    return {
        "success": True,
        "nama_pemilik": pemilik,
        "passcode": req.passcode,
        "total_outlets": len(outlets),
        "outlets": outlets
    }


@app.get("/api/v1/user/outlets", summary="User Link: Get Outlets for Authenticated User")
def user_get_outlets(nama_pemilik: str = Query(..., description="Nama Pemilik / Mitra")):
    outlets = db.user_get_outlets(nama_pemilik)
    return {"success": True, "nama_pemilik": nama_pemilik, "total_outlets": len(outlets), "outlets": outlets}


@app.post("/api/v1/user/pause", summary="User Link: Pause Store with Selected Duration")
def user_pause_store(req: UserPauseRequest):
    store = db.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    dtype = req.duration_type.lower()
    now_dt = datetime.now()

    if dtype in ("30", "30_min", "30min"):
        duration_mins = 30
        label = "30 Menit"
    elif dtype in ("60", "60_min", "60min"):
        duration_mins = 60
        label = "60 Menit"
    elif dtype in ("rest_of_day", "sepanjang_hari", "today"):
        midnight = datetime(now_dt.year, now_dt.month, now_dt.day, 23, 59, 59)
        duration_mins = int((midnight - now_dt).total_seconds() // 60)
        if duration_mins < 10:
            duration_mins = 60
        label = "Sepanjang Hari"
    elif dtype in ("custom", "waktu_lain"):
        duration_mins = req.custom_minutes or 120
        label = f"{duration_mins} Menit (Custom)"
    else:
        duration_mins = 1440
        label = "Default (1 Hari)"

    pause_until_dt = now_dt + timedelta(minutes=duration_mins)
    pause_until_str = pause_until_dt.strftime("%Y-%m-%d %H:%M:%S")

    db.update_vercel_toggle(req.store_id, "OFF", pause_until_str)
    db.record_log(
        store_id=req.store_id,
        store_name=store["store_name"],
        action="USER_PAUSE_STORE",
        target_state="CLOSED",
        reason=f"User set store OFF with duration: {label} (Until {pause_until_str})"
    )

    return {
        "success": True,
        "store_id": req.store_id,
        "vercel_status": "OFF",
        "duration_label": label,
        "pause_until": pause_until_str,
        "message": f"Store {req.store_id} paused for {label}."
    }


@app.post("/api/v1/user/resume", summary="User Link: Resume / Open Store")
def user_resume_store(store_id: str = Query(..., description="Target Store ID")):
    store = db.get_store_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' not found.")

    db.update_vercel_toggle(store_id, "ON", None)
    db.record_log(
        store_id=store_id,
        store_name=store["store_name"],
        action="USER_RESUME_STORE",
        target_state="OPEN",
        reason="User manually turned Vercel Toggle ON (Auto Open)"
    )

    return {
        "success": True,
        "store_id": store_id,
        "vercel_status": "ON",
        "message": f"Store {store_id} Vercel status updated to ON."
    }


@app.get("/api/v1/user/history", summary="User Link: Get Audit History for Outlets")
def user_get_history(store_ids: str = Query(..., description="Comma-separated store IDs (e.g. 21897166,22403325)")):
    id_list = [s.strip() for s in store_ids.split(",") if s.strip()]
    logs = db.get_recent_logs(limit=50, store_ids=id_list)
    return {"success": True, "total_logs": len(logs), "logs": logs}


# ── COMPATIBILITY & REST ENDPOINTS ─────────────────────────────────────────────

@app.get("/api/v1/stores", response_model=List[StoreStatusResponse], summary="Get All Store Statuses")
def list_stores():
    try:
        worker.sync_all_stores(execute_actions=False)
    except Exception:
        pass
    stores = db.get_all_stores()

    response = []
    for s in stores:
        response.append(StoreStatusResponse(
            store_id=s["store_id"],
            store_name=s["store_name"],
            merchant_name=s["merchant_name"],
            account_username=s["account_username"],
            nama_pemilik=s.get("nama_pemilik", ""),
            paket=s.get("paket", "3 Bulan"),
            tanggal_mulai_layanan=s.get("tanggal_mulai_layanan", ""),
            tanggal_berakhir_layanan=s.get("tanggal_berakhir_layanan", ""),
            vercel_link=s.get("vercel_link", ""),
            vercel_password=s.get("vercel_password", ""),
            vercel_status=s["vercel_status"],
            shopee_status=s["shopee_status"],
            subscription_status=s["subscription_status"],
            is_suspended=bool(s["is_suspended"]),
            alasan_penangguhan=s.get("alasan_penangguhan", ""),
            pause_until=s["pause_until"],
            last_synced_at=s["last_synced_at"]
        ))
    return response


@app.post("/api/v1/sync", response_model=SyncResponse, summary="Trigger Manual Synchronization Loop")
def trigger_sync(execute: bool = Query(default=True, description="Whether to execute Shopee API actions if mismatch detected")):
    result = worker.sync_all_stores(execute_actions=execute)
    return SyncResponse(
        success=result["success"],
        total_stores_processed=result["total_stores_processed"],
        actions_taken=result["actions_taken"],
        message=result["message"]
    )


@app.get("/api/v1/logs", response_model=List[AutomationLogResponse], summary="Get Automation Audit Logs")
def get_logs(limit: int = Query(default=50, ge=1, le=200)):
    logs = db.get_recent_logs(limit=limit)
    return [
        AutomationLogResponse(
            id=l["id"],
            timestamp=l["timestamp"],
            store_id=l["store_id"],
            store_name=l["store_name"],
            action=l["action"],
            target_state=l["target_state"],
            reason=l["reason"]
        ) for l in logs
    ]
