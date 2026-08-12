import time
import json
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

log = logging.getLogger(__name__)

def ensure_business_hours_page(driver, store_id: str) -> bool:
    """
    Navigates Chrome browser to the exact Business Hours URL for store_id and verifies if the Business Hours menu is fully loaded.
    URL: https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}
    """
    if not driver or not store_id:
        return False

    target_url = f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}"
    current_url = str(driver.current_url or "").lower()
    
    if f"storeid={store_id}".lower() not in current_url:
        log.info(f"🌐 [NAVIGATE BUSINESS HOURS] Navigasi browser ke menu business hours untuk store {store_id}: {target_url}")
        driver.get(target_url)
        time.sleep(2.0)

    # Verifikasi langsung keterdeteksian menu Business Hours untuk target store_id
    is_loaded = False
    for attempt in range(1, 4):
        try:
            check_res = driver.execute_script("""
                var bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                var hasKeywords = bodyText.includes('jam operasional') || bodyText.includes('tutup outlet') || bodyText.includes('buka outlet');
                var currUrl = window.location.href.toLowerCase();
                return {
                    url_match: currUrl.includes('business-hours'),
                    has_keywords: hasKeywords
                };
            """)
            
            if check_res and check_res.get("url_match") and check_res.get("has_keywords"):
                is_loaded = True
                log.info(f"  ✅ [VERIFY BUSINESS HOURS] Outlet Store {store_id} BERHASIL TERDETEKSI & TER-LOAD di menu Business Hours! (URL: {driver.current_url})")
                break
            else:
                log.warning(f"  ⚠️ [VERIFY BUSINESS HOURS] Percobaan {attempt}/3: Halaman Business Hours Store {store_id} belum ter-load sempurna. Menunggu hidrasi React SPA...")
                time.sleep(2.0)
        except Exception as e:
            log.warning(f"  ⚠️ [VERIFY BUSINESS HOURS] Error saat verifikasi hidrasi halaman: {e}")
            time.sleep(1.5)

    return is_loaded


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
    Triggers store pause (Auto Close) for store_id.
    Executes UI Button Click ('Tutup Outlet Sementara') first, then falls back to XHR POST API.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"⚡ [ACTION PAUSE UI] Triggering UI Button Click for Store {store_id}...")

        # 1. UI Button Click (Native React UI trigger on Business Hours page)
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
            log.info("  👉 Clicked 'Tutup Outlet Sementara' button on UI. Confirming modal...")
            time.sleep(1.0)
            modal_confirm = driver.execute_script("""
                var modalBtns = Array.from(document.querySelectorAll('.ant-modal-footer button, div[class*="modal"] button, button'));
                var confirmBtn = modalBtns.find(b => {
                    var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    return txt === 'konfirmasi' || txt === 'ya' || txt === 'setuju' || txt === 'ok' || txt.includes('tutup');
                });
                if (confirmBtn) {
                    confirmBtn.click();
                    return true;
                }
                return false;
            """)
            if modal_confirm:
                log.info("  ✅ [UI ACTION PAUSE SUCCESS] Confirmed 'Tutup Outlet' modal successfully.")
                time.sleep(1.0)
                return True

        # 2. XHR POST API Fallback with explicit store_id query param
        log.info("  🌐 UI Button not found, executing XHR POST fallback with store context...")
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        res = driver.execute_script(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id={store_id}', false);
                xhr.withCredentials = true;
                xhr.setRequestHeader('Content-Type', 'application/json');
                var now = Date.now();
                var end = now + ({pause_duration_minutes} * 60 * 1000);
                xhr.send(JSON.stringify({{
                    "pause_start_time": now,
                    "pause_end_time": end,
                    "store_id": {target_num}
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

    except Exception as e:
        log.error(f"  ❌ Failed to execute pause action for store {store_id}: {e}")

    return False


def open_store_action(driver, store_id: str, merchant_id: str = "14367488") -> bool:
    """
    Triggers store reopen (Auto Open) for store_id.
    Executes UI Button Click ('Buka Outlet') first, then falls back to XHR POST API.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"⚡ [ACTION OPEN UI] Triggering UI Button Click for Store {store_id}...")

        # 1. UI Button Click (Native React UI trigger on Business Hours page)
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
            log.info("  👉 Clicked 'Buka Outlet' button on UI. Confirming modal...")
            time.sleep(1.0)
            modal_confirm = driver.execute_script("""
                var modalBtns = Array.from(document.querySelectorAll('.ant-modal-footer button, div[class*="modal"] button, button'));
                var confirmBtn = modalBtns.find(b => {
                    var txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                    return txt === 'konfirmasi' || txt === 'ya' || txt === 'setuju' || txt === 'ok' || txt.includes('buka');
                });
                if (confirmBtn) {
                    confirmBtn.click();
                    return true;
                }
                return false;
            """)
            if modal_confirm:
                log.info("  ✅ [UI ACTION OPEN SUCCESS] Confirmed 'Buka Outlet' modal successfully.")
                time.sleep(1.0)
                return True

        # 2. XHR POST API Fallback with explicit store_id query param
        log.info("  🌐 UI Button not found, executing XHR POST fallback with store context...")
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        res = driver.execute_script(f"""
            try {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', 'https://foody.shopee.co.id/api/seller/store/opening-status/action/open?store_id={store_id}', false);
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

    except Exception as e:
        log.error(f"  ❌ Failed to execute open action for store {store_id}: {e}")

    return False
