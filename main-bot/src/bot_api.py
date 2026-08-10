"""
bot_api.py
==========
Lightweight HTTP Control & Trace API Server for main-bot running on port 8081.
Allows the Web Dashboard to monitor, start, pause, and trigger instant sync cycles on main-bot.
"""

import os
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import db
import worker
from logger import get_logger

log = get_logger("bot_api")

# ─── State File (persists pause/running across restarts) ───────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BOT_STATE_FILE = SCRIPT_DIR / "bot_state.json"


def _load_persisted_state() -> dict:
    """Load persisted bot state from disk."""
    try:
        if BOT_STATE_FILE.exists():
            data = json.loads(BOT_STATE_FILE.read_text())
            return data
    except Exception:
        pass
    return {"status": "running"}


def _save_persisted_state(status: str):
    """Persist bot status to disk so pause survives daemon restarts."""
    try:
        BOT_STATE_FILE.write_text(json.dumps({
            "status": status,
            "updated_at": datetime.now().isoformat()
        }))
    except Exception as e:
        log.warning(f"⚠️ Could not persist bot state: {e}")


# ─── In-Memory Bot State ───────────────────────────────────────────────────────
_persisted = _load_persisted_state()

BOT_STATE = {
    "status": _persisted.get("status", "running"),   # "running" | "paused" | "stopped"
    "mode": "24/7 Patrol",
    "last_cycle_at": None,
    "cycle_count": 0,
    "total_stores_processed": 0,
    "last_actions": [],         # List of last actions taken (store opens/closes)
    "next_cycle_in_seconds": None,
}

BOT_API_PORT = int(os.getenv("BOT_API_PORT", "8081"))


app = FastAPI(
    title="FoodMaster Bot Control & Trace API",
    description="Internal inter-service HTTP API for controlling and tracing main-bot automation daemon",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="Bot API Health & Status Trace")
@app.get("/bot/status", summary="Bot Status Trace")
def get_bot_status() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "bot_status": BOT_STATE["status"],
        "mode": BOT_STATE["mode"],
        "last_cycle_at": BOT_STATE["last_cycle_at"] or datetime.now().isoformat(),
        "cycle_count": BOT_STATE["cycle_count"],
        "total_stores_processed": BOT_STATE["total_stores_processed"],
        "last_actions": BOT_STATE["last_actions"][-10:],
        "timestamp": datetime.now().isoformat()
    }


@app.get("/bot/activity", summary="Bot Activity Evidence — last cycle detail + actions taken")
def get_bot_activity() -> Dict[str, Any]:
    """
    Returns concrete evidence of bot activity:
    - last cycle timestamp
    - cycle count
    - total stores processed
    - last actions taken (open/close with store name and reason)
    - next cycle countdown
    """
    last_cycle_at = BOT_STATE.get("last_cycle_at")
    seconds_since_last_cycle = None

    if last_cycle_at:
        try:
            parsed = datetime.fromisoformat(last_cycle_at)
            seconds_since_last_cycle = int((datetime.now() - parsed).total_seconds())
        except Exception:
            pass

    # Fallback: read from DB if bot hasn't completed a cycle yet
    last_actions = BOT_STATE.get("last_actions", [])
    if not last_actions:
        try:
            db_logs = db.get_recent_logs(limit=10)
            last_actions = [
                {
                    "store_id": str(l.get("store_id", "")),
                    "store_name": l.get("store_name", ""),
                    "action": l.get("action", ""),
                    "reason": l.get("reason", ""),
                    "at": str(l.get("timestamp", ""))[:19]
                }
                for l in db_logs
                if l.get("action", "").startswith("ACTION_")
            ][:5]
        except Exception:
            last_actions = []

    return {
        "bot_status": BOT_STATE["status"],
        "last_cycle_at": last_cycle_at,
        "seconds_since_last_cycle": seconds_since_last_cycle,
        "cycle_count": BOT_STATE["cycle_count"],
        "total_stores_processed": BOT_STATE["total_stores_processed"],
        "next_cycle_in_seconds": BOT_STATE.get("next_cycle_in_seconds"),
        "last_actions_taken": last_actions,
        "timestamp": datetime.now().isoformat()
    }


@app.post("/bot/start", summary="Resume Bot Patrol Loop")
def start_bot():
    BOT_STATE["status"] = "running"
    _save_persisted_state("running")
    log.info("[BOT CONTROL API] Received START command. Bot patrol resumed.")
    return {"success": True, "bot_status": "running", "message": "Bot patrol loop resumed."}


@app.post("/bot/pause", summary="Pause Bot Patrol Loop")
def pause_bot():
    BOT_STATE["status"] = "paused"
    _save_persisted_state("paused")
    log.info("[BOT CONTROL API] Received PAUSE command. Bot patrol paused.")
    return {"success": True, "bot_status": "paused", "message": "Bot patrol loop paused."}


@app.post("/bot/sync", summary="Trigger Instant Store Patrol Cycle")
def trigger_instant_sync(execute_actions: bool = False):
    log.info(f"[BOT CONTROL API] Received INSTANT SYNC command (execute_actions={execute_actions}). Executing patrol cycle...")
    try:
        res = worker.sync_all_stores(execute_actions=execute_actions)
        BOT_STATE["cycle_count"] += 1
        BOT_STATE["last_cycle_at"] = datetime.now().isoformat()
        BOT_STATE["total_stores_processed"] = res.get("total_stores_processed", 0)
        BOT_STATE["last_actions"] = res.get("actions_taken", [])
        return {"success": True, "data": res}
    except Exception as e:
        log.error(f"Instant sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bot/logs", summary="Fetch Live Automation Logs")
def get_bot_logs(limit: int = 50):
    return {"success": True, "logs": db.get_recent_logs(limit=limit)}


def start_bot_api_server_background():
    """
    Launches the Uvicorn server in a separate background thread.
    """
    def run_server():
        log.info(f"[BOT API SERVER] Starting HTTP Control & Trace API on port {BOT_API_PORT}...")
        uvicorn.run(app, host="0.0.0.0", port=BOT_API_PORT, log_level="warning")

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    return t
