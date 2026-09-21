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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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
LOCAL_TZ = ZoneInfo("Asia/Jakarta")
FAILED_RETRY_TRACKER: dict[str, dict] = {}


import fcntl

LOCK_FILE_PATH = Path(__file__).resolve().parent / "daemon.lock"
_lock_file_handle = None


import socket


def is_port_in_use(port: int | None = None) -> bool:
    if port is None:
        port = int(os.getenv("BOT_API_PORT", "8082"))
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
    
    # 1. Check if bot api port is already bound by an active daemon
    api_port = int(os.getenv("BOT_API_PORT", "8082"))
    if is_port_in_use(api_port):
        log.warning(f"⚠️ Socket lock check: Port {api_port} is already in use by an active daemon.")
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
            dispatched_actionable_stores = set()
            cycle_actions = []
            cycle_merchant_groups = []
            total_stores_processed = 0
            total_outlets_loaded = 0
            last_result = {}
            while RUNNING:
                current_outlets = db.fetch_merchant_outlets_from_db()
                total_outlets_loaded = max(total_outlets_loaded, len(current_outlets))

                # Prune inactive / turned OFF outlets from retry tracker
                now_dt = datetime.now(LOCAL_TZ)
                outlet_by_sid = {o.store_id: o for o in current_outlets}
                for sid in list(FAILED_RETRY_TRACKER.keys()):
                    out = outlet_by_sid.get(sid)
                    if not out:
                        FAILED_RETRY_TRACKER.pop(sid, None)
                        continue
                    tgt = (out.status_utama or "OFF").strip().upper()
                    if tgt in ("OFF", "CLOSE", "CLOSED") or out.penangguhan.strip().lower() == "ya":
                        FAILED_RETRY_TRACKER.pop(sid, None)

                # Check which retries are due right now
                due_retry_sids = {
                    sid for sid, info in FAILED_RETRY_TRACKER.items()
                    if info.get("next_retry_at") and info["next_retry_at"] <= now_dt
                }

                queue = scheduler.build_queue(current_outlets)
                # If any due retry stores exist, ensure their merchant item has priority 100 and includes those sids
                if due_retry_sids:
                    augmented_queue = []
                    for item in queue:
                        item_sids = {o.store_id for o in current_outlets if scheduler.merchant_key(o) == item.merchant_key}
                        item_retries = tuple(sid for sid in due_retry_sids if sid in item_sids)
                        if item_retries:
                            combined_actionable = tuple(dict.fromkeys(item.actionable_store_ids + item_retries))
                            augmented_queue.append(scheduler.MerchantQueueItem(
                                merchant_key=item.merchant_key,
                                username=item.username,
                                portal_name=item.portal_name,
                                due_at=min(item.due_at, now_dt),
                                priority=max(item.priority, 100),
                                due_store_ids=tuple(dict.fromkeys(item.due_store_ids + item_retries)),
                                outlet_count=item.outlet_count,
                                actionable_count=len(combined_actionable),
                                actionable_store_ids=combined_actionable,
                                reasons=item.reasons + ("priority action retry",),
                            ))
                        else:
                            augmented_queue.append(item)
                    queue = sorted(augmented_queue, key=lambda it: (-it.priority, it.due_at, -it.actionable_count, it.merchant_key))

                available = [
                    item for item in queue
                    if item.merchant_key not in processed_keys
                    or any(sid not in dispatched_actionable_stores for sid in item.actionable_store_ids)
                ]
                selected = scheduler.select_next_group(available)
                if selected is None and available:
                    # VB patrols by portal. Even a portal without an urgent
                    # action gets one pass so random Shopee closures are seen
                    # before the next cycle, without switching per brand.
                    selected = min(
                        available,
                        key=lambda item: (
                            item.due_at,
                            -item.priority,
                            item.merchant_key,
                        ),
                    )
                if selected is None:
                    next_sleep_seconds = scheduler.seconds_until_next(queue, fallback_seconds=interval_seconds)
                    next_sleep_reason = "merchant group berikutnya jatuh tempo"
                    break

                pending_actionable_ids = tuple(
                    sid for sid in selected.actionable_store_ids if sid not in dispatched_actionable_stores
                )
                is_actionable = len(pending_actionable_ids) > 0
                target_store_ids = set(pending_actionable_ids) if is_actionable else None

                if is_actionable:
                    dispatched_actionable_stores.update(pending_actionable_ids)
                    retry_matches = [sid for sid in pending_actionable_ids if sid in due_retry_sids]
                    if retry_matches:
                        log.info(
                            "⚡ [RETRY EXPRESS LANE] Dispatching %d actionable store(s) (including %d retry: %s) for '%s' (Account: %s, P%d)...",
                            len(target_store_ids),
                            len(retry_matches),
                            retry_matches,
                            selected.portal_name,
                            selected.username,
                            selected.priority,
                        )
                    else:
                        log.info(
                            "⚡ [EXPRESS LANE] Dispatching %d actionable store(s) %s for '%s' (Account: %s, P%d)...",
                            len(target_store_ids),
                            target_store_ids,
                            selected.portal_name,
                            selected.username,
                            selected.priority,
                        )
                else:
                    log.info(
                        "🚶 [PATROL LANE] Dispatching %s outlets for '%s' (Account: %s, P%d)...",
                        selected.outlet_count,
                        selected.portal_name,
                        selected.username,
                        selected.priority,
                    )

                last_result = worker.sync_all_stores(
                    execute_actions=not dry_run,
                    default_interval_seconds=interval_seconds,
                    target_groups={selected.merchant_key},
                    target_store_ids=target_store_ids,
                )
                if not is_actionable:
                    processed_keys.add(selected.merchant_key)

                # Update FAILED_RETRY_TRACKER based on action results
                for act in last_result.get("actions_taken", []):
                    sid = act.get("store_id")
                    if not sid or sid == "SYSTEM":
                        continue
                    is_success = bool(act.get("success"))
                    if is_success:
                        if sid in FAILED_RETRY_TRACKER:
                            log.info(
                                f"  ✅ [RETRY RESOLVED] Store {sid} ({act.get('store_name')}) recovered successfully and removed from retry collection."
                            )
                            FAILED_RETRY_TRACKER.pop(sid, None)
                    else:
                        info = FAILED_RETRY_TRACKER.get(sid, {
                            "merchant_key": act.get("merchant_key") or selected.merchant_key,
                            "attempts": 0,
                            "action": act.get("action"),
                        })
                        info["attempts"] += 1
                        info["last_reason"] = act.get("reason", "")
                        if info["attempts"] == 1:
                            delay_sec = 15
                        elif info["attempts"] == 2:
                            delay_sec = 45
                        elif info["attempts"] == 3:
                            delay_sec = 90
                        else:
                            delay_sec = 900  # 15 minutes cooldown after 3+ consecutive failures
                            log.warning(
                                f"  ⚠️ [RETRY COOLDOWN] Store {sid} reached {info['attempts']} failed attempts. Cooling down for 15 minutes."
                            )
                        info["next_retry_at"] = datetime.now(LOCAL_TZ) + timedelta(seconds=delay_sec)
                        FAILED_RETRY_TRACKER[sid] = info

                cycle_actions.extend(last_result.get("actions_taken", []))
                cycle_merchant_groups.extend(last_result.get("processed_merchant_groups", []))
                total_stores_processed += last_result.get("total_stores_processed", 0)

                # Check if any brands with pending actions have completed all actionable stores
                pending_brand_ids = db.get_pending_brand_ids()
                if pending_brand_ids:
                    try:
                        next_outlets = db.fetch_merchant_outlets_from_db()
                        next_queue = scheduler.build_queue(next_outlets)
                        remaining_actionable_sids = set()
                        for item in next_queue:
                            for sid in item.actionable_store_ids:
                                if sid not in dispatched_actionable_stores:
                                    remaining_actionable_sids.add(sid)

                        brand_store_map = db.get_brand_store_ids(pending_brand_ids)
                        completed_brands = [
                            bid for bid in pending_brand_ids
                            if not (brand_store_map.get(bid, set()) & remaining_actionable_sids)
                        ]
                        if completed_brands:
                            db.flush_pending_brand_notifications(brand_ids=completed_brands)
                    except Exception as brand_flush_err:
                        log.warning(f"⚠️ Error in immediate brand-completion flush: {brand_flush_err}")

                # One --once invocation completes one full portal sweep.

            # Flush aggregated notifications for all processed brands in this cycle
            try:
                db.flush_pending_brand_notifications()
            except Exception as flush_err:
                log.warning(f"⚠️ Error flushing brand notifications: {flush_err}")

            result = {
                "success": True,
                "total_stores_processed": total_stores_processed,
                "total_outlets_loaded": total_outlets_loaded,
                "actions_taken": cycle_actions,
                "next_wake_hint_seconds": next_sleep_seconds,
                "next_wake_hint_reason": next_sleep_reason,
                "processed_merchant_groups": cycle_merchant_groups,
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

            # Check if any pending retry in FAILED_RETRY_TRACKER needs an earlier wake up
            if FAILED_RETRY_TRACKER:
                now_check = datetime.now(LOCAL_TZ)
                pending_delays = [
                    (info["next_retry_at"] - now_check).total_seconds()
                    for info in FAILED_RETRY_TRACKER.values()
                    if info.get("next_retry_at") and info["next_retry_at"] > now_check
                ]
                if pending_delays:
                    min_retry_delay = max(5, int(min(pending_delays)))
                    if min_retry_delay < next_sleep_seconds:
                        next_sleep_seconds = min_retry_delay
                        next_sleep_reason = "antrean retry outlet gagal"
            
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
        finally:
            try:
                import gc
                gc.collect()
            except Exception:
                pass

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
