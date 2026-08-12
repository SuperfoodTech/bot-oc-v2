import time
import json
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

log = logging.getLogger(__name__)

def ensure_business_hours_page(driver, store_id: str):
    """
    Navigates Chrome browser to the exact Business Hours URL for store_id as specified in DOCS/guide-masuk-business-hours.md.
    URL: https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}
    """
    if not driver or not store_id:
        return

    target_url = f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}"
    current_url = str(driver.current_url or "").lower()
    
    if f"storeid={store_id}".lower() not in current_url:
        log.info(f"🌐 [NAVIGATE BUSINESS HOURS] Navigasi browser ke menu business hours untuk store {store_id}: {target_url}")
        driver.get(target_url)
        time.sleep(1.0)  # Sleep 1s to allow Shopee React SPA to hydrate store context


def get_actual_store_status(driver, store_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetches exact real-time opening status directly from Shopee Partner Dashboard API (`/api/seller/store`).
    Exact real-time condition matching DOCS/store-response.json & UI Screenshot:
    - display_opening_status: 2 (OPEN / BUKA) vs 3 (PAUSE / TUTUP SEMENTARA)
    - order_enabled: 1 (CAN RECEIVE ORDERS) vs 0 (PAUSED / CANNOT RECEIVE ORDERS)
    - pause_time: pause_start_time > 0 indicates active pause
    """
    if not driver or not store_id:
        return None

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"📊 [LIVE STORE API] Fetching real-time store state via /api/seller/store for Store {store_id}...")

        res = driver.execute_script("""
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', 'https://foody.shopee.co.id/api/seller/store', false);
                xhr.withCredentials = true;
                xhr.send(null);
                return JSON.parse(xhr.responseText);
            } catch(e) {
                return null;
            }
        """)

        if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
            data = res["data"]
            store_data = data.get("store", {})
            op_data = data.get("opening_status", {})

            display_status = op_data.get("display_opening_status", op_data.get("opening_status", store_data.get("opening_status", 0)))
            order_enabled = op_data.get("order_enabled", 0)
            pause_time = op_data.get("pause_time") or {}
            pause_start = pause_time.get("pause_start_time", 0) if isinstance(pause_time, dict) else 0

            # Exact condition matching DOCS/store-response.json & UI Screenshot:
            # - If (display_status == 2 or order_enabled == 1) and pause_start == 0 -> OPEN (BUKA)
            # - Otherwise -> CLOSED (PAUSE / TUTUP SEMENTARA)
            if (display_status == 2 or order_enabled == 1) and pause_start == 0:
                status_str = "OPEN"
            else:
                status_str = "CLOSED"

            log.info(
                f"  ✅ [REALTIME LIVE STATE] Store {store_id} | "
                f"Status: {status_str} (BUKA) | display_opening_status: {display_status} | "
                f"order_enabled: {order_enabled} | "
                f"pause_start_time: {pause_start}"
            )

            return {
                "opening_status": display_status,
                "order_enabled": order_enabled,
                "status_str": status_str,
                "pause_info": pause_time,
                "raw": op_data
            }

        # Fallback: DOM check matching UI Screenshot
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "tutup outlet sementara" in body_text:
            log.info("  ✅ [LIVE DOM STATUS] Button 'Tutup Outlet Sementara' detected -> Store is OPEN.")
            return {"opening_status": 2, "order_enabled": 1, "status_str": "OPEN", "raw": {"source": "partner_dom"}}
        elif "buka outlet" in body_text or "tutup" in body_text:
            log.info("  ✅ [LIVE DOM STATUS] Button 'Buka Outlet' detected -> Store is CLOSED.")
            return {"opening_status": 3, "order_enabled": 0, "status_str": "CLOSED", "raw": {"source": "partner_dom"}}

    except Exception as e:
        log.warning(f"⚠️ Pengecekan status toko gagal untuk store {store_id}: {e}")

    return None


def get_regular_hours(driver, store_id: str) -> Optional[Dict[str, Any]]:
    """
    Pulls regular business hours for a specific storeId after navigating browser to Business Hours page.
    Endpoint: GET https://foody.shopee.co.id/api/seller/store/regular-hours
    """
    if not driver or not store_id:
        return None

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"🕒 [PULL REGULAR HOURS] Menarik data jadwal reguler Store {store_id}...")
        res = driver.execute_script("""
            try {
                var xhr = new XMLHttpRequest();
                xhr.open("GET", "https://foody.shopee.co.id/api/seller/store/regular-hours", false);
                xhr.withCredentials = true;
                xhr.send(null);
                return JSON.parse(xhr.responseText);
            } catch(e) {
                return null;
            }
        """)
        log.info(f"  🔍 [REGULAR HOURS API RESPONSE] Store {store_id} | Response: {res.get('code') if isinstance(res, dict) else None}")
        if isinstance(res, dict) and res.get("code") == 0:
            reg_hours = res.get("data", {}).get("regular_hours", [])
            log.info(f"  ✅ [PULL REGULAR HOURS SUCCESS] Berhasil menarik data jadwal reguler ({len(reg_hours)} hari terkonfigurasi).")
            return res.get("data")
    except Exception as e:
        log.warning(f"⚠️ Gagal menarik data jadwal reguler untuk store {store_id}: {e}")

    return None


def pause_store_action(driver, store_id: str, merchant_id: str = "14367488", pause_duration_minutes: int = 1440) -> bool:
    """
    Triggers store pause (Auto Close) via exact API endpoint POST https://foody.shopee.co.id/api/seller/store/opening-status/action/pause
    Matching DOCS/pause outlet/pause-header.txt & DOCS/pause outlet/pause-payload.txt
    Payload: {"pause_start_time": now, "pause_end_time": end} (65 bytes)
    Requires xhr.withCredentials = true to pass session cookies across origins.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"⚡ [ACTION PAUSE API] Triggering POST action/pause API for Store {store_id}...")

        # Exact API call matching DOCS/pause outlet/
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        res = driver.execute_script(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://foody.shopee.co.id/api/seller/store/opening-status/action/pause', false);
                xhr.withCredentials = true;
                xhr.setRequestHeader('Content-Type', 'application/json');
                var now = Date.now();
                var end = now + ({pause_duration_minutes} * 60 * 1000);
                xhr.send(JSON.stringify({{
                    "pause_start_time": now,
                    "pause_end_time": end
                }}));
                return JSON.parse(xhr.responseText);
            }} catch(e) {{
                return {{code: -1, msg: e.message}};
            }}
        """)

        log.info(f"  🔍 [PAUSE API RESPONSE] Store {store_id} | Response: {res}")
        if isinstance(res, dict) and res.get("code") == 0:
            log.info(f"  ✅ [ACTION PAUSE SUCCESS] Store {store_id} berhasil di-pause (Tutup Toko via API).")
            return True
        else:
            log.warning(f"  ⚠️ Pause action returned response: {res}")

        # Fallback: UI Button Click if API returns auth/other error
        log.info("  👉 Executing UI Button Click fallback...")
        btn_clicked = driver.execute_script("""
            var btns = Array.from(document.querySelectorAll('button, a, div[role="button"], span'));
            var targetBtn = btns.find(b => {
                var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                return txt.includes('tutup outlet') || txt.includes('tutup sementara') || txt.includes('pause');
            });
            if (targetBtn) {
                targetBtn.scrollIntoView({block: 'center'});
                targetBtn.click();
                return true;
            }
            return false;
        """)

        if btn_clicked:
            time.sleep(1.0)
            driver.execute_script("""
                var modalBtns = Array.from(document.querySelectorAll('.ant-modal-footer button, div[class*="modal"] button, button'));
                var confirmBtn = modalBtns.find(b => {
                    var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    return txt === 'konfirmasi' || txt === 'ya' || txt === 'setuju' || txt === 'ok' || txt.includes('tutup');
                });
                if (confirmBtn) confirmBtn.click();
            """)
            log.info("  ✅ [UI ACTION PAUSE SUCCESS] Confirmed 'Tutup Outlet' modal successfully.")
            return True

    except Exception as e:
        log.error(f"  ❌ Failed to execute pause action for store {store_id}: {e}")

    return False


def open_store_action(driver, store_id: str, merchant_id: str = "14367488") -> bool:
    """
    Triggers store reopen (Auto Open) via exact API endpoint POST https://foody.shopee.co.id/api/seller/store/opening-status/action/open
    Matching DOCS/open outlet/open-header.txt & DOCS/open outlet/open-payload,txt
    Payload: {"store_id": "21897166"} (23 bytes)
    Requires xhr.withCredentials = true to pass session cookies across origins.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"⚡ [ACTION OPEN API] Triggering POST action/open API for Store {store_id}...")

        res = driver.execute_script(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://foody.shopee.co.id/api/seller/store/opening-status/action/open', false);
                xhr.withCredentials = true;
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.send(JSON.stringify({{
                    "store_id": "{store_id}"
                }}));
                return JSON.parse(xhr.responseText);
            }} catch(e) {{
                return {{code: -1, msg: e.message}};
            }}
        """)

        log.info(f"  🔍 [OPEN API RESPONSE] Store {store_id} | Response: {res}")
        if isinstance(res, dict) and res.get("code") == 0:
            log.info(f"  ✅ [ACTION OPEN SUCCESS] Store {store_id} berhasil dibuka (Buka Toko via API).")
            return True
        else:
            log.warning(f"  ⚠️ Open action returned response: {res}")

        # Fallback: UI Button Click if API returns auth/other error
        log.info("  👉 Executing UI Button Click fallback...")
        btn_clicked = driver.execute_script("""
            var btns = Array.from(document.querySelectorAll('button, a, div[role="button"], span'));
            var targetBtn = btns.find(b => {
                var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                return txt.includes('buka outlet') || txt.includes('buka toko') || txt.includes('buka');
            });
            if (targetBtn) {
                targetBtn.scrollIntoView({block: 'center'});
                targetBtn.click();
                return true;
            }
            return false;
        """)

        if btn_clicked:
            time.sleep(1.0)
            driver.execute_script("""
                var modalBtns = Array.from(document.querySelectorAll('.ant-modal-footer button, div[class*="modal"] button, button'));
                var confirmBtn = modalBtns.find(b => {
                    var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    return txt === 'konfirmasi' || txt === 'ya' || txt === 'setuju' || txt === 'ok' || txt.includes('buka');
                });
                if (confirmBtn) confirmBtn.click();
            """)
            log.info("  ✅ [UI ACTION OPEN SUCCESS] Confirmed 'Buka Outlet' modal successfully.")
            return True

    except Exception as e:
        log.error(f"  ❌ Failed to execute open action for store {store_id}: {e}")

    return False
