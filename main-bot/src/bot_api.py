"""
bot_api.py
==========
Lightweight HTTP Control & Trace API Server for main-bot running on port 8081.
Allows the Web Dashboard to monitor, start, pause, and trigger instant sync cycles on main-bot.
"""

import os
import threading
import time
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import db
import worker
from logger import get_logger

log = get_logger("bot_api")

app = FastAPI(
    title="FoodMaster Bot Control & Trace API",
    description="Internal inter-service HTTP API for controlling and tracing main-bot automation daemon",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Bot State
BOT_STATE = {
    "status": "running",          # "running" | "paused" | "stopped"
    "mode": "24/7 Patrol",
    "last_cycle_at": None,
    "cycle_count": 0,
    "total_stores_processed": 0,
    "last_actions": []
}

BOT_API_PORT = int(os.getenv("BOT_API_PORT", "8081"))


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


@app.post("/bot/start", summary="Resume Bot Patrol Loop")
def start_bot():
    BOT_STATE["status"] = "running"
    log.info("▶️ [BOT CONTROL API] Received START command. Bot patrol resumed.")
    return {"success": True, "bot_status": "running", "message": "Bot patrol loop resumed."}


@app.post("/bot/pause", summary="Pause Bot Patrol Loop")
def pause_bot():
    BOT_STATE["status"] = "paused"
    log.info("⏸️ [BOT CONTROL API] Received PAUSE command. Bot patrol paused.")
    return {"success": True, "bot_status": "paused", "message": "Bot patrol loop paused."}


@app.post("/bot/sync", summary="Trigger Instant Store Patrol Cycle")
def trigger_instant_sync(execute_actions: bool = False):
    log.info(f"⚡ [BOT CONTROL API] Received INSTANT SYNC command (execute_actions={execute_actions}). Executing patrol cycle...")
    try:
        res = worker.sync_all_stores(execute_actions=execute_actions)
        BOT_STATE["cycle_count"] += 1
        BOT_STATE["last_cycle_at"] = datetime.now().isoformat()
        BOT_STATE["total_stores_processed"] = res.get("total_stores_processed", 0)
        BOT_STATE["last_actions"] = res.get("actions_taken", [])
        return {"success": True, "data": res}
    except Exception as e:
        log.error(f"❌ Instant sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/bot/logs", summary="Fetch Live Automation Logs")
def get_bot_logs(limit: int = 50):
    return {"success": True, "logs": db.get_recent_logs(limit=limit)}


def start_bot_api_server_background():
    """
    Launches the Uvicorn server in a separate background thread.
    """
    def run_server():
        log.info(f"🌐 [BOT API SERVER] Starting HTTP Control & Trace API on port {BOT_API_PORT}...")
        uvicorn.run(app, host="0.0.0.0", port=BOT_API_PORT, log_level="warning")

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    return t
