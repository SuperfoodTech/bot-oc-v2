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
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from backend import db, realtime, state, worker
from backend import apps_script
from backend import vb
from backend.pause_utils import FULL_DAY_MINUTES, resolve_pause_window
from core.timezones import normalize_timezone, timezone_for
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
    UserPauseRequest
)


class VBStatusRequest(BaseModel):
    status: str
    duration_type: Optional[str] = None
    custom_minutes: Optional[int] = None
    custom_until: Optional[str] = None


def _is_within_shopee_schedule(store: dict, now_dt: datetime) -> bool:
    """Return whether a store may be manually changed in its local timezone."""
    local_now = now_dt.astimezone(timezone_for(store.get("timezone")))
    return db.is_within_shopee_schedule(store.get("shopee_regular_hours"), local_now)


def _build_store_status_response(store: Dict[str, Any]) -> StoreStatusResponse:
    return StoreStatusResponse(
        store_id=store["store_id"],
        store_name=store["store_name"],
        merchant_name=store["merchant_name"],
        nama_portal=store.get("nama_portal", store.get("merchant_name", "")),
        account_username=store["account_username"],
        nama_pemilik=store.get("nama_pemilik", ""),
        paket=store.get("paket", "3 Bulan"),
        tanggal_mulai_layanan=store.get("tanggal_mulai_layanan", ""),
        tanggal_berakhir_layanan=store.get("tanggal_berakhir_layanan", ""),
        vercel_link=store.get("vercel_link", ""),
        vercel_password=store.get("vercel_password", ""),
        google_email=store.get("google_email", ""),
        special_hours=store.get("special_hours", ""),
        vercel_status=store["vercel_status"],
        shopee_status=store["shopee_status"],
        shopee_regular_hours=store.get("shopee_regular_hours") or {},
        subscription_status=store["subscription_status"],
        is_suspended=bool(store["is_suspended"]),
        alasan_penangguhan=store.get("alasan_penangguhan", ""),
        pause_until=store["pause_until"],
        pause_mode=store.get("pause_mode"),
        timezone=store.get("timezone", "Asia/Jakarta"),
        last_synced_at=store["last_synced_at"],
        last_action=store.get("last_action", "no change"),
        last_toggle_action_raw=store.get("last_toggle_action_raw"),
        last_toggle_reason=store.get("last_toggle_reason", ""),
        last_toggle_at=store.get("last_toggle_at"),
        desired_state=store.get("desired_state"),
        live_state=store.get("live_state"),
        bot_phase=store.get("bot_phase"),
        schedule_available=store.get("schedule_available"),
        within_operating_schedule=store.get("within_operating_schedule"),
        display_toggle_on=store.get("display_toggle_on"),
        display_toggle_disabled=store.get("display_toggle_disabled"),
        display_toggle_reason=store.get("display_toggle_reason"),
        display_status_bucket=store.get("display_status_bucket"),
        display_status_label=store.get("display_status_label"),
        display_status_tone=store.get("display_status_tone"),
        display_note=store.get("display_note"),
    )


