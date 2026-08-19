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
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend import db, state, worker
from backend.models import (
    ToggleRequest,
    StoreStatusResponse,
    SyncResponse,
    AutomationLogResponse,
    AdminGenerateLinkRequest,
    AdminCreateOutletRequest,
    AdminSuspendRequest,
    AdminRenewRequest,
    AdminEditOutletRequest,
    AdminLoginRequest,
    AdminAccountUpdateRequest,
    AdminAccountCreateRequest,
    UserLoginRequest,
    UserPauseRequest,
    AgencyToggleRequest,
    AgencyForceCloseRequest
)
from agency import sheets as agency_sheets
from agency import runner as agency_runner


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
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
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


# ── FRONTEND HTML ROUTES (Serving /admin/dashboard, /admin/bot, /app) ─────────

@app.get("/", summary="Admin Console Homepage Redirect")
@app.get("/admin", summary="Admin Desktop Console Redirect")
def admin_redirect():
    return RedirectResponse(url="/admin/dashboard", status_code=303)


@app.get("/admin/dashboard", response_class=HTMLResponse, summary="Admin Dashboard (Operasional & Settings)")
def admin_dashboard_page(request: Request, admin_session: Optional[str] = Cookie(default=None, alias=ADMIN_SESSION_COOKIE)):
    if not _read_admin_session(admin_session):
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse(request=request, name="admin_dashboard.html", context={"active_page": "dashboard"})


@app.get("/admin/mitra/tambah", response_class=HTMLResponse, summary="Admin: Add Merchant and Outlet")
def admin_add_merchant_page(request: Request, admin_session: Optional[str] = Cookie(default=None, alias=ADMIN_SESSION_COOKIE)):
    if not _read_admin_session(admin_session):
        return RedirectResponse(url="/admin/login")
    return templates.TemplateResponse(request=request, name="admin_add_merchant.html", context={"active_page": "add-merchant"})


@app.get("/admin/bot", summary="Admin Bot Patrol Monitor Page Redirect")
@app.get("/admin/logs", summary="Admin Logs Page Redirect")
def admin_logs_page():
    return RedirectResponse(url="/admin/dashboard?tab=logs", status_code=303)






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


@app.get("/api/v1/auth/google/login", summary="Initiate Google OAuth Flow")
def google_login(role: str = "merchant", state_url: Optional[str] = Query(None, alias="state_url")):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    if not client_id or not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI in the environment."
        )
    
    scope = "openid email profile"
    state_param = f"{role}"
    if state_url:
        state_param = f"{role}:{state_url}"
    
    import urllib.parse
    google_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
        f"scope={urllib.parse.quote(scope)}&"
        f"state={urllib.parse.quote(state_param)}"
    )
    return RedirectResponse(url=google_url)


@app.get("/api/v1/auth/google/callback", summary="Google OAuth Callback")
def google_callback(code: str, state_val: Optional[str] = Query(None, alias="state"), response: Response = None):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="Google OAuth configuration missing.")
    
    role = "merchant"
    redirect_path = ""
    if state_val:
        parts = state_val.split(":", 1)
        role = parts[0]
        if len(parts) > 1:
            redirect_path = parts[1]

    fallback_login_url = "/admin/login" if role == "admin" else "/app"
    if redirect_path:
        fallback_login_url = redirect_path

    import requests
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    
    try:
        token_res = requests.post(token_url, data=data, timeout=10)
        token_res.raise_for_status()
        token_data = token_res.json()
    except Exception as e:
        import urllib.parse
        return RedirectResponse(url=f"{fallback_login_url}?error=token_exchange_failed&detail={urllib.parse.quote(str(e))}")
        
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(url=f"{fallback_login_url}?error=no_access_token")
        
    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        user_res = requests.get(userinfo_url, headers=headers, timeout=10)
        user_res.raise_for_status()
        user_info = user_res.json()
    except Exception as e:
        import urllib.parse
        return RedirectResponse(url=f"{fallback_login_url}?error=userinfo_fetch_failed&detail={urllib.parse.quote(str(e))}")
        
    email = user_info.get("email")
    if not email:
        return RedirectResponse(url=f"{fallback_login_url}?error=email_not_provided")
        
    account = state.google_authenticate(email)
    if not account:
        import urllib.parse
        return RedirectResponse(url=f"{fallback_login_url}?error=email_not_registered&email={urllib.parse.quote(email)}")

    if role == "admin":
        if account.get("role") != "ADMIN":
            return RedirectResponse(url=f"{fallback_login_url}?error=unauthorized_role")
        payload = {"sub": str(account["id"]), "username": account["username"], "role": "ADMIN", "exp": int(datetime.now().timestamp()) + ADMIN_SESSION_TTL_SECONDS}
        signed = _sign_admin_session(payload)
        resp = RedirectResponse(url="/admin/dashboard", status_code=303)
        resp.set_cookie(ADMIN_SESSION_COOKIE, signed, httponly=True, max_age=ADMIN_SESSION_TTL_SECONDS, samesite="lax", secure=False, path="/")
        return resp
    else:
        if account.get("role") != "MERCHANT":
            return RedirectResponse(url=f"{fallback_login_url}?error=unauthorized_role")
        passcode = account.get("password_plain")
        import urllib.parse
        target = redirect_path if redirect_path else "/app"
        separator = "&" if "?" in target else "?"
        return RedirectResponse(url=f"{target}{separator}passcode={urllib.parse.quote(passcode)}")


