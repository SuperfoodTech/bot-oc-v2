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

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from logger import get_logger
from sheets import MerchantOutlet
from decision import evaluate_outlet_status, ACTION_OPEN, ACTION_CLOSE, ACTION_NO_CHANGE
import browser
import db
from shopee import store_status

log = get_logger("backend_worker")

# Filter account usernames allowed for bot execution (Default: auto7313 only)
ALLOWED_USERNAMES_ENV = os.getenv("ALLOWED_USERNAMES", "auto7313")
ALLOWED_USERNAMES = {u.strip() for u in ALLOWED_USERNAMES_ENV.split(",") if u.strip()}
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() in {"1", "true", "yes", "on"}
# One long-lived browser per Shopee bot account. Merchant switching happens in
# this browser; the bot does not close/reopen Chrome for every outlet action.
ACTIVE_SESSIONS = {}


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

        # Always launch/verify persistent browser session for the account
        log.info(f"  🌐 [STARTUP WARMUP] Initializing active browser session for account '{username}' (Target Portal: {outlet.nama_portal})...")
        try:
            session = browser.get_session(
                username=username,
                password=outlet.password,
                phone=outlet.hp,
                target_name=outlet.nama_portal,
                headless=HEADLESS,
                close_browser=False,
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
        headless=HEADLESS,
        close_browser=False,
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
                success = store_status.pause_store_action(driver, outlet.store_id, merchant_id=m_id)
            if success:
                log.info(f"  ✅ [IN-BROWSER XHR SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                return True

    log.error(f"  ❌ Gagal mengeksekusi {action} untuk Store {outlet.store_id}.")
    return False


def sync_all_stores(execute_actions: bool = True) -> Dict[str, Any]:
    log.info("🔄 [BACKEND WORKER] Starting store synchronization...")

    # Runtime source of truth: PostgreSQL. Spreadsheet is import-only.
    outlets = db.fetch_merchant_outlets_from_db()
    actions_taken = []

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

    # Process each merchant portal group
    for (username, portal_name), merchant_outlets in grouped_outlets.items():
        log.info(f"🏬 [MERCHANT GROUP] Processing {len(merchant_outlets)} outlets for Merchant Portal: '{portal_name}' (Account: {username})...")

        # 1. Ensure browser session is active and switched to portal_name
        cached = ACTIVE_SESSIONS.get(username)
        driver = cached.get("driver") if cached else None

        if driver:
            try:
                curr_url = str(driver.current_url or "").lower()
                if "partner.shopee.co.id" in curr_url:
                    log.info(f"  ✅ [MERCHANT] Browser sudah aktif di portal merchant '{portal_name}'. Skip switch.")
                else:
                    browser.auto_switch_merchant(driver, portal_name)
            except Exception as sw_err:
                log.warning(f"  ⚠️ Merchant context switch warning: {sw_err}")
        else:
            # Launch/get browser session targeting portal_name
            try:
                first_outlet = merchant_outlets[0]
                session = browser.get_session(
                    username=username,
                    password=first_outlet.password,
                    phone=first_outlet.hp,
                    target_name=portal_name,
                    headless=HEADLESS,
                    close_browser=False,
                )
                if session and session.get("shopee_tob_token"):
                    ACTIVE_SESSIONS[username] = session
                    cached = session
                    driver = session.get("driver")
            except Exception as sess_err:
                log.warning(f"  ⚠️ Browser session init error for merchant '{portal_name}': {sess_err}")

        tob_token = cached.get("shopee_tob_token") if cached else None
        entity_id = cached.get("shopee_tob_entity_id") if cached else None
        extra_cookies = cached.get("extra_cookies") if cached else None

        # 2. Process all outlets in this merchant group
        for outlet in merchant_outlets:
            if outlet.username:
                browser.set_session_file(PROJECT_ROOT / "src" / "data" / f"session_{outlet.username}.json")

            log.info(f"📌 Memasuki tab Business Hours untuk Store {outlet.store_id} ({outlet.nama_panjang_outlet})...")

            # Check and verify if the Business Hours menu for target store_id is detected
            is_detected = store_status.ensure_business_hours_page(driver, store_id=outlet.store_id)
            if is_detected:
                log.info(f"  ✅ [BUSINESS HOURS CONFIRMED] Target Store {outlet.store_id} ({outlet.nama_panjang_outlet}) TERDETEKSI & TER-LOAD SEMPURNA di menu Business Hours!")
            else:
                log.warning(f"  ⚠️ [BUSINESS HOURS WARNING] Target Store {outlet.store_id} ({outlet.nama_panjang_outlet}) BELUM TERDETEKSI SEMPURNA di menu Business Hours!")

            # Single Essential Endpoint: Fetch Realtime Live Store Status via /api/seller/store
            try:
                live_info = store_status.get_actual_store_status(driver, store_id=outlet.store_id)
                if live_info and live_info.get("status_str") in ("OPEN", "CLOSED"):
                    actual_st = "ON" if live_info["status_str"] == "OPEN" else "PAUSE"
                    outlet.status_aktual = actual_st
                    db.update_shopee_actual_status(outlet.store_id, actual_st)
            except Exception as st_err:
                log.debug(f"  ⚠️ Live Shopee status query skipped for Store {outlet.store_id}: {st_err}")

            # Evaluate decision engine rules from database-backed state.
            decision = evaluate_outlet_status(outlet)
            shopee_before = (outlet.status_aktual or "UNKNOWN").upper()
            vercel_status = (outlet.status_utama or "OFF").upper()

            log.info(
                f"  🔍 [PRE-CHECK] Store {outlet.store_id} ({outlet.nama_panjang_outlet}) | "
                f"Shopee Status Sebelum: {shopee_before} | Vercel Toggle: {vercel_status} | "
                f"Decision: {decision.action} ({decision.reason})"
            )

            # 3. If action needed and execute_actions is True
            if decision.action in (ACTION_OPEN, ACTION_CLOSE) and execute_actions:
                log.info(f"⚡ [ACTION TRIGGERED] Executing {decision.action} for Store {outlet.store_id} (Target: {decision.target_state})...")
                exec_ok = execute_outlet_shopee_action(outlet, decision.action)

                if exec_ok:
                    log.info(f"  🔍 [POST-EXECUTION VERIFICATION] Memverifikasi ulang status live Shopee setelah {decision.action} untuk Store {outlet.store_id}...")
                    time.sleep(1.5)
                    post_info = store_status.get_actual_store_status(driver, store_id=outlet.store_id)
                    if post_info and post_info.get("status_str") in ("OPEN", "CLOSED"):
                        verified_st = "ON" if post_info["status_str"] == "OPEN" else "PAUSE"
                        log.info(f"  ✅ [POST-EXECUTION VERIFIED] Status Live Shopee Pasca-{decision.action}: '{verified_st}' (Expected: '{'ON' if decision.target_state == 'OPEN' else 'PAUSE'}').")
                        new_actual_status = verified_st
                    else:
                        new_actual_status = "ON" if decision.target_state == "OPEN" else "PAUSE"

                    try:
                        db.update_shopee_actual_status(outlet.store_id, new_actual_status)
                        log.info(f"  ✅ [DB STATUS SYNC] Status shopee_actual_status Store {outlet.store_id} berhasil diupdate ke '{new_actual_status}' di DB.")
                    except Exception as sync_err:
                        log.warning(f"  ⚠️ Gagal mengupdate DB shopee_actual_status: {sync_err}")

                reason_text = f"{decision.reason} | Shopee Action: {'SUCCESS' if exec_ok else 'FAILED'}"
                actions_taken.append({
                    "store_id": outlet.store_id,
                    "store_name": outlet.nama_panjang_outlet,
                    "action": decision.action,
                    "target_state": decision.target_state,
                    "reason": reason_text
                })

                # Record in the runtime audit log
                db.record_log(
                    store_id=outlet.store_id,
                    store_name=outlet.nama_panjang_outlet,
                    action=decision.action,
                    target_state=decision.target_state,
                    reason=reason_text
                )

    # Record overall cycle evaluation log for process tracking
    db.record_log(
        store_id="SYSTEM",
        store_name="BOT_DAEMON",
        action="SYNC_CYCLE",
        target_state="SYNCED",
        reason=f"Evaluasi bot selesai untuk {len(actions_taken)} aksi dijalankan (Filtered: username == auto7313)"
    )

    return {
        "success": True,
        "total_stores_processed": len(outlets),
        "actions_taken": actions_taken,
        "message": f"Successfully processed stores for allowed usernames {ALLOWED_USERNAMES}."
    }