def _hydrate_outlet_transition(transition: Dict[str, Any]) -> Dict[str, Any]:
    store_id = str(transition.get("store_id") or "").strip()
    if not store_id:
        return dict(transition)

    snapshot = state.get_store_by_id(store_id)
    if not snapshot:
        return dict(transition)

    merged = dict(snapshot)
    merged.update(
        {
            "success": transition.get("success", True),
            "code": transition.get("code"),
            "detail": transition.get("detail"),
            "store_id": store_id,
            "store_name": transition.get("store_name") or snapshot.get("store_name", ""),
            "owner_name": transition.get("owner_name") or snapshot.get("nama_pemilik", ""),
            "vercel_status": transition.get("vercel_status", snapshot.get("vercel_status")),
            "pause_until": transition.get("pause_until", snapshot.get("pause_until")),
            "changed_at": transition.get("changed_at") or snapshot.get("last_toggle_at"),
            "reason": transition.get("reason") or snapshot.get("last_toggle_reason", ""),
        }
    )
    return merged


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
USER_SESSION_COOKIE = "foodmaster_user_session"
USER_SESSION_SECRET = os.getenv("USER_SESSION_SECRET", ADMIN_SESSION_SECRET)
USER_SESSION_TTL_SECONDS = 60 * 60 * 12
GOOGLE_AUTH_ENABLED = os.getenv("GOOGLE_AUTH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


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


def _sign_user_session(owner: str, slug: Optional[str]) -> str:
    payload = {
        "role": "MERCHANT",
        "owner": owner,
        "slug": slug or "",
        "exp": int(datetime.now().timestamp()) + USER_SESSION_TTL_SECONDS,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(USER_SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _read_user_session(token: Optional[str]) -> Optional[dict]:
    if not token or "." not in token:
        return None
    encoded, signature = token.rsplit(".", 1)
    expected = hmac.new(USER_SESSION_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if payload.get("role") != "MERCHANT" or int(payload.get("exp", 0)) < int(datetime.now().timestamp()):
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
    raise HTTPException(status_code=403, detail="Tambah mitra dari Dashboard sedang dinonaktifkan. Gunakan Google Sheet lalu Fetch.")


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
    if not GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Google Auth sedang dinonaktifkan.")
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
    if not GOOGLE_AUTH_ENABLED:
        raise HTTPException(status_code=404, detail="Google Auth sedang dinonaktifkan.")
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
    state.sync_expired_user_pauses()
    users_data = state.admin_get_all_users_with_stores()
    return {"success": True, "users": users_data}


@app.post("/api/v1/admin/sync-source", summary="Admin: Import the published spreadsheet into PostgreSQL")
def admin_sync_source(admin: dict = Depends(require_admin)):
    try:
        from core.import_sheet import run_import_sheet
        summary = run_import_sheet()
        return {"success": True, "summary": summary, "message": "Data Google Sheet berhasil di-fetch ke database."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Source import failed: {exc}") from exc


@app.get("/api/v1/admin/vb/brands", summary="Admin: List Virtual Brands")
def admin_vb_brands(admin: dict = Depends(require_admin)):
    return {"success": True, "brands": vb.list_brands()}


@app.get("/api/v1/admin/vb/brands/{brand_id}", summary="Admin: Virtual Brand detail")
def admin_vb_brand_detail(brand_id: UUID, admin: dict = Depends(require_admin)):
    result = vb.brand_detail(str(brand_id))
    if not result:
        raise HTTPException(status_code=404, detail="Brand VB tidak ditemukan.")
    return {"success": True, "brand": result}


@app.patch("/api/v1/admin/vb/brands/{brand_id}/status", summary="Admin: Request Virtual Brand status")
def admin_vb_request_status(brand_id: UUID, req: VBStatusRequest, admin: dict = Depends(require_admin)):
    requested = req.status.strip().upper()
    if requested not in {"ON", "PAUSED"}:
        raise HTTPException(status_code=422, detail="Status VB harus ON atau PAUSED.")
    pause_until = None
    if requested == "PAUSED":
        now_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
        try:
            if (req.duration_type or "").strip().lower() in {"rest_of_day", "sepanjang_hari", "today"}:
                # VB brands do not have Shopee operating-hour schedules.
                pause_until = now_dt + timedelta(minutes=FULL_DAY_MINUTES)
            else:
                pause_until, _duration_mins, _label = resolve_pause_window(
                    now_dt,
                    req.duration_type or "",
                    custom_until=req.custom_until,
                    custom_minutes=req.custom_minutes,
                    allow_default=False,
                )
        except ValueError as exc:
            message = str(exc)
            if message == "Durasi pause wajib dipilih.":
                message = "Durasi pause VB wajib dipilih."
            raise HTTPException(status_code=422, detail=message) from exc
    result = vb.request_status(str(brand_id), requested, admin["sub"], pause_until=pause_until)
    if not result:
        raise HTTPException(status_code=404, detail="Brand VB tidak ditemukan.")
    return {"success": True, "brand": result, "message": "Perubahan disimpan dan menunggu giliran brand berikutnya."}


@app.post("/api/v1/admin/vb/import", summary="Admin: Import Virtual Brand matrix")
def admin_vb_import(admin: dict = Depends(require_admin)):
    try:
        return {"success": True, "summary": vb.import_sheet(admin["sub"])}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Import VB gagal: {exc}") from exc


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
    raise HTTPException(status_code=403, detail="Tambah mitra dari Dashboard sedang dinonaktifkan. Gunakan Google Sheet lalu Fetch.")
    base_url = str(request.base_url).rstrip("/")
    try:
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
            base_url=base_url,
            google_email=req.google_email,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"success": True, "data": state.get_store_by_id(req.store_id)}


@app.post("/api/v1/admin/suspend", summary="Admin: Toggle User/Store Suspension")
def admin_suspend(req: AdminSuspendRequest, admin: dict = Depends(require_admin)):
    raise HTTPException(status_code=403, detail="Pengaturan akun dari Dashboard sedang dinonaktifkan.")
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
    raise HTTPException(status_code=403, detail="Perpanjangan layanan dari Dashboard sedang dinonaktifkan.")
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
    raise HTTPException(status_code=403, detail="Edit outlet dari Dashboard sedang dinonaktifkan. Ubah data di Google Sheet lalu Fetch.")
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' tidak ditemukan.")

    try:
        success = state.admin_edit_outlet(
            store_id=req.store_id,
            nama_pemilik=req.nama_pemilik,
            nama_portal=req.nama_portal,
            nama_panjang_outlet=req.nama_panjang_outlet,
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
    try:
        apps_script.set_store_import_status(store_id, "Nonaktif")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gagal mengubah status Google Sheet: {exc}") from exc
    try:
        success = state.delete_store(store_id)
    except Exception as exc:
        # Keep the dashboard consistent if the database delete fails after the Sheet write.
        state.deactivate_store(store_id)
        raise HTTPException(status_code=500, detail=f"Google Sheet sudah Nonaktif, tetapi database gagal dihapus: {exc}") from exc
    if not success:
        state.deactivate_store(store_id)
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
def user_login(req: UserLoginRequest, response: Response):
    user_info = state.user_authenticate(req.passcode, req.slug)
    if not user_info:
        response.delete_cookie(USER_SESSION_COOKIE)
        raise HTTPException(status_code=401, detail="Link atau passcode mitra tidak valid.")

    pemilik = user_info.get("nama_pemilik", "Fando")
    state.sync_expired_user_pauses()
    outlets = state.user_get_outlets(pemilik)
    response.set_cookie(
        USER_SESSION_COOKIE,
        _sign_user_session(pemilik, user_info.get("link_slug") or req.slug),
        max_age=USER_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )

    return {
        "success": True,
        "nama_pemilik": pemilik,
        "passcode": req.passcode,
        "total_outlets": len(outlets),
        "outlets": outlets
    }


@app.get("/api/v1/admin/events", summary="Admin realtime outlet state events")
def admin_events(admin: dict = Depends(require_admin)):
    return StreamingResponse(
        realtime.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/user/events", summary="Mitra realtime outlet state events")
def user_events(user_session: Optional[str] = Cookie(default=None, alias=USER_SESSION_COOKIE)):
    session = _read_user_session(user_session)
    if not session:
        raise HTTPException(status_code=401, detail="Mitra session expired.")
    owner = session.get("owner", "")
    return StreamingResponse(
        realtime.stream(lambda event: event.get("owner_name") == owner),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/user/outlets", summary="User Link: Get Outlets for Authenticated User")
def user_get_outlets(nama_pemilik: str = Query(..., description="Nama Pemilik / Mitra")):
    state.sync_expired_user_pauses()
    outlets = state.user_get_outlets(nama_pemilik)
    return {"success": True, "nama_pemilik": nama_pemilik, "total_outlets": len(outlets), "outlets": outlets}


@app.post("/api/v1/user/pause", summary="User Link: Pause Store with Selected Duration")
def user_pause_store(
    req: UserPauseRequest,
    admin_session: Optional[str] = Cookie(default=None, alias=ADMIN_SESSION_COOKIE),
):
    admin_account = _read_admin_session(admin_session)
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")

    if not admin_account and (store.get("is_suspended") or store.get("suspension_status") == "SUSPENDED"):
        reason = store.get("alasan_penangguhan") or "Tindakan admin"
        raise HTTPException(status_code=403, detail=f"Outlet ditangguhkan oleh Admin (Alasan: {reason}). Silakan hubungi CS.")

    now_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
    if not admin_account and not _is_within_shopee_schedule(store, now_dt):
        raise HTTPException(status_code=403, detail="Di luar jadwal operasional")

    try:
        pause_mode = "REST_OF_DAY" if req.duration_type.strip().lower() in {"rest_of_day", "sepanjang_hari", "today"} else ("CUSTOM" if req.duration_type.strip().lower() in {"custom", "waktu_lain"} else "FIXED_DURATION")
        pause_until_dt, duration_mins, label = resolve_pause_window(
            now_dt,
            req.duration_type,
            schedule=store.get("shopee_regular_hours") or {},
            timezone=normalize_timezone(store.get("timezone")),
            custom_until=req.custom_until,
            custom_minutes=req.custom_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pause_until_str = pause_until_dt.strftime("%Y-%m-%d %H:%M:%S")
    pause_start_time_ms = int(now_dt.timestamp() * 1000)
    pause_end_time_ms = int(pause_until_dt.timestamp() * 1000)

    # Admin uses the same request contract as Mitra, but keeps Admin ownership in the audit log.
    action = "ADMIN_PAUSE_STORE" if admin_account else "USER_PAUSE_STORE"
    reason = (
        f"Admin {admin_account.get('username')} set store OFF via Mitra pause modal until {pause_until_str} WIB"
        if admin_account
        else f"User set store OFF with duration: {label} (Until {pause_until_str} WIB); pause_start_time_ms={pause_start_time_ms}; pause_end_time_ms={pause_end_time_ms}"
    )
    apply_toggle = state.apply_admin_toggle if admin_account else state.apply_user_toggle
    transition = apply_toggle(
        store_id=req.store_id,
        status="OFF",
        pause_until=pause_until_dt,
        action=action,
        target_state="CLOSED",
        reason=reason,
        pause_mode=pause_mode,
    )
    if not transition["success"]:
        raise HTTPException(status_code=403 if transition["code"] in {"suspended", "subscription_expired"} else 404, detail=transition["detail"])
    realtime.publish_outlet_state_changed(
        _hydrate_outlet_transition(transition),
        action,
        "ADMIN" if admin_account else "MITRA",
    )

    return {
        "success": True,
        "store_id": req.store_id,
        "vercel_status": "OFF",
        "duration_label": label,
        "pause_until": pause_until_str,
        "pause_start_time": pause_start_time_ms,
        "pause_end_time": pause_end_time_ms,
        "timezone": f"{store.get('timezone', 'Asia/Jakarta')}",
        "message": f"Permintaan tutup sementara tersimpan untuk outlet {req.store_id} ({label})."
    }


@app.post("/api/v1/user/resume", summary="User Link: Resume / Open Store")
def user_resume_store(store_id: str = Query(..., description="Target Store ID")):
    store = state.get_store_by_id(store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' not found.")

    if store.get("is_suspended") or store.get("suspension_status") == "SUSPENDED":
        reason = store.get("alasan_penangguhan") or "Tindakan admin"
        raise HTTPException(status_code=403, detail=f"Outlet ditangguhkan oleh Admin (Alasan: {reason}). Silakan hubungi CS.")

    now_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
    if not _is_within_shopee_schedule(store, now_dt):
        raise HTTPException(status_code=403, detail="Di luar jadwal operasional")

    transition = state.apply_user_toggle(
        store_id=store_id,
        status="ON",
        pause_until=None,
        action="USER_RESUME_STORE",
        target_state="OPEN",
        reason="User manually turned Vercel Toggle ON (Auto Open)",
    )
    if not transition["success"]:
        raise HTTPException(status_code=403 if transition["code"] in {"suspended", "subscription_expired"} else 404, detail=transition["detail"])
    realtime.publish_outlet_state_changed(
        _hydrate_outlet_transition(transition),
        "USER_RESUME_STORE",
        "MITRA",
    )

    return {
        "success": True,
        "store_id": store_id,
        "vercel_status": transition["vercel_status"],
        "message": f"Permintaan buka tersimpan untuk outlet {store_id}."
    }


@app.get("/api/v1/user/history", summary="User Link: Get Audit History for Outlets")
def user_get_history(store_ids: str = Query(..., description="Comma-separated store IDs (e.g. 21897166,22403325)")):
    id_list = [s.strip() for s in store_ids.split(",") if s.strip()]
    logs = state.get_recent_logs(limit=50, store_ids=id_list)
    return {"success": True, "total_logs": len(logs), "logs": logs}


# ── COMPATIBILITY & REST ENDPOINTS ─────────────────────────────────────────────

@app.get("/api/v1/stores", response_model=List[StoreStatusResponse], summary="Get All Store Statuses")
def list_stores(admin: dict = Depends(require_admin)):
    state.sync_expired_user_pauses()
    stores = state.get_all_stores()
    return [_build_store_status_response(store) for store in stores]


@app.get("/api/v1/stores/{store_id}", response_model=StoreStatusResponse, summary="Get Single Store Status")
def get_store_detail(store_id: str, admin: dict = Depends(require_admin)):
    state.sync_expired_user_pauses()
    s = state.get_store_by_id(store_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"Store ID '{store_id}' not found.")
    return _build_store_status_response(s)


@app.post("/api/v1/toggle", summary="Toggle Vercel status for store")
def toggle_store(req: ToggleRequest, admin: dict = Depends(require_admin)):
    store = state.get_store_by_id(req.store_id)
    if not store:
        raise HTTPException(status_code=404, detail=f"Store ID '{req.store_id}' not found.")
    next_status = req.status.upper()
    pause_until = None
    pause_label = ""
    pause_mode = None
    if next_status == "OFF":
        now_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
        try:
            if req.duration_type:
                pause_mode = "REST_OF_DAY" if req.duration_type.strip().lower() in {"rest_of_day", "sepanjang_hari", "today"} else "CUSTOM"
                pause_until, _duration_mins, pause_label = resolve_pause_window(
                    now_dt,
                    req.duration_type,
                    schedule=store.get("shopee_regular_hours") or {},
                    timezone=normalize_timezone(store.get("timezone")),
                    custom_until=req.custom_until,
                    custom_minutes=req.pause_duration_minutes,
                )
            elif req.pause_duration_minutes is not None:
                pause_mode = "FIXED_DURATION"
                if req.pause_duration_minutes <= 0:
                    raise ValueError("Durasi pause harus lebih besar dari 0 menit.")
                pause_until = now_dt + timedelta(minutes=req.pause_duration_minutes)
                pause_label = f"{req.pause_duration_minutes} Menit"
            else:
                pause_mode = "REST_OF_DAY"
                pause_until, _duration_mins, pause_label = resolve_pause_window(
                    now_dt,
                    "rest_of_day",
                    schedule=store.get("shopee_regular_hours") or {},
                    timezone=normalize_timezone(store.get("timezone")),
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    pause_until_str = pause_until.astimezone(ZoneInfo(normalize_timezone(store.get("timezone")))).strftime("%Y-%m-%d %H:%M:%S") if pause_until else ""
    transition = state.apply_admin_toggle(
        store_id=req.store_id,
        status=next_status,
        pause_until=pause_until,
        action="ADMIN_PAUSE_STORE" if next_status == "OFF" else "ADMIN_RESUME_STORE",
        target_state="CLOSED" if next_status == "OFF" else "OPEN",
        pause_mode=pause_mode,
        reason=(f"Admin {admin.get('username')} set store OFF via Dashboard ({pause_label}) until {pause_until_str} WIB" if next_status == "OFF" and pause_until_str
                else f"Admin {admin.get('username')} set store OFF via Dashboard" if next_status == "OFF"
                else f"Admin {admin.get('username')} set store ON via Dashboard"),
    )
    if not transition["success"]:
        raise HTTPException(status_code=404, detail=transition["detail"])
    realtime.publish_outlet_state_changed(
        _hydrate_outlet_transition(transition),
        "ADMIN_PAUSE_STORE" if next_status == "OFF" else "ADMIN_RESUME_STORE",
        "ADMIN",
    )
    return {
        "success": True,
        "store_id": req.store_id,
        "new_vercel_status": transition["vercel_status"],
        "pause_until": transition["pause_until"]
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


@app.get("/api/v1/admin/logs/overview", summary="Admin: Compact logs for regular bot and VB")
def get_logs_overview(limit: int = Query(default=40, ge=1, le=100), admin: dict = Depends(require_admin)):
    return state.get_log_overview(limit=limit)


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