@app.get("/api/v1/admin/me", summary="Get Current Admin")
def admin_me(admin: dict = Depends(require_admin)):
    account = state.get_dashboard_account_by_id(admin["sub"])
    if not account:
        raise HTTPException(status_code=404, detail="Akun admin tidak ditemukan.")
    return {"success": True, "username": account["username"], "role": account["role"], "google_email": account.get("google_email")}


@app.get("/api/v1/admin/accounts", summary="List Admin Accounts")
def admin_accounts(admin: dict = Depends(require_admin)):
    return {"success": True, "accounts": state.admin_list_accounts()}


@app.patch("/api/v1/admin/account", summary="Update Current Admin Account")
def admin_update_current_account(req: AdminAccountUpdateRequest, response: Response, admin: dict = Depends(require_admin)):
    try:
        account = state.admin_update_account(admin["sub"], req.username, req.password, req.google_email)
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
        account = state.admin_create_account(req.username, req.password, req.google_email)
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
def admin_generate_link(req: AdminGenerateLinkRequest, request: Request, admin: dict = Depends(require_admin)):
    base_url = str(request.base_url).rstrip("/")
    result = state.admin_generate_user_link(req.nama_pemilik, req.passcode, base_url=base_url)
    state.record_log(
        store_id="ADMIN",
        store_name="ADMIN_SYSTEM",
        action="GENERATE_USER_LINK",
        target_state="CREATED",
        reason=f"Generated Vercel link for '{req.nama_pemilik}' (Passcode: {result['passcode']})"
    )
    return {"success": True, "data": result}


