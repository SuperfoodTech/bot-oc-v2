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
sys.path.insert(0, str(SCRIPT_DIR))

from core.logger import get_logger
from backend import db, worker

log = get_logger("daemon")

RUNNING = True


import fcntl

LOCK_FILE_PATH = Path(__file__).resolve().parent / "daemon.lock"
_lock_file_handle = None


def acquire_single_instance_lock() -> bool:
    global _lock_file_handle
    if _lock_file_handle is not None:
        return False
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
    db.init_db()
    cycle_count = 0

    while RUNNING:
        cycle_count += 1
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.info(f"\n🔄 [CYCLE #{cycle_count}] Running sync evaluation at {now_str}...")

        try:
            result = worker.sync_all_stores(execute_actions=not dry_run)
            log.info(f"  ✅ Cycle #{cycle_count} Finished. Stores Processed: {result['total_stores_processed']}")
            
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

        log.info(f"⏳ Waiting {interval_seconds} seconds until next cycle...")
        # Sleep in 1-second chunks for responsive SIGINT handling
        for _ in range(interval_seconds):
            if not RUNNING:
                break
            time.sleep(1)

    release_single_instance_lock()
    log.info("👋 Daemon Engine stopped gracefully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FoodMaster Automation 24/7 Daemon Engine")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Interval between sync cycles in seconds")
    parser.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate decisions without calling live Shopee APIs")

    args = parser.parse_args()
    run_daemon(interval_seconds=args.interval_seconds, once=args.once, dry_run=args.dry_run)
