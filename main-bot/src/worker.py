"""
worker.py
=========
Backend Worker Engine that syncs store states, evaluates PRD rules, and triggers direct API open/close actions or Selenium browser login.
"""

import sys
import os
import math
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from logger import get_logger
from sheets import MerchantOutlet
from decision import (
    evaluate_outlet_status,
    get_pause_recheck_delay_seconds,
    ACTION_OPEN,
    ACTION_CLOSE,
    ACTION_NO_CHANGE,
)
import browser
import db
from shopee import store_status

log = get_logger("backend_worker")

# Filter account usernames allowed for bot execution (Default: auto7313 only)
ALLOWED_USERNAMES_ENV = os.getenv("ALLOWED_USERNAMES", "auto7313")
ALLOWED_USERNAMES = {u.strip() for u in ALLOWED_USERNAMES_ENV.split(",") if u.strip()}
# One long-lived browser per Shopee bot account. Merchant switching happens in
# this browser; the bot does not close/reopen Chrome for every outlet action.
ACTIVE_SESSIONS = {}
SYNC_LOCK = threading.Lock()


def _normalize_live_status(live_info: dict) -> str:
    """Preserve Shopee's PAUSE state instead of collapsing it into CLOSED."""
    if not isinstance(live_info, dict):
        return "UNKNOWN"
    pause_info = live_info.get("pause_info") or {}
    pause_start = pause_info.get("pause_start_time", 0) if isinstance(pause_info, dict) else 0
    try:
        pause_start = float(pause_start or 0)
    except (TypeError, ValueError):
        pause_start = 0
    if pause_start > 0:
        return "PAUSE"
    return "ON" if live_info.get("status_str") == "OPEN" else "CLOSED"


def _pause_end_time_ms(outlet: MerchantOutlet):
    """Convert the DB's local pause end time to Shopee's epoch milliseconds."""
    pause_until = getattr(outlet, "pause_until", "") or ""
    if not pause_until:
        return None
    try:
        end_dt = datetime.fromisoformat(str(pause_until).replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=ZoneInfo("Asia/Jakarta"))
        now_dt = datetime.now(ZoneInfo("Asia/Jakarta"))
        if end_dt <= now_dt:
            log.info("  ℹ️ Pause time %s for Store %s has already passed. Using default pause.", pause_until, outlet.store_id)
            return None
        return int(end_dt.timestamp() * 1000)
    except (TypeError, ValueError):
        log.warning("  ⚠️ Invalid pause_until for Store %s: %s", outlet.store_id, pause_until)
        return None


