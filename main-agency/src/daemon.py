"""
main-agency/src/daemon.py
==========================
24/7 Continuous Patrol Daemon untuk Agency Churn Bot (fm-agency container).

Behaviour:
  - Selalu berjalan (loop continuous, interval 5 menit per cycle).
  - Membaca flag `auto_force_close_enabled` dari DB di setiap cycle.
  - Jika flag OFF: hanya inspect status, tidak ada action.
  - Jika flag ON:  inspect + force close outlet yang OPEN.
  - Menyimpan hasil inspeksi ke tabel `agency_outlet_status` di PostgreSQL.
  - Automatic Browser Crash Recovery: jika driver mati/corrupt, buat session baru.
  - Menjalankan internal HTTP server di port 8082 untuk trigger manual dari fm-backend.
"""

import os
import sys
import signal
import time
import logging
import threading
from datetime import datetime
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
_DAEMON_DIR = Path(__file__).resolve().parent
_MAIN_AGENCY_ROOT = _DAEMON_DIR.parent
_PROJECT_ROOT = _MAIN_AGENCY_ROOT.parent
_SRC_DIR = _PROJECT_ROOT / "src"

for p in [str(_SRC_DIR), str(_DAEMON_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agency-daemon")

# ── Imports ────────────────────────────────────────────────────────────────────
from backend import db
from agency import runner as agency_runner
from agency import browser as agency_browser
import agency_api

# ── Constants ──────────────────────────────────────────────────────────────────
PATROL_CYCLE_SECONDS = int(os.getenv("AGENCY_PATROL_INTERVAL", "300"))
RUNNING = True


def handle_signal(sig, frame):
    global RUNNING
    log.info("[DAEMON] Signal %d received — initiating graceful shutdown...", sig)
    RUNNING = False
    agency_api.AGENCY_STATE["status"] = "stopped"


def _manual_force_close_handler(store_id: str) -> dict:
    log.info("[DAEMON] Manual force close triggered for store_id: %s", store_id)
    return agency_runner.run_agency_force_close_patrol(target_store_id=store_id)


def _ensure_valid_driver():
    """Helper to initialize or recover an active Selenium driver instance."""
    session = agency_browser.get_agency_session(close_browser=False)
    if session and "driver" in session:
        return session["driver"]
    return None


def run_daemon():
    global RUNNING

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("=" * 70)
    log.info("  Agency Churn Bot Daemon — fm-agency")
    log.info("  Patrol interval: %d detik per cycle", PATROL_CYCLE_SECONDS)
    log.info("=" * 70)

    try:
        db.init_db()
        log.info("[DAEMON] Database initialized.")
    except Exception as e:
        log.error("[DAEMON] DB init failed: %s", e)
        sys.exit(1)

    agency_api.register_force_close_callback(_manual_force_close_handler)
    agency_api.start_agency_api_server_background()

    log.info("[DAEMON] Initializing agency browser session...")
    driver = _ensure_valid_driver()
    if not driver:
        log.error("[DAEMON] Failed to initialize browser session. Exiting.")
        sys.exit(1)

    with agency_runner._patrol_lock:
        agency_runner._patrol_driver = driver
        agency_runner._patrol_running = True

    agency_api.AGENCY_STATE["status"] = "running"
    log.info("[DAEMON] Browser session ready. Starting patrol loop...")

    cycle_count = 0

    try:
        while RUNNING:
            cycle_count += 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log.info("[CYCLE #%d] Starting patrol at %s", cycle_count, now_str)

            auto_fc = db.get_agency_auto_toggle()

            try:
                # Test driver health before starting cycle
                try:
                    _ = driver.current_url
                except Exception:
                    log.warning("[DAEMON] Driver appears unresponsive or crashed. Restarting session...")
                    agency_browser.cleanup_agency_driver(driver)
                    driver = _ensure_valid_driver()
                    if not driver:
                        log.error("[DAEMON] Failed to recreate driver after crash. Sleeping 30s...")
                        time.sleep(30)
                        continue
                    with agency_runner._patrol_lock:
                        agency_runner._patrol_driver = driver

                result = agency_runner._run_patrol_cycle(driver, auto_fc_enabled=auto_fc)

                agency_api.AGENCY_STATE.update({
                    "status": "running",
                    "cycle_count": cycle_count,
                    "last_cycle_at": now_str,
                    "next_cycle_in_seconds": PATROL_CYCLE_SECONDS,
                    "last_actions": result,
                })

                log.info(
                    "[CYCLE #%d] Done. Processed=%d Closed=%d Stopped=%d Errors=%d",
                    cycle_count,
                    result.get("processed", 0),
                    result.get("closed", 0),
                    result.get("stopped", 0),
                    result.get("errors", 0),
                )
            except Exception as e:
                log.error("[CYCLE #%d] Cycle error: %s", cycle_count, e)

            log.info("[DAEMON] Waiting %d seconds (5 minutes) before starting Cycle #%d...", PATROL_CYCLE_SECONDS, cycle_count + 1)
            for remaining in range(PATROL_CYCLE_SECONDS, 0, -1):
                if not RUNNING:
                    break
                agency_api.AGENCY_STATE["next_cycle_in_seconds"] = remaining
                time.sleep(1)

            agency_api.AGENCY_STATE["next_cycle_in_seconds"] = 0

    finally:
        log.info("[DAEMON] Shutting down — closing browser...")
        agency_api.AGENCY_STATE["status"] = "stopped"
        with agency_runner._patrol_lock:
            agency_runner._patrol_driver = None
            agency_runner._patrol_running = False
        agency_browser.cleanup_agency_driver(driver)
        log.info("[DAEMON] Agency patrol daemon stopped.")


if __name__ == "__main__":
    run_daemon()
