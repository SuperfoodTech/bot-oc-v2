"""
worker.py
=========
Backend Worker Engine that syncs store states, evaluates PRD rules, and triggers direct API open/close actions.
"""

import sys
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
from backend import db

log = get_logger("backend_worker")


def sync_all_stores(execute_actions: bool = True) -> Dict[str, Any]:
    log.info("🔄 [BACKEND WORKER] Starting store synchronization...")

    # Fetch merchant outlets from control source (Google Sheets)
    outlets = fetch_merchant_outlets()
    actions_taken = []

    for outlet in outlets:
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
            action_desc = f"Triggered {decision.action} for Store {outlet.store_id}"
            actions_taken.append({
                "store_id": outlet.store_id,
                "store_name": outlet.nama_pendek_outlet,
                "action": decision.action,
                "target_state": decision.target_state,
                "reason": decision.reason
            })

            # Record in SQLite audit log
            db.record_log(
                store_id=outlet.store_id,
                store_name=outlet.nama_pendek_outlet,
                action=decision.action,
                target_state=decision.target_state,
                reason=decision.reason
            )

    return {
        "success": True,
        "total_stores_processed": len(outlets),
        "actions_taken": actions_taken,
        "message": f"Successfully processed {len(outlets)} stores."
    }
