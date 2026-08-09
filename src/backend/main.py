"""
main.py
=======
FastAPI Backend Application serving REST API endpoints, Admin Desktop Dashboard, and Mobile-First User Link Dashboard.
"""

import sys
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse

from backend import state, worker
from backend.models import (
    ToggleRequest,
    StoreStatusResponse,
    SyncResponse,
    AutomationLogResponse,
    AdminGenerateLinkRequest,
    AdminCreateOutletRequest,
    AdminSuspendRequest,
    AdminRenewRequest,
    AdminLoginRequest,
    AdminAccountUpdateRequest,
    AdminAccountCreateRequest,
    UserLoginRequest,
    UserPauseRequest
)

# Spreadsheet-backed state has no database startup step.
state.init_state()

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
FRONTEND_DIR = SCRIPT_DIR
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
ADMIN_SESSION_COOKIE = "foodmaster_admin_session"
ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "dev-only-change-me")
ADMIN_SESSION_TTL_SECONDS = 60 * 60 * 12


def _sign_admin_session(payload: dict) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(ADMIN_SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _read_admin_session(token: Optional[str]) -> Optional[dict]:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(ADMIN_SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("role") != "ADMIN" or int(payload.get("exp", 0)) < int(datetime.now().timestamp()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def require_admin(admin_session: Optional[str] = Cookie(default=None, alias=ADMIN_SESSION_COOKIE)):
    account = _read_admin_session(admin_session)
    if not account:
        raise HTTPException(status_code=401, detail="Admin authentication required.")
    return account

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── FRONTEND HTML ROUTES (Direct Serving on / and /admin and /app) ─────────────

@app.get("/", response_class=HTMLResponse, summary="Admin Console Homepage")
@app.get("/admin", response_class=HTMLResponse, summary="Admin Desktop Console Web Page")
def admin_page(admin_session: Optional[str] = Cookie(default=None, alias=ADMIN_SESSION_COOKIE)):
    if not _read_admin_session(admin_session):
        return RedirectResponse(url="/admin/login", status_code=303)
    admin_html = TEMPLATES_DIR / "admin_dashboard.html"
    if not admin_html.exists():
        raise HTTPException(status_code=404, detail="Admin template not found.")
    return HTMLResponse(content=admin_html.read_text(encoding="utf-8"))


@app.get("/admin/login", response_class=HTMLResponse, summary="Admin Login Page")
def admin_login_page():
    login_html = TEMPLATES_DIR / "admin_login.html"
    if not login_html.exists():
        raise HTTPException(status_code=404, detail="Admin login template not found.")
    return HTMLResponse(content=login_html.read_text(encoding="utf-8"))


@app.post("/api/v1/admin/login", summary="Authenticate Admin")
def admin_login(req: AdminLoginRequest, response: Response):
    account = state.admin_authenticate(req.username.strip(), req.password)
    if not account:
        raise HTTPException(status_code=401, detail="Username atau password admin tidak valid.")
    payload = {"sub": str(account["id"]), "username": account["username"], "role": "ADMIN", "exp": int(datetime.now().timestamp()) + ADMIN_SESSION_TTL_SECONDS}
    response.set_cookie(ADMIN_SESSION_COOKIE, _sign_admin_session(payload), httponly=True, max_age=ADMIN_SESSION_TTL_SECONDS, samesite="lax", secure=False, path="/")
    return {"success": True, "username": account["username"], "role": account["role"]}


@app.post("/api/v1/admin/logout", summary="Logout Admin")
def admin_logout(response: Response):
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    return {"success": True}


@app.get("/api/v1/admin/me", summary="Get Current Admin")
def admin_me(admin: dict = Depends(require_admin)):
    return {"success": True, "username": admin["username"], "role": admin["role"]}


@app.get("/api/v1/admin/accounts", summary="List Admin Accounts")
def admin_accounts(admin: dict = Depends(require_admin)):
    return {"success": True, "accounts": state.admin_list_accounts()}


@app.patch("/api/v1/admin/account", summary="Update Current Admin Account")
def admin_update_current_account(req: AdminAccountUpdateRequest, response: Response, admin: dict = Depends(require_admin)):
    try:
        account = state.admin_update_account(admin["sub"], req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not account:
        raise HTTPException(status_code=404, detail="Akun admin tidak ditemukan atau sudah tidak aktif.")
    payload = {"sub": str(account["id"]), "username": account["username"], "role": "ADMIN", "exp": int(datetime.now().timestamp()) + ADMIN_SESSION_TTL_SECONDS}
    response.set_cookie(ADMIN_SESSION_COOKIE, _sign_admin_session(payload), httponly=True, max_age=ADMIN_SESSION_TTL_SECONDS, samesite="lax", secure=False, path="/")
    return {"success": True, "account": account}


@app.post("/api/v1/admin/accounts", summary="Create Admin Account")
def admin_create_account(req: AdminAccountCreateRequest, admin: dict = Depends(require_admin)):
    try:
        account = state.admin_create_account(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "account": account}


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


# ── ADMIN DASHBOARD ENDPOINTS (PostgreSQL is the runtime source of truth) ─────

@app.get("/api/v1/admin/users", summary="Admin: List All Users & Outlets from PostgreSQL")
def admin_list_users(admin: dict = Depends(require_admin)):
    users_data = state.admin_get_all_users_with_stores()
    return {"success": True, "users": users_data}


@app.post("/api/v1/admin/sync-source", summary="Admin: Import the published spreadsheet into PostgreSQL")
def admin_sync_source(admin: dict = Depends(require_admin)):
    try:
        from scripts.import_sheet import run_import_sheet
        imported_count = run_import_sheet()
        return {"success": True, "message": f"Successfully imported {imported_count} store(s) from spreadsheet into PostgreSQL."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source import failed: {exc}") from exc


@app.post("/api/v1/admin/generate-link", summary="Admin: Generate Unique User Link")
def admin_generate_link(req: AdminGenerateLinkRequest, admin: dict = Depends(require_admin)):
    result = state.admin_generate_user_link(req.nama_pemilik, req.passcode)
    state.record_log(
        store_id="ADMIN",
        store_name="ADMIN_SYSTEM",
        action="GENERATE_USER_LINK",
        target_state="CREATED",
        reason=f"Generated Vercel link for '{req.nama_pemilik}' (Passcode: {result['passcode']})"
    )
    return {"success": True, "data": result}


@app.post("/api/v1/admin/outlets", summary="Admin: Create or update merchant outlet")
def admin_create_outlet(req: AdminCreateOutletRequest, admin: dict = Depends(require_admin)):
    if state.get_store_by_id(req.store_id):
        raise HTTPException(status_code=409, detail=f"Store ID '{req.store_id}' sudah terdaftar.")
    state.save_or_update_store(
        store_id=req.store_id,
        store_name=req.nama_panjang_outlet,
        merchant_name=req.nama_portal,
        account_username=req.username,
        nama_pemilik=req.nama_pemilik,
        paket=req.paket,
        tanggal_mulai_layanan=req.tanggal_mulai_layanan,
        tanggal_berakhir_layanan=req.tanggal_berakhir_layanan,
        vercel_password=req.dashboard_password,
        regular_hours=req.operating_hours,
        special_hours=req.special_hours,
    )
    return {"success": True, "data": state.get_store_by_id(req.store_id)}


@app.post("/api/v1/admin/suspend", summary="Admin: Toggle User/Store Suspension")
def admin_suspend(req: AdminSuspendRequest, admin: dict = Depends(require_admin)):
    penangguhan_upper = req.penangguhan.capitalize()
    if penangguhan_upper not in ("Ya", "Tidak"):
        raise HTTPException(status_code=400, detail="penangguhan must be 'Ya' or 'Tidak'.")

    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    state.admin_set_suspension(req.store_id, penangguhan_upper, req.alasan_penangguhan or "")
    state.record_log(
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
def admin_renew(req: AdminRenewRequest, admin: dict = Depends(require_admin)):
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    state.admin_renew_subscription(req.store_id, req.new_expiry_date)
    state.record_log(
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
    user_info = state.user_authenticate(req.passcode)
    if not user_info:
        raise HTTPException(status_code=401, detail="Passcode kata sandi Vercel tidak valid.")

    pemilik = user_info.get("nama_pemilik", "Fando")
    outlets = state.user_get_outlets(pemilik)

    return {
        "success": True,
        "nama_pemilik": pemilik,
        "passcode": req.passcode,
        "total_outlets": len(outlets),
        "outlets": outlets
    }


@app.get("/api/v1/user/outlets", summary="User Link: Get Outlets for Authenticated User")
def user_get_outlets(nama_pemilik: str = Query(..., description="Nama Pemilik / Mitra")):
    outlets = state.user_get_outlets(nama_pemilik)
    return {"success": True, "nama_pemilik": nama_pemilik, "total_outlets": len(outlets), "outlets": outlets}


@app.post("/api/v1/user/pause", summary="User Link: Pause Store with Selected Duration")
def user_pause_store(req: UserPauseRequest):
    store = state.get_store_by_id(req.store_id)
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

    state.update_vercel_toggle(req.store_id, "OFF", pause_until_str)
    state.record_log(
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
    store = state.get_store_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' not found.")

    state.update_vercel_toggle(store_id, "ON", None)
    actual_store = state.get_store_by_id(store_id)
    state.record_log(
        store_id=store_id,
        store_name=store["store_name"],
        action="USER_RESUME_STORE",
        target_state="OPEN",
        reason="User manually turned Vercel Toggle ON (Auto Open)"
    )

    return {
        "success": True,
        "store_id": store_id,
        "vercel_status": actual_store["vercel_status"],
        "message": f"Store {store_id} Vercel status updated to {actual_store['vercel_status']}."
    }


@app.get("/api/v1/user/history", summary="User Link: Get Audit History for Outlets")
def user_get_history(store_ids: str = Query(..., description="Comma-separated store IDs (e.g. 21897166,22403325)")):
    id_list = [s.strip() for s in store_ids.split(",") if s.strip()]
    logs = state.get_recent_logs(limit=50, store_ids=id_list)
    return {"success": True, "total_logs": len(logs), "logs": logs}


# ── COMPATIBILITY & REST ENDPOINTS ─────────────────────────────────────────────

@app.get("/api/v1/stores", response_model=List[StoreStatusResponse], summary="Get All Store Statuses")
def list_stores(admin: dict = Depends(require_admin)):
    stores = state.get_all_stores()

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


@app.get("/api/v1/stores/{store_id}", response_model=StoreStatusResponse, summary="Get Single Store Status")
def get_store_detail(store_id: str, admin: dict = Depends(require_admin)):
    s = state.get_store_by_id(store_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' not found.")
    return StoreStatusResponse(
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
    )


@app.post("/api/v1/toggle", summary="Toggle Vercel status for store")
def toggle_store(req: ToggleRequest, admin: dict = Depends(require_admin)):
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")
    pause_until = None
    if req.status.upper() == "OFF" and req.pause_duration_minutes:
        pause_dt = datetime.now() + timedelta(minutes=req.pause_duration_minutes)
        pause_until = pause_dt.strftime("%Y-%m-%d %H:%M:%S")
    state.update_vercel_toggle(req.store_id, req.status, pause_until)
    updated = state.get_store_by_id(req.store_id)
    return {
        "success": True,
        "store_id": req.store_id,
        "new_vercel_status": updated["vercel_status"],
        "pause_until": updated["pause_until"]
    }


@app.post("/api/v1/sync", response_model=SyncResponse, summary="Trigger Manual Synchronization Loop")
def trigger_sync(execute: bool = Query(default=True, description="Whether to execute Shopee API actions if mismatch detected"), admin: dict = Depends(require_admin)):
    # The browser bot is an independent service. The monolith only exposes
    # the current DB snapshot here; it never re-imports or mutates the sheet.
    stores = state.get_all_stores()
    result = {"success": True, "total_stores_processed": len(stores), "actions_taken": [], "message": "Current PostgreSQL state returned; bot daemon owns Shopee actions."}
    return SyncResponse(
        success=result["success"],
        total_stores_processed=result["total_stores_processed"],
        actions_taken=result["actions_taken"],
        message=result["message"]
    )


@app.get("/api/v1/logs", response_model=List[AutomationLogResponse], summary="Get Automation Audit Logs")
def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: Optional[str] = Query(default=None, description="Filter by action name"),
    search: Optional[str] = Query(default=None, description="Search keyword in store_id, name, or reason"),
    admin: dict = Depends(require_admin)
):
    logs = state.get_recent_logs(limit=limit)
    if action and action.strip():
        act_q = action.strip().upper()
        logs = [l for l in logs if act_q in l["action"].upper()]
    if search and search.strip():
        sq = search.strip().lower()
        logs = [
            l for l in logs
            if sq in l["store_id"].lower() or sq in l["store_name"].lower() or sq in l["reason"].lower() or sq in l["action"].lower()
        ]
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