def _normalize_shopee_regular_hours(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    """Convert Shopee regular-hours relative seconds into read-only WIB ranges."""
    # Shopee regular-hours API uses 1=Sunday through 7=Saturday.
    day_names = {1: "Minggu", 2: "Senin", 3: "Selasa", 4: "Rabu", 5: "Kamis", 6: "Jumat", 7: "Sabtu"}
    normalized = {name: [] for name in day_names.values()}
    for day in payload.get("regular_hours", []) if isinstance(payload, dict) else []:
        if not isinstance(day, dict):
            continue
        try:
            name = day_names.get(int(day.get("weekday", 0)))
        except (TypeError, ValueError):
            continue
        if not name or not day.get("config_enabled"):
            continue
        for interval in day.get("intervals", []) or []:
            if not isinstance(interval, dict):
                continue
            try:
                start = max(0, int(interval.get("start_relative_sec", 0)))
                end = max(0, int(interval.get("end_relative_sec", 0)))
            except (TypeError, ValueError):
                continue
            if end <= start or end > 24 * 60 * 60:
                continue
            value = f"{start // 3600:02d}:{(start % 3600) // 60:02d}-{end // 3600:02d}:{(end % 3600) // 60:02d}"
            if value not in normalized[name]:
                normalized[name].append(value)
        normalized[name].sort()
    return normalized


def _mark_schedule_fetch_retry(outlet: MerchantOutlet, message: str) -> None:
    outlet.schedule_fetch_status = "FETCH_RETRYING"
    try:
        db.mark_schedule_fetch_retry(outlet.store_id, message)
    except Exception as persist_err:
        log.warning(
            f"  ⚠️ [REGULAR HOURS STATUS SYNC] Gagal menyimpan status retry fetch jadwal Store {outlet.store_id}: "
            f"{persist_err}"
        )


def _mark_schedule_fetch_empty(outlet: MerchantOutlet) -> None:
    outlet.regular_hours = {}
    outlet.shopee_regular_hours = {}
    outlet.schedule_fetch_status = "FETCHED_EMPTY"
    try:
        db.mark_schedule_fetch_empty(outlet.store_id)
    except Exception as persist_err:
        log.warning(
            f"  ⚠️ [REGULAR HOURS STATUS SYNC] Jadwal Shopee Store {outlet.store_id} kosong tetapi gagal "
            f"menyimpan statusnya ke DB: {persist_err}"
        )
    else:
        log.info(
            f"  ✅ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} terkonfirmasi belum memiliki "
            "jadwal Shopee yang diatur."
        )


def warmup_all_account_sessions():
    """
    On service startup, iterates over registered merchant accounts and ensures
    each account is logged in to the Shopee Partner Dashboard, saving active sessions.
    Only processes accounts matching ALLOWED_USERNAMES (e.g. auto7313).
    """
    log.info(f"🚀 [STARTUP WARMUP] Initializing & verifying Shopee Dashboard sessions for whitelisted accounts {ALLOWED_USERNAMES}...")
    try:
        outlets = db.fetch_merchant_outlets_from_db()
    except Exception as e:
        log.warning(f"⚠️ [STARTUP WARMUP] Could not fetch control source outlets for warmup: {e}")
        return

    processed_accounts = set()
    for outlet in outlets:
        username = (outlet.username or "").strip()
        if not username or username in processed_accounts:
            continue

        # Exclude usernames not in whitelist (username != auto7313)
        if ALLOWED_USERNAMES and username not in ALLOWED_USERNAMES:
            log.info(f"  ⏭️ [STARTUP WARMUP] Excluding account '{username}' (username != auto7313).")
            continue

        processed_accounts.add(username)

        session_file = PROJECT_ROOT / "src" / "data" / f"session_{username}.json"
        browser.set_session_file(session_file)

        # Warmup: verifikasi login saja, tanpa switch ke portal tertentu.
        # Switch portal dilakukan per-merchant-group saat sync_all_stores berjalan.
        log.info(f"  🌐 [STARTUP WARMUP] Initializing active browser session for account '{username}'...")
        try:
            session = browser.get_session(
                username=username,
                password=outlet.password,
                phone=outlet.hp,
                target_name=None,  # Jangan paksa switch portal saat warmup
                close_browser=False,
                interactive=False,
            )
            if session and session.get("shopee_tob_token"):
                ACTIVE_SESSIONS[username] = session
                log.info(f"  ✅ [STARTUP WARMUP] Account '{username}' session active & stored (Entity ID: {session.get('shopee_tob_entity_id')}).")
            else:
                log.warning(f"  ⚠️ [STARTUP WARMUP] Account '{username}' login completed, session pending.")
        except Exception as ex:
            log.warning(f"  ⚠️ [STARTUP WARMUP] Account '{username}' warmup exception: {ex}")


def execute_outlet_shopee_action(outlet: MerchantOutlet, action: str) -> bool:
    """
    Executes actual Open/Close action on Shopee Partner API or via Selenium browser login.
    Excludes execution if outlet.username != auto7313.
    """
    # Exclude accounts not in ALLOWED_USERNAMES whitelist
    if ALLOWED_USERNAMES and outlet.username not in ALLOWED_USERNAMES:
        log.info(f"  ⏭️ [SHOPEE EXECUTION] Excluding Store {outlet.store_id} - username '{outlet.username}' != auto7313.")
        return False

    log.info(f"🌐 [SHOPEE EXECUTION] Initiating {action} for Store {outlet.store_id} ({outlet.nama_panjang_outlet})...")

    # Set session file according to outlet username
    if outlet.username:
        account_session_file = PROJECT_ROOT / "src" / "data" / f"session_{outlet.username}.json"
        if account_session_file.exists():
            browser.set_session_file(account_session_file)

    cached = ACTIVE_SESSIONS.get(outlet.username)
    session = cached or browser.get_session(
        username=outlet.username,
        password=outlet.password,
        phone=outlet.hp,
        target_name=outlet.nama_portal,
        close_browser=False,
        interactive=False,
    )

    if session:
        driver = session.get("driver")
        ACTIVE_SESSIONS[outlet.username] = session

        # Primary Action: In-Browser XHR via store_status module (Instant execution)
        if driver and outlet.store_id:
            m_id = str(getattr(outlet, "merchant_id", "") or "14367488")
            if action == ACTION_OPEN:
                success = store_status.open_store_action(driver, outlet.store_id, merchant_id=m_id)
            else:
                success = store_status.pause_store_action(
                    driver,
                    outlet.store_id,
                    merchant_id=m_id,
                    pause_end_time_ms=_pause_end_time_ms(outlet),
                )
            if success:
                log.info(f"  ✅ [IN-BROWSER XHR SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                return True

    log.error(f"  ❌ Gagal mengeksekusi {action} untuk Store {outlet.store_id}.")
    return False


def sync_all_stores(
    execute_actions: bool = True,
    default_interval_seconds: Optional[int] = None,
    target_groups: Optional[set[tuple[str, str]]] = None,
) -> Dict[str, Any]:
    if not SYNC_LOCK.acquire(blocking=False):
        log.warning("⏭️ [BACKEND WORKER] Sync skipped because another cycle is still in progress.")
        return {
            "success": True,
            "sync_skipped": True,
            "total_stores_processed": 0,
            "actions_taken": [],
            "message": "Sync skipped because another cycle is still in progress.",
            "next_wake_hint_seconds": 1,
            "next_wake_hint_reason": "sync sebelumnya masih berjalan",
        }

    local_tz = ZoneInfo("Asia/Jakarta")
    cycle_started_at = datetime.now(local_tz)
    log.info("🔄 [BACKEND WORKER] Starting store synchronization...")

    post_action_recheck_at: Optional[datetime] = None
    post_action_recheck_reason = "default interval"

    def _request_post_action_recheck(reason: str, delay_seconds: int = 15) -> None:
        nonlocal post_action_recheck_at, post_action_recheck_reason
        candidate_dt = datetime.now(local_tz) + timedelta(seconds=max(1, int(delay_seconds or 1)))
        if post_action_recheck_at is None or candidate_dt < post_action_recheck_at:
            post_action_recheck_at = candidate_dt
            post_action_recheck_reason = reason

    try:
        if hasattr(db, "sync_expired_user_pauses"):
            try:
                db.sync_expired_user_pauses()
            except Exception as e:
                log.warning("  ⚠️ Failed to sync expired user pauses: %s", e)

        # Runtime source of truth: PostgreSQL. Spreadsheet is import-only.
        outlets = db.fetch_merchant_outlets_from_db()
        actions_taken = []
        watched_outlets: List[MerchantOutlet] = []

        # Group outlets by account and merchant portal (nama_portal)
        # Format: { (username, nama_portal): [outlet1, outlet2, ...] }
        grouped_outlets: Dict[tuple, List[MerchantOutlet]] = {}
        for outlet in outlets:
            if ALLOWED_USERNAMES and outlet.username not in ALLOWED_USERNAMES:
                log.debug(f"  ⏭️ Excluding store {outlet.store_id} ({outlet.nama_panjang_outlet}) - username '{outlet.username}' not in ALLOWED_USERNAMES")
                continue
            key = (outlet.username, outlet.nama_portal or "")
            if key not in grouped_outlets:
                grouped_outlets[key] = []
            grouped_outlets[key].append(outlet)

        if target_groups is not None:
            grouped_outlets = {
                key: merchant_outlets
                for key, merchant_outlets in grouped_outlets.items()
                if key in target_groups
            }

        # Process each merchant portal group
        for (username, portal_name), merchant_outlets in grouped_outlets.items():
            log.info(f"🏬 [MERCHANT GROUP] Processing {len(merchant_outlets)} outlets for Merchant Portal: '{portal_name}' (Account: {username})...")

            cached = ACTIVE_SESSIONS.get(username)
            driver = cached.get("driver") if cached else None

            def _is_session_dead(drv) -> bool:
                """Return True if the WebDriver session is no longer valid."""
                if not drv:
                    return True
                try:
                    _ = drv.current_url
                    return False
                except Exception:
                    return True

            def _recover_session(reason: str) -> None:
                """Clear stale session cache and re-launch a fresh browser session."""
                nonlocal cached, driver
                log.warning(f"  🔁 [SESSION RECOVERY] Dead session detected ({reason}). Re-launching browser for account '{username}'...")
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                ACTIVE_SESSIONS.pop(username, None)
                cached = None
                driver = None
                try:
                    first_outlet = merchant_outlets[0]
                    new_session = browser.get_session(
                        username=username,
                        password=first_outlet.password,
                        phone=first_outlet.hp,
                        target_name=portal_name,
                        close_browser=False,
                        interactive=False,
                    )
                    if new_session and new_session.get("shopee_tob_token"):
                        ACTIVE_SESSIONS[username] = new_session
                        cached = new_session
                        driver = new_session.get("driver")
                        log.info(f"  ✅ [SESSION RECOVERY] Browser session restored for account '{username}' (Portal: {portal_name}).")
                    else:
                        log.warning(f"  ⚠️ [SESSION RECOVERY] Re-launch completed but session token missing for '{username}'.")
                except Exception as rec_err:
                    log.error(f"  ❌ [SESSION RECOVERY] Failed to re-launch browser for '{username}': {rec_err}")

            def _ensure_group_session_ready(reason: str) -> bool:
                nonlocal cached, driver
                cached = ACTIVE_SESSIONS.get(username) or cached
                driver = cached.get("driver") if cached else driver
                if _is_session_dead(driver):
                    _recover_session(reason)
                cached = ACTIVE_SESSIONS.get(username) or cached
                driver = cached.get("driver") if cached else None
                return bool(driver) and not _is_session_dead(driver)

            if driver:
                if _is_session_dead(driver):
                    _recover_session("invalid session id")
                else:
                    try:
                        current_merchant = ""
                        try:
                            current_merchant = driver.execute_script(
                                "return (document.querySelector('.merchantName')?.innerText || '').trim();"
                            )
                        except Exception:
                            pass

                        already_active = False
                        if portal_name and current_merchant:
                            p_norm = portal_name.lower().strip()
                            c_norm = current_merchant.lower().strip()
                            if p_norm == c_norm or p_norm in c_norm or c_norm in p_norm:
                                already_active = True

                        if already_active:
                            log.info(f"  ✅ [MERCHANT] Browser sudah aktif di portal merchant '{portal_name}' (Current UI: '{current_merchant}'). Skip switch.")
                        else:
                            log.info(f"  🔄 [MERCHANT] Current merchant di browser: '{current_merchant or 'Unknown'}' | Target group: '{portal_name}'. Executing auto_switch_merchant...")
                            sw_ok = browser.auto_switch_merchant(driver, portal_name)
                            if sw_ok:
                                log.info(f"  ✅ [MERCHANT] Switched successfully to portal merchant '{portal_name}'.")
                                tok, eid = browser.extract_tokens_from_driver(driver)
                                if cached:
                                    if tok:
                                        cached["shopee_tob_token"] = tok
                                    if eid:
                                        cached["shopee_tob_entity_id"] = eid
                            else:
                                log.warning(f"  ⚠️ [MERCHANT] auto_switch_merchant ke '{portal_name}' gagal. Initiating session recovery...")
                                _recover_session(f"switch merchant to {portal_name} failed")
                    except Exception as sw_err:
                        log.warning(f"  ⚠️ Merchant context switch warning: {sw_err}")
                        if _is_session_dead(driver):
                            _recover_session("switch merchant failed")
            else:
                try:
                    first_outlet = merchant_outlets[0]
                    session = browser.get_session(
                        username=username,
                        password=first_outlet.password,
                        phone=first_outlet.hp,
                        target_name=portal_name,
                        close_browser=False,
                        interactive=False,
                    )
                    if session and session.get("shopee_tob_token"):
                        ACTIVE_SESSIONS[username] = session
                        cached = session
                        driver = session.get("driver")
                except Exception as sess_err:
                    log.warning(f"  ⚠️ Browser session init error for merchant '{portal_name}': {sess_err}")

            _ensure_group_session_ready(f"group bootstrap for merchant '{portal_name}'")

            for outlet in merchant_outlets:
                if outlet.username:
                    browser.set_session_file(PROJECT_ROOT / "src" / "data" / f"session_{outlet.username}.json")

                driver_ready = _ensure_group_session_ready(f"before patrol Store {outlet.store_id}")
                if not driver_ready:
                    log.warning(
                        f"  ⚠️ [SESSION READY] Browser session belum siap untuk Store {outlet.store_id} "
                        f"({outlet.nama_panjang_outlet}). Bot akan memakai state DB sementara."
                    )

                log.info(f"📌 Memasuki tab Business Hours untuk Store {outlet.store_id} ({outlet.nama_panjang_outlet})...")

                is_detected = False
                if driver_ready and driver:
                    is_detected = store_status.ensure_business_hours_page(driver, store_id=outlet.store_id)
                    if not is_detected and _is_session_dead(driver):
                        _recover_session(f"business hours page lost for Store {outlet.store_id}")
                        driver_ready = _ensure_group_session_ready(f"retry patrol Store {outlet.store_id}")
                        if driver_ready and driver:
                            is_detected = store_status.ensure_business_hours_page(driver, store_id=outlet.store_id)

                if is_detected:
                    log.info(f"  ✅ [BUSINESS HOURS CONFIRMED] Target Store {outlet.store_id} ({outlet.nama_panjang_outlet}) TERDETEKSI & TER-LOAD SEMPURNA di menu Business Hours!")
                else:
                    log.warning(f"  ⚠️ [BUSINESS HOURS WARNING] Target Store {outlet.store_id} ({outlet.nama_panjang_outlet}) BELUM TERDETEKSI SEMPURNA di menu Business Hours!")

                # Keep the last known Shopee schedule in-memory unless this cycle
                # successfully fetches a newer one. This prevents multi-schedule
                # pauses from being lost when the boundary recheck lands on a
                # temporary regular-hours fetch failure.
                last_known_regular_hours = (
                    getattr(outlet, "regular_hours", None)
                    or getattr(outlet, "shopee_regular_hours", None)
                    or {}
                )
                last_known_schedule_available = any(last_known_regular_hours.values())
                current_schedule_fetch_status = str(getattr(outlet, "schedule_fetch_status", "") or "").strip().upper()
                outlet.regular_hours = last_known_regular_hours
                outlet.shopee_regular_hours = last_known_regular_hours
                schedule_identity_valid = True

                if driver_ready and driver:
                    try:
                        shopee_hours = store_status.get_regular_hours(driver, store_id=outlet.store_id)
                        if isinstance(shopee_hours, dict) and "regular_hours" in shopee_hours:
                            normalized_hours = _normalize_shopee_regular_hours(shopee_hours)
                            if not any(normalized_hours.values()):
                                _mark_schedule_fetch_empty(outlet)
                            else:
                                outlet.regular_hours = normalized_hours
                                outlet.shopee_regular_hours = normalized_hours
                                outlet.schedule_fetch_status = "READY"

                                try:
                                    db.update_shopee_regular_hours(outlet.store_id, normalized_hours)
                                except Exception as persist_err:
                                    log.warning(
                                        f"  ⚠️ [REGULAR HOURS STATUS SYNC] Jadwal Shopee Store {outlet.store_id} berhasil diambil "
                                        f"tetapi gagal disimpan ke DB: {persist_err}"
                                    )
                                else:
                                    log.info(
                                        f"  ✅ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} jadwal Shopee tersimpan "
                                        f"({sum(bool(v) for v in normalized_hours.values())} hari aktif)."
                                    )
                        elif shopee_hours is None:
                            if current_schedule_fetch_status == "FETCHED_EMPTY":
                                log.info(
                                    f"  ℹ️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} mempertahankan status jadwal kosong "
                                    "karena fetch saat ini tidak mengembalikan data."
                                )
                            elif last_known_schedule_available:
                                log.info(
                                    f"  ℹ️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} tetap memakai jadwal Shopee terakhir "
                                    "yang valid karena fetch saat ini tidak mengembalikan data."
                                )
                            else:
                                _mark_schedule_fetch_retry(outlet, "Shopee tidak mengembalikan data jadwal.")
                                log.warning(
                                    f"  ⚠️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} belum memiliki jadwal Shopee valid. "
                                    "Bot akan retry fetch pada patroli berikutnya."
                                )
                        else:
                            if current_schedule_fetch_status == "FETCHED_EMPTY":
                                log.warning(
                                    f"  ⚠️ [REGULAR HOURS STATUS SYNC] Response jadwal Shopee Store {outlet.store_id} tidak valid. "
                                    "Status jadwal kosong terakhir dipertahankan."
                                )
                            elif last_known_schedule_available:
                                log.warning(
                                    f"  ⚠️ [REGULAR HOURS STATUS SYNC] Response jadwal Shopee Store {outlet.store_id} tidak valid. "
                                    "Tetap memakai jadwal terakhir yang valid."
                                )
                            else:
                                _mark_schedule_fetch_retry(outlet, "Response jadwal Shopee tidak valid.")
                                log.warning(
                                    f"  ⚠️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} belum memiliki jadwal Shopee valid. "
                                    "Response tidak valid dan bot akan retry."
                                )
                    except store_status.StoreIdentityMismatch as identity_err:
                        schedule_identity_valid = False
                        if not last_known_schedule_available and current_schedule_fetch_status != "FETCHED_EMPTY":
                            _mark_schedule_fetch_retry(
                                outlet,
                                f"Store identity mismatch saat fetch jadwal: {identity_err}",
                            )
                        log.error(
                            f"  ❌ [REGULAR HOURS QUARANTINE] Store {outlet.store_id} dilewati pada cycle ini: {identity_err}. "
                            "Tidak ada decision/action yang dijalankan memakai jadwal yang tidak terpercaya."
                        )
                    except Exception as hours_err:
                        if current_schedule_fetch_status == "FETCHED_EMPTY":
                            log.warning(
                                f"  ⚠️ [REGULAR HOURS STATUS SYNC] Gagal menarik jadwal Shopee Store {outlet.store_id}: {hours_err}. "
                                "Status jadwal kosong terakhir dipertahankan."
                            )
                        elif last_known_schedule_available:
                            log.warning(
                                f"  ⚠️ [REGULAR HOURS STATUS SYNC] Gagal menarik jadwal Shopee Store {outlet.store_id}: {hours_err}. "
                                "Tetap memakai jadwal terakhir yang valid."
                            )
                        else:
                            _mark_schedule_fetch_retry(outlet, str(hours_err))
                            log.warning(
                                f"  ⚠️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} belum memiliki jadwal Shopee valid. "
                                "Bot akan retry setelah fetch gagal."
                            )
                else:
                    if current_schedule_fetch_status == "FETCHED_EMPTY":
                        log.info(
                            f"  ℹ️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} mempertahankan status jadwal kosong "
                            "karena sesi browser belum siap."
                        )
                    elif last_known_schedule_available:
                        log.info(
                            f"  ℹ️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} tetap memakai jadwal Shopee terakhir "
                            "yang valid karena sesi browser belum siap."
                        )
                    else:
                        _mark_schedule_fetch_retry(outlet, "Sesi browser belum siap untuk fetch jadwal.")
                        log.warning(
                            f"  ⚠️ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} belum memiliki jadwal Shopee valid "
                            "karena sesi browser belum siap. Bot akan retry."
                        )

                if driver_ready and driver:
                    live_identity_valid = True
                    try:
                        live_info = store_status.get_actual_store_status(driver, store_id=outlet.store_id)
                        if live_info and live_info.get("timezone"):
                            outlet.timezone = live_info["timezone"]
                            db.update_outlet_timezone(outlet.store_id, outlet.timezone)
                        if live_info and live_info.get("status_str") in ("OPEN", "CLOSED"):
                            actual_st = _normalize_live_status(live_info)
                            outlet.status_aktual = actual_st
                            db.update_shopee_actual_status(outlet.store_id, actual_st)
                    except store_status.StoreIdentityMismatch as identity_err:
                        live_identity_valid = False
                        log.error(
                            f"  ❌ [LIVE STATE QUARANTINE] Store {outlet.store_id} dilewati pada cycle ini: {identity_err}. "
                            "Tidak ada decision/action yang dijalankan memakai live state yang tidak terpercaya."
                        )
                    except Exception as st_err:
                        log.debug(f"  ⚠️ Live Shopee status query skipped for Store {outlet.store_id}: {st_err}")
                else:
                    live_identity_valid = True
                    log.debug(f"  ⚠️ Live Shopee status query skipped for Store {outlet.store_id}: browser session belum siap")

                watched_outlets.append(outlet)

                if not schedule_identity_valid or not live_identity_valid:
                    continue

                decision = evaluate_outlet_status(
                    outlet,
                    current_time=datetime.now(local_tz),
                    require_regular_schedule=True,
                )
                shopee_before = (outlet.status_aktual or "UNKNOWN").upper()
                vercel_status = (outlet.status_utama or "OFF").upper()

                log.info(
                    f"  🔍 [PRE-CHECK] Store {outlet.store_id} ({outlet.nama_panjang_outlet}) | "
                    f"Shopee Status Sebelum: {shopee_before} | Vercel Toggle: {vercel_status} | "
                    f"Decision: {decision.action} ({decision.reason})"
                )

                if decision.action in (ACTION_OPEN, ACTION_CLOSE) and execute_actions:
                    log.info(f"⚡ [ACTION TRIGGERED] Executing {decision.action} for Store {outlet.store_id} (Target: {decision.target_state})...")
                    exec_ok = execute_outlet_shopee_action(outlet, decision.action)
                    expected_st = "ON" if decision.target_state == "OPEN" else "PAUSE"
                    verification_note = ""
                    verification_ok = False

                    if exec_ok:
                        driver_ready = _ensure_group_session_ready(f"post action verify Store {outlet.store_id}")
                        if not driver_ready:
                            verification_note = " | Verification: pending browser recovery"
                            _request_post_action_recheck(
                                f"post-action verify tertunda untuk Store {outlet.store_id}: browser recovery"
                            )
                        else:
                            log.info(f"  🔍 [POST-EXECUTION VERIFICATION] Memverifikasi ulang status live Shopee setelah {decision.action} untuk Store {outlet.store_id}...")
                            time.sleep(1.5)
                            post_info = None
                            try:
                                post_info = store_status.get_actual_store_status(driver, store_id=outlet.store_id)
                            except Exception as post_err:
                                log.warning(f"  ⚠️ [POST-EXECUTION VERIFICATION] Gagal membaca live state pasca-aksi untuk Store {outlet.store_id}: {post_err}")

                            if post_info and post_info.get("status_str") in ("OPEN", "CLOSED"):
                                verified_st = _normalize_live_status(post_info)
                                outlet.status_aktual = verified_st
                                verification_note = f" | Verification: LIVE={verified_st}"
                                log.info(f"  ✅ [POST-EXECUTION VERIFIED] Status Live Shopee Pasca-{decision.action}: '{verified_st}' (Expected: '{expected_st}').")
                                try:
                                    db.update_shopee_actual_status(outlet.store_id, verified_st)
                                    log.info(f"  ✅ [DB STATUS SYNC] Status shopee_actual_status Store {outlet.store_id} berhasil diupdate ke '{verified_st}' di DB.")
                                except Exception as sync_err:
                                    log.warning(f"  ⚠️ Gagal mengupdate DB shopee_actual_status: {sync_err}")

                                if verified_st != expected_st:
                                    verification_note = f"{verification_note} (expected {expected_st})"
                                    _request_post_action_recheck(
                                        f"post-action verify mismatch untuk Store {outlet.store_id}: live {verified_st}, expected {expected_st}"
                                    )
                                else:
                                    verification_ok = True
                            else:
                                verification_note = " | Verification: pending recheck"
                                log.warning(
                                    f"  ⚠️ [POST-EXECUTION VERIFICATION] Live state pasca-aksi untuk Store {outlet.store_id} "
                                    "belum bisa diverifikasi. Menjadwalkan recheck cepat."
                                )
                                _request_post_action_recheck(
                                    f"post-action verify ulang untuk Store {outlet.store_id}: live state belum terbaca"
                                )
                    else:
                        verification_note = " | Verification: action failed"
                        _request_post_action_recheck(
                            f"retry action Store {outlet.store_id}: eksekusi {decision.action} gagal"
                        )

                    action_success = exec_ok and verification_ok
                    action_result = "SUCCESS" if exec_ok else "FAILED"
                    if exec_ok and not verification_ok:
                        action_result = "VERIFICATION_MISMATCH"
                    reason_text = f"{decision.reason} | Shopee Action: {action_result}{verification_note}"
                    actions_taken.append({
                        "store_id": outlet.store_id,
                        "store_name": outlet.nama_panjang_outlet,
                        "action": decision.action,
                        "target_state": decision.target_state,
                        "reason": reason_text,
                    })

                    db.record_log(
                        store_id=outlet.store_id,
                        store_name=outlet.nama_panjang_outlet,
                        action=decision.action,
                        target_state=decision.target_state,
                        reason=reason_text,
                        success=action_success,
                        error_message=None if action_success else reason_text,
                    )

        db.record_log(
            store_id="SYSTEM",
            store_name="BOT_DAEMON",
            action="SYNC_CYCLE",
            target_state="SYNCED",
            reason=f"Evaluasi bot selesai untuk {len(actions_taken)} aksi dijalankan (Filtered: username == auto7313)"
        )

        cycle_finished_at = datetime.now(local_tz)
        next_wake_hint_seconds = None
        next_wake_hint_reason = "default interval"
        if default_interval_seconds:
            next_wake_hint_seconds, next_wake_hint_reason = get_pause_recheck_delay_seconds(
                watched_outlets,
                default_interval_seconds=default_interval_seconds,
                now_dt=cycle_started_at,
                effective_now_dt=cycle_finished_at,
            )

        if post_action_recheck_at:
            post_action_delay_seconds = max(
                1,
                math.ceil((post_action_recheck_at - cycle_finished_at).total_seconds()),
            )
            if next_wake_hint_seconds is None or post_action_delay_seconds < next_wake_hint_seconds:
                next_wake_hint_seconds = post_action_delay_seconds
                next_wake_hint_reason = post_action_recheck_reason

        return {
            "success": True,
            "total_stores_processed": sum(len(group) for group in grouped_outlets.values()),
            "actions_taken": actions_taken,
            "processed_merchant_groups": [
                {"username": username, "portal_name": portal_name}
                for username, portal_name in grouped_outlets
            ],
            "message": f"Successfully processed stores for allowed usernames {ALLOWED_USERNAMES}.",
            "next_wake_hint_seconds": next_wake_hint_seconds,
            "next_wake_hint_reason": next_wake_hint_reason,
        }
    finally:
        SYNC_LOCK.release()
