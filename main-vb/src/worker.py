"""Brand-level patrol worker for Virtual Brand.

The patrol unit is a brand. Shopee operations remain per Store ID, grouped by
portal so the copied browser merchant-switch flow is reused unchanged.
"""

from __future__ import annotations

import sys
import time
import fcntl
from pathlib import Path

VB_SRC = Path(__file__).resolve().parent
if str(VB_SRC) not in sys.path:
    sys.path.insert(0, str(VB_SRC))

from config import MAX_RETRIES, PASSWORD, SESSION_FILE, USERNAME, validate_runtime_paths
from core import browser
from core.logger import get_logger
from shopee import store_status

import db

log = get_logger("vb_worker")
ACTIVE_SESSION = None
PATROL_LOCK_PATH = VB_SRC.parent / "patrol.lock"


def configure_browser() -> None:
    """Inject VB session path without changing the copied browser.py."""
    validate_runtime_paths()
    browser.set_session_file(SESSION_FILE)


def _load_session():
    global ACTIVE_SESSION
    configure_browser()
    if ACTIVE_SESSION and ACTIVE_SESSION.get("driver"):
        return ACTIVE_SESSION
    ACTIVE_SESSION = browser.get_session(
        username=USERNAME,
        password=PASSWORD,
        phone=None,
        target_name=None,
        close_browser=False,
        interactive=False,
    )
    return ACTIVE_SESSION


def _driver_alive(driver) -> bool:
    run_id = None
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def _ensure_portal(session: dict, portal_name: str) -> bool:
    driver = session.get("driver")
    if not driver or not _driver_alive(driver):
        return False
    current = ""
    try:
        current = driver.execute_script("return (document.querySelector('.merchantName')?.innerText || '').trim();")
    except Exception:
        pass
    current_norm = current.casefold().strip()
    target_norm = (portal_name or "").casefold().strip()
    if target_norm and (target_norm == current_norm or target_norm in current_norm or current_norm in target_norm):
        return True
    return bool(browser.auto_switch_merchant(driver, portal_name))


def _read_actual(driver, store_id: str) -> str:
    data = store_status.get_actual_store_status(driver, store_id=store_id)
    if not data:
        return "UNKNOWN"
    return "ON" if data.get("status_str") == "OPEN" else "PAUSE"


def _execute(driver, store: dict, target: str) -> bool:
    if target == "ON":
        return bool(store_status.open_store_action(driver, store["store_id"], merchant_id=store.get("merchant_id_external") or ""))
    return bool(store_status.pause_store_action(driver, store["store_id"], merchant_id=store.get("merchant_id_external") or ""))


def _process_store(session: dict, store: dict, target: str, brand_name: str) -> tuple[bool, str]:
    driver = session.get("driver")
    action = "OPEN" if target == "ON" else "PAUSE"
    total_attempts = MAX_RETRIES + 1
    if not driver:
        log.error("❌ [VB ERROR] Brand=%s | Merchant=%s | Store ID=%s | Action=%s | Browser driver tidak tersedia", brand_name, store.get("portal_name", "-"), store["store_id"], action)
        return False, "Browser driver tidak tersedia"
    if not _ensure_portal(session, store["portal_name"]):
        log.error("❌ [VB ERROR] Brand=%s | Merchant=%s | Store ID=%s | Action=%s | Gagal switch merchant", brand_name, store.get("portal_name", "-"), store["store_id"], action)
        return False, f"Gagal switch merchant: {store['portal_name']}"
    last_error = ""
    for attempt in range(total_attempts):
        try:
            actual = _read_actual(driver, store["store_id"])
            log.info("  🔎 [VB CHECK] Brand=%s | Merchant=%s | Store ID=%s | Actual=%s | Target=%s | Action=%s | Attempt=%s/%s", brand_name, store.get("portal_name", "-"), store["store_id"], actual, target, action, attempt + 1, total_attempts)
            if actual == target:
                log.info("  ⏭️ [VB SKIP] Brand=%s | Store ID=%s | Action=%s | Status sudah sesuai", brand_name, store["store_id"], action)
                return True, "Status sudah sesuai"
            if not _execute(driver, store, target):
                last_error = "Aksi Shopee mengembalikan gagal"
            else:
                log.info("  ⚡ [VB ACTION] Brand=%s | Merchant=%s | Store ID=%s | Action=%s | Target=%s", brand_name, store.get("portal_name", "-"), store["store_id"], action, target)
                time.sleep(1.5)
                verified = _read_actual(driver, store["store_id"])
                if verified == target:
                    log.info("  ✅ [VB SUCCESS] Brand=%s | Store ID=%s | Action=%s | Verified=%s", brand_name, store["store_id"], action, verified)
                    return True, "Aksi berhasil dan terverifikasi"
                last_error = f"Verifikasi status {verified}, target {target}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < MAX_RETRIES:
            log.warning("  🔁 [VB RETRY] Brand=%s | Store ID=%s | Action=%s | Retry=%s/%s | Error=%s", brand_name, store["store_id"], action, attempt + 1, MAX_RETRIES, last_error)
    log.error("❌ [VB ERROR] Brand=%s | Merchant=%s | Store ID=%s | Action=%s | Attempts=%s | Error=%s", brand_name, store.get("portal_name", "-"), store["store_id"], action, total_attempts, last_error)
    return False, last_error


