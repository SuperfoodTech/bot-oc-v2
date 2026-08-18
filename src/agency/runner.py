"""
src/agency/runner.py
====================
Pure patrol functions untuk Agency Churn Bot.

Digunakan oleh:
  - main-agency/src/daemon.py  → patrol loop di container fm-agency
  - main-agency/src/daemon.py  → manual force close via internal API

TIDAK ada threading di sini. Threading/lifecycle dikelola oleh daemon.py.
State patrol (driver, running flag) diekspos sebagai module-level vars
agar daemon.py bisa mengisinya dan agency_api.py bisa membacanya.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from agency.sheets import get_agency_shopeefood_outlets
from agency.decision import evaluate_agency_outlet_status, ACTION_CLOSE, ACTION_STOP
from agency import browser as agency_browser
from backend import db

log = logging.getLogger(__name__)

# ── Module-level patrol state (diisi oleh daemon.py) ──────────────────────────
# Lock melindungi akses concurrent: patrol loop vs. manual trigger dari API server
_patrol_lock = threading.Lock()
_patrol_driver = None       # Selenium WebDriver instance — None jika belum init
_patrol_running = False     # True saat daemon berjalan


# ── Grouping helper ────────────────────────────────────────────────────────────

def _group_outlets_by_merchant(outlets: List[Dict]) -> List[Tuple[str, List[Dict]]]:
    """
    Mengelompokkan outlet churn berdasarkan merchant_name.
    Urutan: merchant dengan outlet TERBANYAK → TERKECIL.
    """
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for outlet in outlets:
        merchant = (
            outlet.get("merchant_name", "").strip()
            or outlet.get("brand", "").strip()
            or "Unknown"
        )
        groups[merchant].append(outlet)

    return sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _upsert_outlet_status(
    store_id: str,
    merchant_name: str,
    brand: str,
    shopee_status: str,
    last_action: str = "",
) -> None:
    """
    Upsert hasil inspeksi satu outlet ke tabel agency_outlet_status.
    Penting: Jika shopee_status baru adalah 'NOT_FOUND', 'UNKNOWN', atau 'ERROR',
    tetapi database sudah menyimpan status valid ('OPEN' atau 'CLOSED') dari cycle
    sebelumnya, status valid tersebut TIDAK akan ditimpa (dipertahankan).
    """
    try:
        with db.get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO agency_outlet_status
                    (store_id, merchant_name, brand, shopee_status, last_checked, last_action)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (store_id) DO UPDATE SET
                    merchant_name = EXCLUDED.merchant_name,
                    brand         = EXCLUDED.brand,
                    shopee_status = CASE
                        WHEN EXCLUDED.shopee_status IN ('NOT_FOUND', 'UNKNOWN', 'ERROR')
                             AND agency_outlet_status.shopee_status IN ('OPEN', 'CLOSED')
                        THEN agency_outlet_status.shopee_status
                        ELSE EXCLUDED.shopee_status
                    END,
                    last_checked  = CASE
                        WHEN EXCLUDED.shopee_status IN ('NOT_FOUND', 'UNKNOWN', 'ERROR')
                             AND agency_outlet_status.shopee_status IN ('OPEN', 'CLOSED')
                        THEN agency_outlet_status.last_checked
                        ELSE EXCLUDED.last_checked
                    END,
                    last_action   = EXCLUDED.last_action
                """,
                (store_id, merchant_name, brand, shopee_status,
                 datetime.now(timezone.utc), last_action),
            )
    except Exception as e:
        log.warning("[AGENCY-RUNNER] DB upsert failed for store %s: %s", store_id, e)


