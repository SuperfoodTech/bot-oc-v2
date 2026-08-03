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

import os
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse

import db
import worker
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

# ── ENVIRONMENT-AWARE ROUTE RESOLUTION ─────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
PORT = os.getenv("PORT", "8080")
PROD_HOST = os.getenv("PROD_HOST", "168.144.143.203")

def get_app_base_url(request: Request = None) -> str:
    """
    Determines base URL dynamically:
    - Local Development: http://localhost:{PORT}
    - Production Mode : http://168.144.143.203:{PORT}
    Can infer directly from incoming Request host header if available.
    """
    if request and request.headers.get("host"):
        host = request.headers.get("host")
        scheme = request.headers.get("x-forwarded-proto", "http")
        return f"{scheme}://{host}"
    
    if ENVIRONMENT == "production":
        return f"http://{PROD_HOST}:{PORT}"
    return f"http://localhost:{PORT}"

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
def admin_page(request: Request):
    admin_html = TEMPLATES_DIR / "admin_dashboard.html"
    if not admin_html.exists():
        raise HTTPException(status_code=404, detail="Admin template not found.")
    content = admin_html.read_text(encoding="utf-8")
    base_url = get_app_base_url(request)
    content = content.replace("{{ BASE_URL }}", base_url)
    return HTMLResponse(content=content)


@app.get("/app", response_class=HTMLResponse, summary="User Link Mobile Dashboard Web Page")
@app.get("/mitra/{slug}", response_class=HTMLResponse, summary="User Link Mobile Dashboard Web Page")
def user_page(request: Request, slug: Optional[str] = None):
    user_html = TEMPLATES_DIR / "user_dashboard.html"
    if not user_html.exists():
        raise HTTPException(status_code=404, detail="User template not found.")
    content = user_html.read_text(encoding="utf-8")
    base_url = get_app_base_url(request)
    content = content.replace("{{ BASE_URL }}", base_url)
    return HTMLResponse(content=content)


# ── SERVICE HEALTHCHECK ────────────────────────────────────────────────────────

@app.get("/api/v1/health", summary="Service Health Check")
def health_check(request: Request):
    return {
        "status": "healthy",
        "service": "FoodMaster Integrated Web App & API",
        "environment": ENVIRONMENT,
        "base_url": get_app_base_url(request),
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
def admin_generate_link(req: AdminGenerateLinkRequest, request: Request):
    base_url = get_app_base_url(request)
    result = db.admin_generate_user_link(req.nama_pemilik, req.passcode, base_url=base_url)
    db.record_log(
        store_id="ADMIN",
        store_name="ADMIN_SYSTEM",
        action="GENERATE_USER_LINK",
        target_state="CREATED",
        reason=f"Generated Vercel link for '{req.nama_pemilik}' (Passcode: {result['passcode']})"
    )
    return {"success": True, "data": result}


# ── INTER-SERVICE BOT CONTROL & TRACE ENDPOINTS ─────────────────────────────
BOT_API_URL = os.getenv("BOT_API_URL", "http://localhost:8081")

@app.get("/api/v1/admin/bot/status", summary="Admin: Fetch Bot Trace & Live Status")
def admin_bot_status():
    try:
        resp = requests.get(f"{BOT_API_URL}/health", timeout=3)
        if resp.status_code == 200:
            return {"success": True, "bot_online": True, "data": resp.json()}
    except Exception:
        pass
    return {
        "success": False,
        "bot_online": False,
        "data": {
            "bot_status": "offline",
            "message": "Bot Automation Engine (port 8081) is currently unreachable."
        }
    }

@app.post("/api/v1/admin/bot/control", summary="Admin: Trigger Bot Command (start/pause/sync)")
def admin_bot_control(command: str = Query(..., description="Command: start, pause, or sync")):
    cmd = command.lower().strip()
    if cmd not in ("start", "pause", "sync"):
        raise HTTPException(status_code=400, detail="Invalid command. Use 'start', 'pause', or 'sync'.")
    try:
        url = f"{BOT_API_URL}/bot/{cmd}"
        resp = requests.post(url, timeout=10)
        if resp.status_code == 200:
            db.record_log(
                store_id="ADMIN",
                store_name="ADMIN_SYSTEM",
                action=f"BOT_CONTROL_{cmd.upper()}",
                target_state=cmd.upper(),
                reason=f"Admin sent '{cmd}' command to Bot Automation Engine via Port 8081."
            )
            return {"success": True, "data": resp.json()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Bot Engine (port 8081) unreachable: {e}")


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
def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    action: Optional[str] = Query(default=None, description="Filter by action name"),
    search: Optional[str] = Query(default=None, description="Search keyword in store_id, name, or reason")
):
    logs = db.get_recent_logs(limit=limit)
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
