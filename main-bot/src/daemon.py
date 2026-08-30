"""
daemon.py
=========
24/7 Continuous Background Scheduler Daemon for FoodMaster ShopeeFood Automation.

Executes periodic evaluation loops to auto-open or auto-close stores based on:
1. Vercel Toggle State
2. Subscription Status
3. Admin Suspension Status
4. Regular & Special Operating Hours
"""

import sys
import time
import signal
import argparse
import os
import fcntl
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from logger import get_logger
from core.network import is_internet_available
import db
import worker
import browser
import scheduler

log = get_logger("daemon")

RUNNING = True
IDLE_REEVALUATION_SECONDS = 30


import fcntl

LOCK_FILE_PATH = Path(__file__).resolve().parent / "daemon.lock"
_lock_file_handle = None


import socket


def is_port_in_use(port: int = 8081) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cleanup_stale_lock():
    if LOCK_FILE_PATH.exists():
        try:
            content = LOCK_FILE_PATH.read_text().strip()
            if content.isdigit():
                pid = int(content)
                if not is_pid_alive(pid):
                    LOCK_FILE_PATH.unlink(missing_ok=True)
            else:
                LOCK_FILE_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def acquire_single_instance_lock() -> bool:
    global _lock_file_handle
    if _lock_file_handle is not None:
        return False
    
    # 1. Check if port 8081 is already bound by an active daemon
    if is_port_in_use(8081):
        log.warning("⚠️ Socket lock check: Port 8081 is already in use by an active daemon.")
        return False

    cleanup_stale_lock()

    try:
        f = open(LOCK_FILE_PATH, "w")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.write(str(os.getpid()))
        f.flush()
        _lock_file_handle = f
        return True
    except (IOError, OSError):
        return False


def release_single_instance_lock():
    global _lock_file_handle
    if _lock_file_handle:
        try:
            fcntl.flock(_lock_file_handle, fcntl.LOCK_UN)
            _lock_file_handle.close()
            if LOCK_FILE_PATH.exists():
                LOCK_FILE_PATH.unlink()
        except Exception:
            pass
        _lock_file_handle = None


def handle_signal(sig, frame):
    global RUNNING
    log.info(f"🛑 Received signal {sig}. Initiating graceful shutdown...")
    RUNNING = False


