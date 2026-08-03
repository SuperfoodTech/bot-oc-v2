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

from core.logger import get_logger
from core.sheets import fetch_merchant_outlets, MerchantOutlet
from core.decision import evaluate_outlet_status, ACTION_OPEN, ACTION_CLOSE, ACTION_NO_CHANGE
from core import browser
from backend import db

log = get_logger("backend_worker")

# Filter account usernames allowed for bot execution (Default: auto7313 only)
ALLOWED_USERNAMES_ENV = os.getenv("ALLOWED_USERNAMES", "auto7313")
ALLOWED_USERNAMES = {u.strip() for u in ALLOWED_USERNAMES_ENV.split(",") if u.strip()}


def warmup_all_account_sessions():
    """
    On service startup, iterates over registered merchant accounts and ensures
    each account is logged in to the Shopee Partner Dashboard, saving active sessions.
    Only processes accounts matching ALLOWED_USERNAMES (e.g. auto7313).
    """
    log.info(f"🚀 [STARTUP WARMUP] Initializing & verifying Shopee Dashboard sessions for whitelisted accounts {ALLOWED_USERNAMES}...")
    try:
        outlets = fetch_merchant_outlets()
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
                headless=True
            )
            if session and session.get("shopee_tob_token"):
                log.info(f"  ✅ [STARTUP WARMUP] Account '{username}' successfully logged in & session saved.")
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

    log.info(f"🌐 [SHOPEE EXECUTION] Initiating {action} for Store {outlet.store_id} ({outlet.nama_pendek_outlet})...")

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
                success = browser.open_store_api(tob_token, entity_id)
            else:
                success = browser.pause_store_api(tob_token, entity_id)
            if success:
                log.info(f"  ✅ [DIRECT API SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                return True

    # 2. Browser Selenium Fallback (Full Login Sequence)
    log.info(f"  🌐 Launching Selenium Chrome Browser to login & execute {action} for Store {outlet.store_id}...")
    try:
        session = browser.get_session(
            username=outlet.username,
            password=outlet.password,
            phone=outlet.hp,
            target_name=outlet.nama_portal,
            headless=True
        )

        if session and session.get("shopee_tob_token") and session.get("shopee_tob_entity_id"):
            tob_token = session["shopee_tob_token"]
            entity_id = session["shopee_tob_entity_id"]
            if action == ACTION_OPEN:
                success = browser.open_store_api(tob_token, entity_id)
            else:
                success = browser.pause_store_api(tob_token, entity_id)
            if success:
                log.info(f"  ✅ [SELENIUM BROWSER SUCCESS] {action} executed successfully for Store {outlet.store_id}.")
                return True
    except Exception as e:
        log.error(f"  ❌ Selenium browser login error for Store {outlet.store_id}: {e}")

    log.error(f"  ❌ Gagal mengeksekusi {action} untuk Store {outlet.store_id}.")
    return False


def sync_all_stores(execute_actions: bool = True) -> Dict[str, Any]:
    log.info("🔄 [BACKEND WORKER] Starting store synchronization...")

    # Fetch merchant outlets from control source (Google Sheets)
    outlets = fetch_merchant_outlets()
    actions_taken = []

    for outlet in outlets:
        # Exclude stores where username != auto7313 (if whitelist active)
        if ALLOWED_USERNAMES and outlet.username not in ALLOWED_USERNAMES:
            log.debug(f"  ⏭️ Excluding store {outlet.store_id} ({outlet.nama_pendek_outlet}) - username '{outlet.username}' != auto7313")
            continue

        # 1. Update / seed store in DB
        db.save_or_update_store(
            store_id=outlet.store_id,
            store_name=outlet.nama_pendek_outlet,
            merchant_name=outlet.nama_portal,
            account_username=outlet.username,
            nama_pemilik=outlet.nama_pemilik,
            paket=outlet.paket,
            tanggal_mulai_layanan=outlet.tanggal_mulai_layanan,
            tanggal_berakhir_layanan=outlet.tanggal_berakhir_layanan,
            vercel_link=outlet.vercel_link,
            vercel_password=outlet.vercel_password,
            vercel_status=outlet.status_utama.upper(),
            shopee_status=outlet.status_aktual.upper(),
            subscription_status=outlet.status_langganan,
            is_suspended=(outlet.penangguhan.lower() == "ya"),
            alasan_penangguhan=outlet.alasan_penangguhan
        )

        # 2. Evaluate decision engine rules
        decision = evaluate_outlet_status(outlet)
        log.info(f"  🏪 Store {outlet.store_id} ({outlet.nama_pendek_outlet}) -> Decision: {decision.action} ({decision.reason})")

        # 3. If action needed and execute_actions is True
        if decision.action in (ACTION_OPEN, ACTION_CLOSE) and execute_actions:
            log.info(f"⚡ [ACTION TRIGGERED] Executing {decision.action} for Store {outlet.store_id}...")
            exec_ok = execute_outlet_shopee_action(outlet, decision.action)

            reason_text = f"{decision.reason} | Shopee Action: {'SUCCESS' if exec_ok else 'FAILED'}"
            actions_taken.append({
                "store_id": outlet.store_id,
                "store_name": outlet.nama_pendek_outlet,
                "action": decision.action,
                "target_state": decision.target_state,
                "reason": reason_text
            })

            # Record in SQLite audit log
            db.record_log(
                store_id=outlet.store_id,
                store_name=outlet.nama_pendek_outlet,
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