@app.post("/api/v1/admin/outlets", summary="Admin: Create or update merchant outlet")
def admin_create_outlet(req: AdminCreateOutletRequest, request: Request, admin: dict = Depends(require_admin)):
    if state.get_store_by_id(req.store_id):
        raise HTTPException(status_code=409, detail=f"Store ID '{req.store_id}' sudah terdaftar.")
    base_url = str(request.base_url).rstrip("/")
    try:
        state.save_or_update_store(
            store_id=req.store_id,
            store_name=req.nama_panjang_outlet,
            merchant_name=req.nama_portal,
            account_username=req.username,
            nama_pemilik=req.nama_pemilik,
            ownership_type=req.ownership_type,
            paket=req.paket,
            tanggal_mulai_layanan=req.tanggal_mulai_layanan,
            tanggal_berakhir_layanan=req.tanggal_berakhir_layanan,
            vercel_password=req.dashboard_password,
            regular_hours=req.operating_hours,
            special_hours=req.special_hours,
            base_url=base_url,
            google_email=req.google_email,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
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


@app.post("/api/v1/admin/outlets/edit", summary="Admin: Edit merchant, portal, and outlet fields")
def admin_edit_outlet(req: AdminEditOutletRequest, admin: dict = Depends(require_admin)):
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' tidak ditemukan.")

    try:
        success = state.admin_edit_outlet(
            store_id=req.store_id,
            nama_pemilik=req.nama_pemilik,
            nama_portal=req.nama_portal,
            nama_panjang_outlet=req.nama_panjang_outlet,
            ownership_type=req.ownership_type,
            paket=req.paket,
            dashboard_password=req.dashboard_password,
            google_email=req.google_email
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    if not success:
        raise HTTPException(status_code=500, detail="Gagal memperbarui data outlet.")

    updated_store = state.get_store_by_id(req.store_id)
    state.record_log(
        store_id=req.store_id,
        store_name=updated_store.get("store_name", req.store_id) if updated_store else req.store_id,
        action="ADMIN_EDIT_OUTLET",
        target_state="UPDATED",
        reason=f"Admin updated outlet details (Pemilik: {req.nama_pemilik}, Portal: {req.nama_portal}, Outlet: {req.nama_panjang_outlet})"
    )

    return {"success": True, "data": updated_store}


@app.delete("/api/v1/admin/outlets/{store_id}", summary="Admin: Delete Store Outlet")
def admin_delete_outlet(store_id: str, admin: dict = Depends(require_admin)):
    store = state.get_store_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' tidak ditemukan.")
    success = state.delete_store(store_id)
    if not success:
        raise HTTPException(status_code=500, detail="Gagal menghapus outlet dari database.")
    state.record_log(
        store_id=store_id,
        store_name=store.get("store_name", store_id),
        action="ADMIN_DELETE_STORE",
        target_state="DELETED",
        reason=f"Admin deleted outlet '{store_id}' ({store.get('store_name')})"
    )
    return {"success": True, "message": f"Outlet '{store_id}' berhasil dihapus."}


@app.delete("/api/v1/admin/users/{nama_pemilik}", summary="Admin: Delete Merchant / Partner")
def admin_delete_merchant(nama_pemilik: str, admin: dict = Depends(require_admin)):
    success = state.delete_merchant(nama_pemilik)
    if not success:
        raise HTTPException(status_code=404, detail=f"Mitra '{nama_pemilik}' tidak ditemukan.")
    state.record_log(
        store_id="ADMIN",
        store_name="ADMIN_SYSTEM",
        action="ADMIN_DELETE_MERCHANT",
        target_state="DELETED",
        reason=f"Admin deleted merchant/partner '{nama_pemilik}' and all associated outlets."
    )
    return {"success": True, "message": f"Data mitra '{nama_pemilik}' beserta seluruh outlet berhasil dihapus."}


# ── USER LINK / DASHBOARD ENDPOINTS ───────────────────────────────────────────

@app.post("/api/v1/user/login", summary="User Link: Login by Passcode")
def user_login(req: UserLoginRequest):
    user_info = state.user_authenticate(req.passcode, req.slug)
    if not user_info:
        raise HTTPException(status_code=401, detail="Link atau passcode mitra tidak valid.")

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

    if store.get("is_suspended") or store.get("suspension_status") == "SUSPENDED":
        reason = store.get("alasan_penangguhan") or "Tindakan admin"
        raise HTTPException(status_code=403, detail=f"Outlet ditangguhkan oleh Admin (Alasan: {reason}). Silakan hubungi CS.")

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

    if store.get("is_suspended") or store.get("suspension_status") == "SUSPENDED":
        reason = store.get("alasan_penangguhan") or "Tindakan admin"
        raise HTTPException(status_code=403, detail=f"Outlet ditangguhkan oleh Admin (Alasan: {reason}). Silakan hubungi CS.")

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
            nama_portal=s.get("nama_portal", s.get("merchant_name", "")),
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
            last_synced_at=s["last_synced_at"],
            last_action=s.get("last_action", "no change")
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
        nama_portal=s.get("nama_portal", s.get("merchant_name", "")),
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
        last_synced_at=s["last_synced_at"],
        last_action=s.get("last_action", "no change")
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


import urllib.request
from datetime import timezone

# Path to bot_state.json written by main-bot/src/bot_api.py
BOT_STATE_FILE = PROJECT_ROOT / "main-bot" / "src" / "bot_state.json"


def _read_persisted_bot_state() -> str:
    """Read persisted bot status from bot_state.json. Returns 'running', 'paused', or 'unknown'."""
    try:
        if BOT_STATE_FILE.exists():
            data = json.loads(BOT_STATE_FILE.read_text())
            return data.get("status", "unknown")
    except Exception:
        pass
    return "unknown"


def fetch_dynamic_bot_status() -> dict:
    """
    Checks real-time bot daemon status dynamically without hardcoding:
    1. HTTP check on http://127.0.0.1:8081/health or /bot/status
    2. Fallback: read persisted bot_state.json (survives restarts)
    3. Fallback: check recent PostgreSQL automation_logs activity for HEALTHY non-error logs
    """
    # 1. Try bot HTTP API
    for endpoint in ["http://127.0.0.1:8081/health", "http://127.0.0.1:8081/bot/status", "http://127.0.0.1:8081/api/v1/bot/status"]:
        try:
            req = urllib.request.Request(endpoint, headers={"User-Agent": "FoodMaster-Backend"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    bot_status = data.get("bot_status", data.get("status", "running"))
                    cycle_count = data.get("cycle_count", 0)
                    last_cycle_at = data.get("last_cycle_at", "")

                    if bot_status == "paused":
                        return {
                            "is_online": False,
                            "status_text": "Di-pause",
                            "status_class": "badge-suspended",
                            "detail_text": "Patroli bot dihentikan sementara",
                            "cycle_count": cycle_count,
                            "last_cycle_at": last_cycle_at
                        }

                    return {
                        "is_online": True,
                        "status_text": "Online",
                        "status_class": "badge-open",
                        "detail_text": f"Patroli aktif (Siklus #{cycle_count})" if cycle_count else "Sinkronisasi aktif 24/7",
                        "cycle_count": cycle_count,
                        "last_cycle_at": last_cycle_at
                    }
        except Exception:
            pass

    # 2. Fallback: read persisted bot_state.json (handles case where daemon is paused but port 8081 is down)
    persisted_status = _read_persisted_bot_state()
    if persisted_status == "paused":
        return {
            "is_online": False,
            "status_text": "Di-pause",
            "status_class": "badge-suspended",
            "detail_text": "Patroli bot dihentikan sementara (dari state terakhir)",
            "seconds_ago": None
        }

    # 3. Fallback: check DB for recent successful automation logs (excluding 404/Error logs)
    try:
        logs = state.get_recent_logs(limit=5)
        if logs:
            latest_log = logs[0]
            action = str(latest_log.get("action", "")).upper()
            details = str(latest_log.get("details", "")).upper()
            status_field = str(latest_log.get("status", "")).upper()
            log_time_str = str(latest_log.get("timestamp", ""))

            # If the latest log is an explicit 404, ERROR, or FAILED status
            if "404" in action or "404" in details or "ERROR" in status_field or "FAILED" in status_field or "CRITICAL" in status_field:
                return {
                    "is_online": False,
                    "status_text": "Offline",
                    "status_class": "badge-closed",
                    "detail_text": "Kendala sistem (404 / Error)",
                    "seconds_ago": None
                }

            if log_time_str:
                parsed_time = datetime.fromisoformat(log_time_str.replace("Z", "+00:00").replace(" ", "T"))
                now_utc = datetime.now(timezone.utc)
                if parsed_time.tzinfo is None:
                    parsed_time = parsed_time.replace(tzinfo=timezone.utc)
                seconds_ago = (now_utc - parsed_time.astimezone(timezone.utc)).total_seconds()

                # Must be recent (within 3 minutes / 180 seconds)
                if seconds_ago <= 180:
                    mins_ago = max(0, int(seconds_ago // 60))
                    detail = "Sinkronisasi aktif" if mins_ago == 0 else f"Patroli aktif ({mins_ago}m lalu)"
                    return {
                        "is_online": True,
                        "status_text": "Online",
                        "status_class": "badge-open",
                        "detail_text": detail,
                        "seconds_ago": int(seconds_ago)
                    }
    except Exception:
        pass

    return {
        "is_online": False,
        "status_text": "Offline",
        "status_class": "badge-closed",
        "detail_text": "Bot patroli tidak aktif",
        "seconds_ago": None
    }


@app.get("/api/v1/admin/bot-status", summary="Get dynamic real-time bot daemon status")
def get_bot_status_endpoint(admin: dict = Depends(require_admin)):
    return fetch_dynamic_bot_status()


@app.get("/api/v1/admin/bot/activity", summary="Get bot activity evidence — last cycle, actions taken")
def get_bot_activity_endpoint(admin: dict = Depends(require_admin)):
    """Proxy to bot_api /bot/activity. Falls back to DB logs if bot is offline."""
    # Try live bot API first
    try:
        req = urllib.request.Request("http://127.0.0.1:8081/bot/activity", headers={"User-Agent": "FoodMaster-Backend"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass

    # Fallback: build activity from DB logs
    try:
        db_logs = state.get_recent_logs(limit=15)
        last_actions = [
            {
                "store_id": str(l.get("store_id", "")),
                "store_name": l.get("store_name", ""),
                "action": l.get("action", ""),
                "reason": l.get("reason", ""),
                "at": str(l.get("timestamp", ""))[:19]
            }
            for l in db_logs
            if str(l.get("action", "")).startswith("ACTION_")
        ][:5]
        return {
            "bot_status": _read_persisted_bot_state(),
            "last_cycle_at": None,
            "seconds_since_last_cycle": None,
            "cycle_count": 0,
            "total_stores_processed": 0,
            "next_cycle_in_seconds": None,
            "last_actions_taken": last_actions,
            "source": "db_fallback"
        }
    except Exception:
        return {
            "bot_status": "unknown",
            "last_cycle_at": None,
            "seconds_since_last_cycle": None,
            "cycle_count": 0,
            "total_stores_processed": 0,
            "next_cycle_in_seconds": None,
            "last_actions_taken": [],
            "source": "error"
        }


class BotControlRequest(BaseModel):
    action: str


@app.post("/api/v1/admin/bot/control", summary="Control Bot Patrol Daemon (Start, Pause, Sync)")
def control_bot_endpoint(req: BotControlRequest, admin: dict = Depends(require_admin)):
    action = req.action.lower()
    
    if action not in ["start", "pause", "sync"]:
        raise HTTPException(status_code=400, detail="Aksi tidak valid. Gunakan 'start', 'pause', atau 'sync'.")
    
    # 1. Action: START
    if action == "start":
        # Try contacting HTTP API on port 8081 first
        try:
            r = urllib.request.Request("http://127.0.0.1:8081/bot/start", method="POST", headers={"User-Agent": "FoodMaster-Backend"})
            with urllib.request.urlopen(r, timeout=2.0) as resp:
                if resp.status == 200:
                    state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_START_BOT", target_state="OPEN", reason=f"Admin {admin.get('username')} mengaktifkan patroli bot via Dashboard")
                    return {"success": True, "message": "Patroli bot berhasil diaktifkan kembali.", "status": "running"}
        except Exception:
            pass
            
        # Fallback: Process is dead / unreachable -> clean stale lock and launch daemon process
        try:
            # Check if another daemon process is already running by checking PID lock
            lock_path = PROJECT_ROOT / "main-bot" / "src" / "daemon.lock"
            if lock_path.exists():
                try:
                    content = lock_path.read_text().strip()
                    if content.isdigit():
                        pid = int(content)
                        try:
                            os.kill(pid, 0)
                            # PID is alive! Do not spawn a duplicate process.
                            state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_START_BOT", target_state="OPEN", reason=f"Admin {admin.get('username')} mengaktifkan kembali daemon yang ada (PID {pid})")
                            return {"success": True, "message": "Proses daemon bot sudah berjalan.", "status": "running"}
                        except (OSError, ProcessLookupError):
                            lock_path.unlink(missing_ok=True)
                    else:
                        lock_path.unlink(missing_ok=True)
                except Exception:
                    pass

            cmd = [sys.executable, "main-bot/src/daemon.py"]
            subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_START_BOT", target_state="OPEN", reason=f"Admin {admin.get('username')} menjalankan proses daemon bot via Dashboard")
            return {"success": True, "message": "Proses daemon bot berhasil dijalankan.", "status": "running"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal menyalakan proses bot: {e}")

    # 2. Action: PAUSE
    elif action == "pause":
        try:
            r = urllib.request.Request("http://127.0.0.1:8081/bot/pause", method="POST", headers={"User-Agent": "FoodMaster-Backend"})
            with urllib.request.urlopen(r, timeout=2.0) as resp:
                if resp.status == 200:
                    state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_PAUSE_BOT", target_state="CLOSED", reason=f"Admin {admin.get('username')} menghentikan sementara bot via Dashboard")
                    return {"success": True, "message": "Patroli bot berhasil di-pause.", "status": "paused"}
        except Exception:
            pass
        
        state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_PAUSE_BOT", target_state="CLOSED", reason=f"Admin {admin.get('username')} menghentikan sementara bot via Dashboard")
        return {"success": True, "message": "Status bot diset ke paused.", "status": "paused"}

    # 3. Action: SYNC
    elif action == "sync":
        try:
            r = urllib.request.Request("http://127.0.0.1:8081/bot/sync?execute_actions=false", method="POST", headers={"User-Agent": "FoodMaster-Backend"})
            with urllib.request.urlopen(r, timeout=5.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_TRIGGER_SYNC", target_state="SYNC", reason=f"Admin {admin.get('username')} memicu instant sync via Dashboard")
                    return {"success": True, "message": "Siklus sinkronisasi instan berhasil dieksekusi.", "data": data}
        except Exception:
            pass
            
        try:
            res = worker.sync_all_stores(execute_actions=False)
            processed_count = res.get("total_stores_processed", len(res) if isinstance(res, list) else 0)
            state.record_log(store_id="SYSTEM", store_name="Bot Patrol Engine", action="ADMIN_TRIGGER_SYNC", target_state="SYNC", reason=f"Admin {admin.get('username')} memicu local sync loop via Dashboard")
            return {"success": True, "message": f"Sync selesai! Status toko di-refresh.", "data": {"processed": processed_count}}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gagal eksekusi sync: {e}")


# ── AGENCY FORCE CLOSE ENDPOINTS ─────────────────────────────────────────────

_AGENCY_INTERNAL_URL = os.getenv("AGENCY_INTERNAL_URL", "http://fm-agency:8082")


def _call_agency_api(path: str, payload: dict = None, timeout: float = 30.0) -> dict:
    """
    Memanggil internal HTTP API di container fm-agency.
    Semua action yang membutuhkan browser (force close, status) diarahkan ke sini.
    """
    url = f"{_AGENCY_INTERNAL_URL}{path}"
    try:
        if payload is not None:
            body = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
        else:
            req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except Exception:
            return {"success": False, "error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/v1/agency/outlets", summary="Get agency churn outlets with live status from DB")
def get_agency_outlets(admin: dict = Depends(require_admin)):
    try:
        churn_list, live_list = agency_sheets.get_agency_shopeefood_outlets()
        auto_enabled = db.get_agency_auto_toggle()
        # Merge real-time status dari DB (diisi oleh fm-agency daemon)
        statuses = db.get_agency_outlet_statuses()
        for outlet in churn_list:
            store_id = outlet.get("store_id", "")
            db_status = statuses.get(store_id, {})
            outlet["shopee_status"] = db_status.get("shopee_status", "UNKNOWN")
            outlet["last_checked"] = db_status.get("last_checked")
            outlet["last_action"] = db_status.get("last_action", "")
        # Query patrol status dari fm-agency internal API
        patrol_running = False
        try:
            agency_status = _call_agency_api("/status", timeout=3.0)
            patrol_running = agency_status.get("agency_state", {}).get("status") == "running"
        except Exception:
            pass
        return {
            "success": True,
            "outlets": churn_list,
            "total_churn": len(churn_list),
            "total_live": len(live_list),
            "auto_force_close_enabled": auto_enabled,
            "patrol_running": patrol_running,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil data sheet Agency: {e}")


@app.post("/api/v1/agency/toggle-auto", summary="Set auto force close toggle state")
def set_agency_toggle(req: AgencyToggleRequest, admin: dict = Depends(require_admin)):
    try:
        db.set_agency_auto_toggle(req.enabled)
        state.record_log(
            store_id="AGENCY_SYSTEM",
            store_name="Agency Force Close Engine",
            action="ADMIN_TOGGLE_AGENCY_AUTO",
            target_state="ENABLED" if req.enabled else "DISABLED",
            reason=f"Admin {admin.get('username')} mengubah Auto Force Close ke {'ON' if req.enabled else 'OFF'}"
        )
        return {
            "success": True,
            "auto_force_close_enabled": req.enabled,
            "message": f"Auto Force Close berhasil diset ke {'ON' if req.enabled else 'OFF'}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengubah toggle Agency: {e}")


@app.post("/api/v1/agency/force-close-single", summary="Proxy force close ke fm-agency container")
def agency_force_close_single(req: AgencyForceCloseRequest, admin: dict = Depends(require_admin)):
    if db.get_agency_auto_toggle():
        raise HTTPException(
            status_code=400,
            detail="Tombol eksekusi manual ter-disable saat Auto Force Close aktif."
        )
    try:
        # Proxy request ke fm-agency internal API
        res = _call_agency_api("/force-close", payload={"store_id": req.store_id})
        if res.get("success"):
            state.record_log(
                store_id=req.store_id,
                store_name=req.store_id,
                action="AGENCY_FORCE_CLOSE_SINGLE",
                target_state="CLOSED",
                reason=f"Admin {admin.get('username')} memicu manual force close outlet churn {req.store_id}"
            )
        return res.get("result", res)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal eksekusi force close: {e}")


@app.get("/api/v1/agency/patrol/status", summary="Get fm-agency container patrol status")
def agency_patrol_status(admin: dict = Depends(require_admin)):
    result = _call_agency_api("/status", timeout=3.0)
    return result
