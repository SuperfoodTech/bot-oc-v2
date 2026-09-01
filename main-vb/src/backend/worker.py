"""
worker.py
=========
Backend Worker Engine that syncs store states, evaluates PRD rules, and triggers direct API open/close actions or Selenium browser login.
"""

import sys
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from core.logger import get_logger
from core.sheets import MerchantOutlet
from core.decision import evaluate_outlet_status, ACTION_OPEN, ACTION_CLOSE, ACTION_NO_CHANGE
from core import browser
from backend import state, db
from shopee import store_status

log = get_logger("backend_worker")

# Filter account usernames allowed for bot execution (Default: auto7313 only)
ALLOWED_USERNAMES_ENV = os.getenv("ALLOWED_USERNAMES", "auto7313")
ALLOWED_USERNAMES = {u.strip() for u in ALLOWED_USERNAMES_ENV.split(",") if u.strip()}
ACTIVE_SESSIONS = {}


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


def _normalize_shopee_regular_hours(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    """Normalize Shopee regular-hours payload into the decision engine shape."""
    return db.normalize_shopee_regular_hours(payload) or {}


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
        log.warning(f"⚠️ [STARTUP WARMUP] Could not fetch database outlets for warmup: {e}")
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

        session_file = SCRIPT_DIR.parent / "data" / f"session_{username}.json"
        browser.set_session_file(session_file)

        saved = browser.load_session()
        if saved and saved.get("shopee_tob_token") and saved.get("shopee_tob_entity_id"):
            if browser.validate_session(saved["shopee_tob_token"], saved["shopee_tob_entity_id"]):
                log.info(f"  ✅ [STARTUP WARMUP] Account '{username}' session valid & ready for Shopee Dashboard.")
                continue

        # If invalid or missing, open browser & perform login
        log.info(f"  🌐 [STARTUP WARMUP] Logging in account '{username}' to Shopee Dashboard via Browser...")
        try:
            session = browser.get_session(
                username=username,
                password=outlet.password,
                phone=outlet.hp,
                target_name=outlet.nama_portal,
                close_browser=False,
                interactive=False,
            )
            if session and session.get("shopee_tob_token"):
                ACTIVE_SESSIONS[username] = session
                log.info(f"  ✅ [STARTUP WARMUP] Account '{username}' successfully logged in & session saved.")
            else:
                log.warning(f"  ⚠️ [STARTUP WARMUP] Account '{username}' login completed, session pending.")
        except Exception as ex:
            log.warning(f"  ⚠️ [STARTUP WARMUP] Account '{username}' warmup exception: {ex}")


from core.notifier import send_discord_success, send_discord_error

def execute_outlet_shopee_action(outlet: MerchantOutlet, action: str) -> bool:
    """
    Executes actual Open/Close action on Shopee Partner API or via Selenium browser login.
    Excludes execution if outlet.username != auto7313.
    """
    # Exclude accounts not in ALLOWED_USERNAMES whitelist
    if ALLOWED_USERNAMES and outlet.username not in ALLOWED_USERNAMES:
        log.info(f"  ⏭️ [SHOPEE EXECUTION] Excluding Store {outlet.store_id} - username '{outlet.username}' != auto7313.")
        return False

    log.info(f"🌐 [SHOPEE EXECUTION] Initiating {action} for Store {outlet.store_id} ({outlet.nama_pendek_outlet})...")

    merchant_name = outlet.nama_portal or outlet.nama_pemilik or "Shopee Merchant"
    outlet_name = outlet.nama_panjang_outlet or outlet.nama_pendek_outlet or outlet.store_id

    # Set session file according to outlet username
    if outlet.username:
        account_session_file = SCRIPT_DIR.parent / "data" / f"session_{outlet.username}.json"
        if account_session_file.exists():
            browser.set_session_file(account_session_file)

    # 1. Fast path: try saved session token
    saved_session = browser.load_session()
    if saved_session and saved_session.get("shopee_tob_token") and saved_session.get("shopee_tob_entity_id"):
        tob_token = saved_session["shopee_tob_token"]
        entity_id = saved_session["shopee_tob_entity_id"]
        if browser.validate_session(tob_token, entity_id):
            log.info(f"  ⚡ Valid session token found. Triggering Direct API for Store {outlet.store_id}...")
            if action == ACTION_OPEN:
                success = browser.open_store_api(tob_token, entity_id, store_id=outlet.store_id)
            else:
                success = browser.pause_store_api(tob_token, entity_id, store_id=outlet.store_id)
            if success:
                log.info(f"  ✅ [DIRECT API SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                send_discord_success(
                    merchant=merchant_name,
                    outlet=outlet_name,
                    action=action,
                    store_id=outlet.store_id
                )
                return True

    # 2. Browser Selenium Fallback (Full Login Sequence)
    log.info(f"  🌐 Launching Selenium Chrome Browser to login & execute {action} for Store {outlet.store_id}...")
    try:
        session = browser.get_session(
            username=outlet.username,
            password=outlet.password,
            phone=outlet.hp,
            target_name=outlet.nama_portal,
        )

        if session:
            driver = session.get("driver")
            tob_token = session.get("shopee_tob_token")
            entity_id = session.get("shopee_tob_entity_id")
            
            # Try API call first with active store_id context
            success = False
            if tob_token and entity_id:
                if action == ACTION_OPEN:
                    success = browser.open_store_api(tob_token, entity_id, store_id=outlet.store_id)
                else:
                    success = browser.pause_store_api(tob_token, entity_id, store_id=outlet.store_id)
                if success:
                    log.info(f"  ✅ [SELENIUM BROWSER API SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                    send_discord_success(
                        merchant=merchant_name,
                        outlet=outlet_name,
                        action=action,
                        store_id=outlet.store_id
                    )
                    return True

            # If API fails or returns need to select store, use UI Button fallback!
            if driver:
                log.info(f"  🖱️ Triggering UI Action fallback for Store {outlet.store_id} ({action})...")
                success = browser.execute_store_action_ui(driver, outlet.store_id, action)
                if success:
                    log.info(f"  ✅ [SELENIUM BROWSER UI SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                    send_discord_success(
                        merchant=merchant_name,
                        outlet=outlet_name,
                        action=action,
                        store_id=outlet.store_id
                    )
                    return True
    except Exception as e:
        log.error(f"  ❌ Selenium browser login error for Store {outlet.store_id}: {e}")

    log.error(f"  ❌ Gagal mengeksekusi {action} untuk Store {outlet.store_id}.")
    send_discord_error(
        platform="Shopee",
        merchant=merchant_name,
        outlet=outlet_name,
        error_type="ACTION_FAILED",
        message=f"Gagal mengeksekusi aksi {action} untuk Outlet '{outlet_name}' (Store ID: {outlet.store_id})."
    )
    return False



def sync_all_stores(execute_actions: bool = True) -> Dict[str, Any]:
    local_tz = ZoneInfo("Asia/Jakarta")
    log.info("🔄 [BACKEND WORKER] Starting store synchronization from PostgreSQL...")

    if hasattr(db, "sync_expired_user_pauses"):
        try:
            db.sync_expired_user_pauses()
        except Exception as e:
            log.warning(f"  ⚠️ Failed to sync expired user pauses: {e}")

    outlets = db.fetch_merchant_outlets_from_db()
    actions_taken = []
    watched_outlets: List[MerchantOutlet] = []

    grouped_outlets: Dict[tuple[str, str], List[MerchantOutlet]] = {}
    for outlet in outlets:
        if ALLOWED_USERNAMES and outlet.username not in ALLOWED_USERNAMES:
            log.debug(
                f"  ⏭️ Excluding store {outlet.store_id} ({outlet.nama_panjang_outlet}) "
                f"- username '{outlet.username}' not in ALLOWED_USERNAMES"
            )
            continue
        key = (outlet.username, outlet.nama_portal or "")
        grouped_outlets.setdefault(key, []).append(outlet)

    for (username, portal_name), merchant_outlets in grouped_outlets.items():
        log.info(
            f"🏬 [MERCHANT GROUP] Processing {len(merchant_outlets)} outlets for Merchant Portal: "
            f"'{portal_name}' (Account: {username})..."
        )

        cached = ACTIVE_SESSIONS.get(username)
        driver = cached.get("driver") if cached else None

        def _is_session_dead(drv) -> bool:
            if not drv:
                return True
            try:
                _ = drv.current_url
                return False
            except Exception:
                return True

        def _recover_session(reason: str) -> None:
            nonlocal cached, driver
            log.warning(
                f"  🔁 [SESSION RECOVERY] Dead session detected ({reason}). "
                f"Re-launching browser for account '{username}'..."
            )
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
                    log.info(
                        f"  ✅ [SESSION RECOVERY] Browser session restored for account '{username}' "
                        f"(Portal: {portal_name})."
                    )
                else:
                    log.warning(
                        f"  ⚠️ [SESSION RECOVERY] Re-launch completed but session token missing for '{username}'."
                    )
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
                        portal_norm = portal_name.lower().strip()
                        current_norm = current_merchant.lower().strip()
                        if portal_norm == current_norm or portal_norm in current_norm or current_norm in portal_norm:
                            already_active = True

                    if already_active:
                        log.info(
                            f"  ✅ [MERCHANT] Browser sudah aktif di portal merchant '{portal_name}' "
                            f"(Current UI: '{current_merchant}'). Skip switch."
                        )
                    else:
                        log.info(
                            f"  🔄 [MERCHANT] Current merchant di browser: '{current_merchant or 'Unknown'}' "
                            f"| Target group: '{portal_name}'. Executing auto_switch_merchant..."
                        )
                        sw_ok = browser.auto_switch_merchant(driver, portal_name)
                        if sw_ok:
                            log.info(f"  ✅ [MERCHANT] Switched successfully to portal merchant '{portal_name}'.")
                            token, entity_id = browser.extract_tokens_from_driver(driver)
                            if cached:
                                if token:
                                    cached["shopee_tob_token"] = token
                                if entity_id:
                                    cached["shopee_tob_entity_id"] = entity_id
                        else:
                            log.warning(
                                f"  ⚠️ [MERCHANT] auto_switch_merchant ke '{portal_name}' gagal. "
                                "Initiating session recovery..."
                            )
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
                log.info(
                    f"  ✅ [BUSINESS HOURS CONFIRMED] Target Store {outlet.store_id} "
                    f"({outlet.nama_panjang_outlet}) TERDETEKSI & TER-LOAD SEMPURNA di menu Business Hours!"
                )
            else:
                log.warning(
                    f"  ⚠️ [BUSINESS HOURS WARNING] Target Store {outlet.store_id} "
                    f"({outlet.nama_panjang_outlet}) BELUM TERDETEKSI SEMPURNA di menu Business Hours!"
                )

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
                                    f"  ⚠️ [REGULAR HOURS STATUS SYNC] Jadwal Shopee Store {outlet.store_id} "
                                    f"berhasil diambil tetapi gagal disimpan ke DB: {persist_err}"
                                )
                            else:
                                log.info(
                                    f"  ✅ [REGULAR HOURS STATUS SYNC] Store {outlet.store_id} jadwal Shopee tersimpan "
                                    f"({sum(bool(value) for value in normalized_hours.values())} hari aktif)."
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
                                f"  ⚠️ [REGULAR HOURS STATUS SYNC] Response jadwal Shopee Store {outlet.store_id} "
                                "tidak valid. Status jadwal kosong terakhir dipertahankan."
                            )
                        elif last_known_schedule_available:
                            log.warning(
                                f"  ⚠️ [REGULAR HOURS STATUS SYNC] Response jadwal Shopee Store {outlet.store_id} "
                                "tidak valid. Tetap memakai jadwal terakhir yang valid."
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
                        f"  ❌ [REGULAR HOURS QUARANTINE] Store {outlet.store_id} dilewati pada cycle ini: "
                        f"{identity_err}. Tidak ada decision/action yang dijalankan memakai jadwal "
                        "yang tidak terpercaya."
                    )
                except Exception as hours_err:
                    if current_schedule_fetch_status == "FETCHED_EMPTY":
                        log.warning(
                            f"  ⚠️ [REGULAR HOURS STATUS SYNC] Gagal menarik jadwal Shopee Store {outlet.store_id}: "
                            f"{hours_err}. Status jadwal kosong terakhir dipertahankan."
                        )
                    elif last_known_schedule_available:
                        log.warning(
                            f"  ⚠️ [REGULAR HOURS STATUS SYNC] Gagal menarik jadwal Shopee Store {outlet.store_id}: "
                            f"{hours_err}. Tetap memakai jadwal terakhir yang valid."
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
                        actual_status = _normalize_live_status(live_info)
                        outlet.status_aktual = actual_status
                        db.update_shopee_actual_status(outlet.store_id, actual_status)
                except store_status.StoreIdentityMismatch as identity_err:
                    live_identity_valid = False
                    log.error(
                        f"  ❌ [LIVE STATE QUARANTINE] Store {outlet.store_id} dilewati pada cycle ini: "
                        f"{identity_err}. Tidak ada decision/action yang dijalankan memakai live state "
                        "yang tidak terpercaya."
                    )
                except Exception as st_err:
                    log.debug(f"  ⚠️ Live Shopee status query skipped for Store {outlet.store_id}: {st_err}")
            else:
                live_identity_valid = True
                log.debug(
                    f"  ⚠️ Live Shopee status query skipped for Store {outlet.store_id}: "
                    "browser session belum siap"
                )

            watched_outlets.append(outlet)

            if not schedule_identity_valid or not live_identity_valid:
                continue

            decision = evaluate_outlet_status(
                outlet,
                current_time=datetime.now(local_tz),
                require_regular_schedule=True,
            )
            log.info(
                f"  🏪 Store {outlet.store_id} ({outlet.nama_pendek_outlet}) -> "
                f"Decision: {decision.action} ({decision.reason})"
            )

            if decision.action in (ACTION_OPEN, ACTION_CLOSE) and execute_actions:
                log.info(f"⚡ [ACTION TRIGGERED] Executing {decision.action} for Store {outlet.store_id}...")
                exec_ok = execute_outlet_shopee_action(outlet, decision.action)

                reason_text = f"{decision.reason} | Shopee Action: {'SUCCESS' if exec_ok else 'FAILED'}"
                actions_taken.append({
                    "store_id": outlet.store_id,
                    "store_name": outlet.nama_pendek_outlet,
                    "action": decision.action,
                    "target_state": decision.target_state,
                    "reason": reason_text,
                })

                state.record_log(
                    store_id=outlet.store_id,
                    store_name=outlet.nama_pendek_outlet,
                    action=decision.action,
                    target_state=decision.target_state,
                    reason=reason_text,
                    success=exec_ok,
                    error_message=None if exec_ok else reason_text,
                    mode="REGULAR",
                )

    state.record_log(
        store_id="SYSTEM",
        store_name="BOT_DAEMON",
        action="SYNC_CYCLE",
        target_state="SYNCED",
        reason=(
            "Evaluasi bot selesai dari PostgreSQL: "
            f"{len(actions_taken)} aksi dijalankan (Filtered: username == auto7313)"
        ),
    )

    return {
        "success": True,
        "total_stores_processed": len(outlets),
        "actions_taken": actions_taken,
        "message": (
            f"Successfully processed {len(outlets)} store(s) from PostgreSQL "
            f"for allowed usernames {ALLOWED_USERNAMES}."
        ),
    }