def run_daemon(interval_seconds: int = 60, once: bool = False, dry_run: bool = False):
    global RUNNING

    if not acquire_single_instance_lock():
        log.warning("⚠️ Another daemon instance is already running (Lock active). Exiting to prevent duplication.")
        return

    # Register signal handlers for graceful exit
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info("=" * 80)
    log.info(f"⚙️ [DAEMON ENGINE] Starting 24/7 Background Scheduler...")
    log.info(f"⏱️ Interval: {interval_seconds} seconds | Mode: {'SINGLE CYCLE (ONCE)' if once else 'CONTINUOUS 24/7'} | Dry Run: {dry_run}")
    log.info("=" * 80)

    # Initialize DB
    db.init_state()

    # Launch HTTP Control & Trace API Server on Port 8081
    try:
        import bot_api
        bot_api.start_bot_api_server_background()
        log.info("📡 Inter-service Control & Trace API Server started on port 8081.")
    except Exception as api_err:
        log.warning(f"⚠️ Could not start Bot Control API: {api_err}")

    # ── SERVICE STARTUP WARMUP & SHOPEE DASHBOARD LOGIN ──────────
    if not dry_run:
        log.info("🚀 [SERVICE STARTUP] Performing initial Shopee Dashboard session login & warmup...")
        try:
            worker.warmup_all_account_sessions()
        except Exception as e:
            log.warning(f"⚠️ [SERVICE STARTUP] Warmup warning: {e}")

    cycle_count = 0

    while RUNNING:
        # Check if bot is paused — check both in-memory state AND persisted file state
        try:
            import bot_api
            # Re-read persisted file state on every loop iteration
            persisted = bot_api._load_persisted_state()
            persisted_status = persisted.get("status", "running")
            if persisted_status == "paused":
                bot_api.BOT_STATE["status"] = "paused"
            elif persisted_status == "running" and bot_api.BOT_STATE["status"] == "paused":
                # Admin resumed via API — sync back in-memory state
                bot_api.BOT_STATE["status"] = "running"

            if bot_api.BOT_STATE["status"] == "paused":
                log.info("[DAEMON] Bot patrol is currently PAUSED. Waiting for START command...")
                time.sleep(3)
                continue
        except Exception:
            pass

        # ── Network Health Gate Check ──
        if not is_internet_available():
            log.warning("⚠️ [NETWORK OFFLINE] Internet connection is unavailable. Pausing store sync cycle...")
            try:
                import bot_api
                bot_api.BOT_STATE["network_status"] = "offline"
                bot_api.BOT_STATE["next_cycle_in_seconds"] = 15
            except Exception:
                pass
            for _ in range(15):
                if not RUNNING:
                    break
                time.sleep(1)
            continue

        try:
            import bot_api
            bot_api.BOT_STATE["network_status"] = "online"
        except Exception:
            pass

        cycle_count += 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"\n🔄 [CYCLE #{cycle_count}] Running sync evaluation at {now_str}...")
        next_sleep_seconds = interval_seconds
        next_sleep_reason = "default interval"

        try:
            # Dispatch one merchant group at a time. Re-read runtime state after
            # every group so a newly detected mismatch can move to the front.
            processed_keys = set()
            cycle_actions = []
            total_stores_processed = 0
            total_outlets_loaded = 0
            last_result = {}
            initial_patrol_pending = True
            while RUNNING:
                current_outlets = db.fetch_merchant_outlets_from_db()
                total_outlets_loaded = max(total_outlets_loaded, len(current_outlets))
                queue = scheduler.build_queue(current_outlets)
                available = [item for item in queue if item.merchant_key not in processed_keys]
                selected = scheduler.select_next_group(available)
                if selected is None and initial_patrol_pending and available:
                    # A fresh process must read live state once before trusting
                    # cached heartbeat due times from the database.
                    selected = available[0]
                if selected is None:
                    initial_patrol_pending = False
                    next_sleep_seconds = scheduler.seconds_until_next(queue, fallback_seconds=interval_seconds)
                    next_sleep_reason = "merchant group berikutnya jatuh tempo"
                    break

                log.info(
                    "🏬 [MERCHANT SCHEDULER] Dispatching %s outlets for '%s' (Account: %s, P%d)...",
                    len(selected.due_store_ids) or 1,
                    selected.portal_name,
                    selected.username,
                    selected.priority,
                )
                last_result = worker.sync_all_stores(
                    execute_actions=not dry_run,
                    default_interval_seconds=interval_seconds,
                    target_groups={selected.merchant_key},
                )
                processed_keys.add(selected.merchant_key)
                cycle_actions.extend(last_result.get("actions_taken", []))
                total_stores_processed += last_result.get("total_stores_processed", 0)

                # A single --once invocation dispatches one merchant group. In
                # continuous mode the loop drains each currently due group.
                if once:
                    break

            result = {
                "success": True,
                "total_stores_processed": total_stores_processed,
                "total_outlets_loaded": total_outlets_loaded,
                "actions_taken": cycle_actions,
                "next_wake_hint_seconds": next_sleep_seconds,
                "next_wake_hint_reason": next_sleep_reason,
                "processed_merchant_groups": last_result.get("processed_merchant_groups", []),
            }
            log.info(
                f"  ✅ Cycle #{cycle_count} Finished. Runtime outlets loaded: {result['total_outlets_loaded']} | "
                f"Stores processed: {result['total_stores_processed']}"
            )
            next_sleep_seconds = max(1, int(result.get("next_wake_hint_seconds") or interval_seconds))
            next_sleep_reason = result.get("next_wake_hint_reason") or "default interval"
            if next_sleep_seconds > IDLE_REEVALUATION_SECONDS:
                # Rebuild the DB-backed queue frequently so dashboard changes
                # can interrupt a stale heartbeat or boundary hint.
                next_sleep_seconds = IDLE_REEVALUATION_SECONDS
                next_sleep_reason = "re-evaluasi state ringan"
            
            try:
                import bot_api
                bot_api.BOT_STATE["cycle_count"] = cycle_count
                bot_api.BOT_STATE["last_cycle_at"] = now_str
                bot_api.BOT_STATE["total_stores_processed"] = result.get("total_stores_processed", 0)
                bot_api.BOT_STATE["last_actions"] = result.get("actions_taken", [])
            except Exception:
                pass

            if result["actions_taken"]:
                log.info(f"  ⚡ Actions Taken in Cycle #{cycle_count} ({len(result['actions_taken'])}):")
                for act in result["actions_taken"]:
                    log.info(f"     -> Store {act['store_id']} ({act['store_name']}): {act['action']} ({act['reason']})")
            else:
                log.info(f"  💤 All stores in sync. No actions required.")

        except Exception as e:
            log.error(f"❌ Error in daemon cycle #{cycle_count}: {e}")

        if once or not RUNNING:
            log.info(f"🏁 Daemon single cycle execution completed.")
            break

        if next_sleep_seconds < interval_seconds:
            log.info(
                f"⏳ Waiting {next_sleep_seconds} seconds until next cycle "
                f"({next_sleep_reason})..."
            )
        else:
            log.info(f"⏳ Waiting {next_sleep_seconds} seconds until next cycle...")
        # Sleep in 1-second chunks for responsive SIGINT handling + countdown tracking
        for remaining in range(next_sleep_seconds, 0, -1):
            if not RUNNING:
                break
            try:
                import bot_api
                bot_api.BOT_STATE["next_cycle_in_seconds"] = remaining
            except Exception:
                pass
            time.sleep(1)
        try:
            import bot_api
            bot_api.BOT_STATE["next_cycle_in_seconds"] = 0
        except Exception:
            pass

    release_single_instance_lock()
    log.info("👋 Daemon Engine stopped gracefully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoodMaster Automation 24/7 Daemon Engine")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Interval between sync cycles in seconds")
    parser.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate decisions without calling live Shopee APIs")
    parser.add_argument("--headless", action="store_true", default=None, help="Run browser in headless mode")
    parser.add_argument("--no-headless", action="store_false", dest="headless", help="Run browser in GUI mode")

    args = parser.parse_args()
    if args.headless is not None:
        os.environ["HEADLESS"] = "true" if args.headless else "false"
    run_daemon(interval_seconds=args.interval_seconds, once=args.once, dry_run=args.dry_run)