def patrol_once(execute_actions: bool = True) -> dict:
    """Process one complete patrol round, in stable brand order."""
    run_id = None
    lock_handle = PATROL_LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_handle.close()
        raise RuntimeError("Putaran patroli VB lain masih berjalan") from exc

    try:
        session = _load_session()
        if not session or not session.get("driver"):
            raise RuntimeError("Session VB tidak aktif")

        with db.connection() as conn:
            with conn.transaction():
                run_id = db.create_patrol_run(conn)
                brands = db.list_brands(conn)

        log.info("🚀 [VB PATROL START] Run=%s | Brands=%s | Interval=30s | Max retry=%s", run_id, len(brands), MAX_RETRIES)

        processed = 0
        outlets_processed = 0
        failures = []
        for brand_index, brand in enumerate(brands, start=1):
            with db.connection() as conn:
                with conn.transaction():
                    applied = db.apply_pending_status(conn, brand["id"])
                    if applied:
                        brand["applied_status"] = applied["applied_status"]
                    stores = db.get_brand_outlets(conn, brand["id"])

            target = "ON" if brand["applied_status"] == "ON" else "PAUSE"
            brand_failures = []
            brand_changed = 0
            merchants = sorted({store.get("portal_name") or "Unknown Merchant" for store in stores})
            log.info("🏷️ [VB BRAND %s/%s] Brand=%s | Target=%s | Merchants=%s | Outlets=%s", brand_index, len(brands), brand["name"], target, ", ".join(merchants), len(stores))
            for store in stores:
                outlets_processed += 1
                if not execute_actions:
                    continue
                ok, reason = _process_store(session, store, target, brand["name"])
                with db.connection() as conn:
                    with conn.transaction():
                        before = store.get("shopee_actual_status") or "UNKNOWN"
                        action = "OPEN_STORE" if target == "ON" else "PAUSE_STORE"
                        if ok and before != target:
                            brand_changed += 1
                            conn.execute(
                                """INSERT INTO automation_logs
                                   (outlet_id, mode, vb_brand_id, vb_patrol_run_id,
                                    suspension_status, subscription_status,
                                    vercel_status_before, shopee_status_before,
                                    target_status, action, success, reason)
                                   VALUES (%s, 'VB', %s, %s, 'ACTIVE', 'ACTIVE',
                                           'ON', %s, %s, %s, true, %s)""",
                                (store["outlet_id"], brand["id"], run_id, before, target, action, reason),
                            )
                        if not ok:
                            conn.execute(
                                """INSERT INTO automation_errors
                                   (mode, patrol_run_id, vb_brand_id, outlet_id, store_id,
                                    merchant_name, action, attempt_count, error_type, error_message)
                                   VALUES ('VB', %s, %s, %s, %s, %s, %s, 2, 'SHOPEE_ACTION_FAILED', %s)""",
                                (run_id, brand["id"], store["outlet_id"], store["store_id"],
                                 store.get("portal_name"), action, reason),
                            )
                        if ok:
                            conn.execute(
                                "UPDATE outlet_states SET shopee_actual_status=%s, last_checked_at=now(), last_action_at=now(), updated_at=now() WHERE outlet_id=%s",
                                (target, store["outlet_id"]),
                            )
                if not ok:
                    brand_failures.append({"store_id": store["store_id"], "reason": reason})
            with db.connection() as conn:
                with conn.transaction():
                    db.mark_patrolled(conn, brand["id"])
                    conn.execute(
                        """INSERT INTO vb_brand_runtime_status
                           (vb_brand_id, last_patrol_run_id, last_patrolled_at,
                            outlets_processed, outlets_changed, error_count,
                            last_error_at, last_error_message, updated_at)
                           VALUES (%s, %s, now(), %s, %s, %s,
                                   CASE WHEN %s > 0 THEN now() ELSE NULL END, %s, now())
                           ON CONFLICT (vb_brand_id) DO UPDATE SET
                             last_patrol_run_id=EXCLUDED.last_patrol_run_id,
                             last_patrolled_at=EXCLUDED.last_patrolled_at,
                             outlets_processed=EXCLUDED.outlets_processed,
                             outlets_changed=EXCLUDED.outlets_changed,
                             error_count=EXCLUDED.error_count,
                             last_error_at=EXCLUDED.last_error_at,
                             last_error_message=EXCLUDED.last_error_message,
                             updated_at=now()""",
                        (brand["id"], run_id, len(stores), brand_changed,
                         len(brand_failures), len(brand_failures),
                         brand_failures[-1]["reason"] if brand_failures else None),
                    )
                    if brand_failures:
                        failures.append({"brand": brand["name"], "stores": brand_failures})
            processed += 1
            log.info("📌 [VB BRAND DONE] Brand=%s | Target=%s | Checked=%s | Changed=%s | Errors=%s", brand["name"], target, len(stores), brand_changed, len(brand_failures))

        status = "PARTIAL_FAILURE" if failures else "SYNCED"
        with db.connection() as conn:
            with conn.transaction():
                conn.execute(
                    "UPDATE vb_patrol_runs SET finished_at=now(), status=%s, brands_processed=%s, outlets_processed=%s WHERE id=%s",
                    (status, processed, outlets_processed, run_id),
                )
        log.info("🏁 [VB PATROL DONE] Run=%s | Status=%s | Brands=%s | Outlets=%s | Errors=%s", run_id, status, processed, outlets_processed, len(failures))
        return {"run_id": run_id, "status": status, "brands_processed": processed, "outlets_processed": outlets_processed, "failures": failures}
    except Exception as exc:
        if run_id is not None:
            try:
                with db.connection() as conn:
                    with conn.transaction():
                        conn.execute(
                            "UPDATE vb_patrol_runs SET finished_at=now(), status='FAILED', error_message=%s WHERE id=%s",
                            (str(exc), run_id),
                        )
            except Exception as mark_error:
                log.error("Gagal menandai patrol run %s sebagai FAILED: %s", run_id, mark_error)
        log.exception("💥 [VB PATROL FAILED] Run=%s | Error=%s", run_id, exc)
        raise
    finally:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_UN)
        finally:
            lock_handle.close()