def _force_update_outlet_status(
    store_id: str,
    merchant_name: str,
    brand: str,
    shopee_status: str,
    last_action: str = "",
) -> None:
    """Paksa update status outlet (digunakan untuk merchant yang memang terkonfirmasi NOT_FOUND)."""
    try:
        with db.get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO agency_outlet_status
                    (store_id, merchant_name, brand, shopee_status, last_checked, last_action)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (store_id) DO UPDATE SET
                    merchant_name = EXCLUDED.merchant_name,
                    brand         = EXCLUDED.brand,
                    shopee_status = EXCLUDED.shopee_status,
                    last_checked  = EXCLUDED.last_checked,
                    last_action   = EXCLUDED.last_action
                """,
                (store_id, merchant_name, brand, shopee_status,
                 datetime.now(timezone.utc), last_action),
            )
    except Exception as e:
        log.warning("[AGENCY-RUNNER] DB force update failed for store %s: %s", store_id, e)


# ── Core patrol cycle ──────────────────────────────────────────────────────────

def _run_patrol_cycle(driver, auto_fc_enabled: bool = False) -> Dict:
    """
    Satu siklus patroli penuh melintasi semua outlet churn.

    Urutan:
      1. Ambil daftar outlet dari Google Sheet.
      2. Group per merchant, urut terbanyak → terkecil.
      3. Untuk setiap group: switch merchant → inspect setiap outlet.
      4. Jika auto_fc_enabled=True dan outlet OPEN → eksekusi force close.
      5. Simpan hasil ke DB.

    Returns: summary dict { processed, closed, stopped, errors }
    """
    churn_outlets, _ = get_agency_shopeefood_outlets()
    if not churn_outlets:
        log.info("[AGENCY-RUNNER] Tidak ada outlet churn di sheet.")
        return {"processed": 0, "closed": 0, "stopped": 0, "errors": 0}

    grouped = _group_outlets_by_merchant(churn_outlets)
    log.info(
        "[AGENCY-RUNNER] Patrol cycle: %d outlet, %d merchant. Auto FC: %s",
        len(churn_outlets), len(grouped),
        "ON" if auto_fc_enabled else "OFF",
    )

    processed = closed = stopped = errors = 0

    for merchant_name, outlets in grouped:
        log.info(
            "[AGENCY-RUNNER] --- %s (%d outlet) ---",
            merchant_name, len(outlets)
        )

        try:
            switched = agency_browser.switch_to_merchant(driver, merchant_name)
            if not switched:
                raise Exception("Switch returned False")
        except agency_browser.MerchantNotFoundError as mnf:
            log.warning(
                "[AGENCY-RUNNER] Merchant '%s' terkonfirmasi TIDAK TERDAFTAR di akun ini. Updating status ke NOT_FOUND...",
                merchant_name
            )
            for outlet in outlets:
                st_id = outlet.get("store_id", "")
                br = outlet.get("brand", "")
                if st_id:
                    _force_update_outlet_status(st_id, merchant_name, br, "NOT_FOUND", "MERCHANT_NOT_FOUND")
            errors += len(outlets)
            continue
        except Exception as sw_err:
            log.warning(
                "[AGENCY-RUNNER] Gangguan transient/driver saat switch ke merchant '%s': %s. Mempertahankan status valid sebelumnya.",
                merchant_name, sw_err
            )
            for outlet in outlets:
                st_id = outlet.get("store_id", "")
                br = outlet.get("brand", "")
                if st_id:
                    _upsert_outlet_status(st_id, merchant_name, br, "UNKNOWN", "TRANSIENT_DRIVER_ERROR")
            errors += len(outlets)
            continue

        for outlet in outlets:
            store_id = outlet.get("store_id", "")
            brand = outlet.get("brand", "")
            if not store_id:
                continue

            try:
                shopee_status = agency_browser.get_outlet_shopee_status(driver, store_id)
                decision = evaluate_agency_outlet_status(shopee_status)
                last_action = "INSPECT"

                if auto_fc_enabled and decision.action == ACTION_CLOSE:
                    success = agency_browser.execute_force_close(driver, store_id)
                    if success:
                        last_action = "FORCE_CLOSE"
                        shopee_status = "CLOSED"
                        closed += 1
                        log.info("[FORCE CLOSE] %s (Store: %s): closed.", brand, store_id)
                    else:
                        last_action = "FORCE_CLOSE_FAILED"
                        errors += 1
                        log.warning("[FORCE CLOSE FAILED] %s (Store: %s).", brand, store_id)
                elif decision.action == ACTION_STOP:
                    last_action = "INSPECT_ALREADY_CLOSED"
                    stopped += 1
                    log.info("[STOP] %s (Store: %s): already closed.", brand, store_id)
                else:
                    log.info(
                        "[INSPECT] %s (Store: %s): status=%s (FC off).",
                        brand, store_id, shopee_status
                    )

                _upsert_outlet_status(store_id, merchant_name, brand, shopee_status, last_action)
                processed += 1

            except Exception as e:
                log.error("[AGENCY-RUNNER] Error store %s: %s", store_id, e)
                _upsert_outlet_status(store_id, merchant_name, brand, "UNKNOWN", "ERROR")
                errors += 1

    log.info(
        "[AGENCY-RUNNER] Cycle selesai: processed=%d closed=%d stopped=%d errors=%d",
        processed, closed, stopped, errors,
    )
    return {"processed": processed, "closed": closed, "stopped": stopped, "errors": errors}


# ── Manual force close (dipanggil via agency_api /force-close) ─────────────────

def run_agency_force_close_patrol(target_store_id: Optional[str] = None) -> Dict:
    """
    Eksekusi force close untuk satu store ID.

    Menggunakan driver patrol aktif jika tersedia (_patrol_driver).
    Jika tidak, membuat sesi browser sementara.

    Dipanggil oleh:
      - main-agency/src/daemon.py melalui agency_api callback (manual button)
    """
    churn_outlets, _ = get_agency_shopeefood_outlets()
    if target_store_id:
        churn_outlets = [
            o for o in churn_outlets if str(o.get("store_id")) == str(target_store_id)
        ]

    if not churn_outlets:
        return {
            "success": True,
            "message": "Tidak ada outlet churn untuk store_id tersebut.",
            "processed": 0, "closed": 0, "stopped": 0,
        }

    with _patrol_lock:
        driver = _patrol_driver

    own_driver = False
    if driver is None:
        log.info("[AGENCY-RUNNER] Patrol driver tidak aktif — buka sesi sementara.")
        session = agency_browser.get_agency_session(close_browser=False)
        if not session or "driver" not in session:
            return {
                "success": False,
                "error": "Gagal inisialisasi browser untuk force close.",
                "processed": 0, "closed": 0, "stopped": 0,
            }
        driver = session["driver"]
        own_driver = True

    closed_count = stopped_count = 0
    results = []

    try:
        grouped = _group_outlets_by_merchant(churn_outlets)
        for merchant_name, outlets in grouped:
            switched = agency_browser.switch_to_merchant(driver, merchant_name)
            if not switched:
                for outlet in outlets:
                    results.append({
                        "store_id": outlet.get("store_id"),
                        "brand": outlet.get("brand"),
                        "action": "ERROR",
                        "reason": "Gagal switch merchant",
                    })
                continue

            for outlet in outlets:
                store_id = outlet.get("store_id", "")
                brand = outlet.get("brand", "")

                shopee_status = agency_browser.get_outlet_shopee_status(driver, store_id)
                decision = evaluate_agency_outlet_status(shopee_status)

                if decision.action == ACTION_CLOSE:
                    success = agency_browser.execute_force_close(driver, store_id)
                    last_action = "FORCE_CLOSE" if success else "FORCE_CLOSE_FAILED"
                    if success:
                        shopee_status = "CLOSED"
                        closed_count += 1
                else:
                    last_action = "STOP_ALREADY_CLOSED"
                    stopped_count += 1

                _upsert_outlet_status(store_id, merchant_name, brand, shopee_status, last_action)
                results.append({
                    "store_id": store_id,
                    "brand": brand,
                    "merchant_name": merchant_name,
                    "action": decision.action,
                    "reason": decision.reason,
                    "shopee_status": shopee_status,
                })
    finally:
        if own_driver:
            agency_browser.cleanup_agency_driver(driver)

    return {
        "success": True,
        "processed": len(results),
        "closed": closed_count,
        "stopped": stopped_count,
        "details": results,
    }


# ── Compatibility stubs (dipanggil oleh fm-backend/main.py) ───────────────────
# Fungsi-fungsi ini ada agar fm-backend tidak error import.
# Patrol lifecycle sekarang dikelola oleh daemon.py di container fm-agency,
# bukan oleh runner. fm-backend menggunakan HTTP call ke fm-agency:8082.

def get_patrol_status() -> Dict:
    """Stub — status sebenarnya diambil dari fm-agency:8082/status oleh main.py."""
    with _patrol_lock:
        return {
            "running": _patrol_running,
            "has_driver": _patrol_driver is not None,
        }


def is_patrol_running() -> bool:
    with _patrol_lock:
        return _patrol_running
