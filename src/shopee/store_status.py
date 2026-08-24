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
    Includes 5s AbortController timeout, 3x retries, and DOM badge fallback.
    """
    if not driver or not store_id:
        return None

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"📊 [LIVE STORE API] Fetching real-time store state via /api/seller/store for Store {store_id}...")

        res = None
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script("""
                    var done = arguments[arguments.length - 1];
                    var controller = new AbortController();
                    var timer = setTimeout(function() {
                        controller.abort();
                        done({code: -1, msg: 'Client timeout (5s)'});
                    }, 5000);
                    fetch('https://foody.shopee.co.id/api/seller/store', {
                        method: 'GET',
                        credentials: 'include',
                        headers: { 'Accept': 'application/json, text/plain, */*' },
                        signal: controller.signal
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(d) { clearTimeout(timer); done(d); })
                    .catch(function(e) { clearTimeout(timer); done({code: -1, msg: e.message || String(e)}); });
                """)
                if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
                    break
                else:
                    log.warning(f"  ⚠️ [LIVE STORE API] Percobaan {attempt}/2 respon API: {res}")
            except Exception as async_err:
                log.warning(f"  ⚠️ [LIVE STORE API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        log.info(f"  🔍 [LIVE STORE API RAW RESPONSE] Store {store_id} | Raw Res: {res}")

        if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
            data = res["data"]
            store_data = data.get("store", {})
            op_data = data.get("opening_status", {})

            display_status = op_data.get("display_opening_status", op_data.get("opening_status", store_data.get("opening_status", 0)))
            order_enabled = op_data.get("order_enabled", 0)
            pause_time = op_data.get("pause_time") or {}
            pause_start = pause_time.get("pause_start_time", 0) if isinstance(pause_time, dict) else 0

            if (display_status == 2 or order_enabled == 1) and pause_start == 0:
                status_str = "OPEN"
            else:
                status_str = "CLOSED"

            log.info(
                f"  ✅ [REALTIME LIVE STATE] Store {store_id} | "
                f"Status: {status_str} | display_opening_status: {display_status} | "
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

        # Fallback: DOM Check with Badge status text & dot inspection
        log.warning(f"  ⚠️ [LIVE STORE API FALLBACK] Respon API /api/seller/store bukan 0: {res}. Menjalankan pengecekan DOM Badge...")
        
        dom_status = driver.execute_script("""
            var badgeText = Array.from(document.querySelectorAll('.shopee-food-badge-status-text, .shopee-food-badge-status, .ant-badge'))
                .map(el => (el.innerText || el.textContent || '').trim().toLowerCase())
                .join(' ');

            var dots = Array.from(document.querySelectorAll('.shopee-food-badge-status-dot'))
                .map(el => (el.getAttribute('style') || '').toLowerCase());
            
            var bodyText = (document.body ? document.body.innerText : '').toLowerCase();

            var isOpen = badgeText.includes('buka') || badgeText.includes('open') || 
                         dots.some(d => d.includes('48, 181, 102') || d.includes('#30b566')) ||
                         bodyText.includes('tutup outlet sementara');

            var isClosed = badgeText.includes('tutup sementara') || badgeText.includes('pause') || badgeText.includes('closed') ||
                           dots.some(d => d.includes('238, 44, 74') || d.includes('#ee2c4a')) ||
                           bodyText.includes('buka outlet');

            if (isOpen && !isClosed) return 'OPEN';
            if (isClosed && !isOpen) return 'CLOSED';
            if (isOpen) return 'OPEN';
            if (isClosed) return 'CLOSED';
            return null;
        """)

        if dom_status == "OPEN":
            log.info("  ✅ [LIVE DOM STATUS] Badge/DOM status detected -> Store is OPEN.")
            return {"opening_status": 2, "order_enabled": 1, "status_str": "OPEN", "raw": {"source": "partner_dom_badge"}}
        elif dom_status == "CLOSED":
            log.info("  ✅ [LIVE DOM STATUS] Badge/DOM status detected -> Store is CLOSED.")
            return {"opening_status": 3, "order_enabled": 0, "status_str": "CLOSED", "raw": {"source": "partner_dom_badge"}}

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
        res = None
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script("""
                    var done = arguments[arguments.length - 1];
                    var controller = new AbortController();
                    var timer = setTimeout(function() {
                        controller.abort();
                        done({code: -1, msg: 'Client timeout (5s)'});
                    }, 5000);
                    fetch('https://foody.shopee.co.id/api/seller/store/regular-hours', {
                        method: 'GET',
                        credentials: 'include',
                        headers: { 'Accept': 'application/json, text/plain, */*' },
                        signal: controller.signal
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(d) { clearTimeout(timer); done(d); })
                    .catch(function(e) { clearTimeout(timer); done({code: -1, msg: e.message || String(e)}); });
                """)
                if isinstance(res, dict) and res.get("code") == 0:
                    break
            except Exception as async_err:
                log.warning(f"  ⚠️ [REGULAR HOURS API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        log.info(f"  🔍 [REGULAR HOURS API RESPONSE] Store {store_id} | Response: {res.get('code') if isinstance(res, dict) else None}")
        if isinstance(res, dict) and res.get("code") == 0:
            reg_hours = res.get("data", {}).get("regular_hours", [])
            log.info(f"  ✅ [PULL REGULAR HOURS SUCCESS] Berhasil menarik data jadwal reguler ({len(reg_hours)} hari terkonfigurasi).")
            return res.get("data")
    except Exception as e:
        log.warning(f"⚠️ Gagal menarik data jadwal reguler untuk store {store_id}: {e}")

    return None


def pause_store_action(
    driver,
    store_id: str,
    merchant_id: str = "14367488",
    pause_duration_minutes: int = 1440,
    pause_end_time_ms: Optional[int] = None,
) -> bool:
    """
    Triggers store pause (Auto Close) for store_id.
    Uses the in-browser XHR POST API directly. UI interaction is intentionally
    disabled while this execution path is being evaluated.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"🌐 [ACTION PAUSE XHR] Executing direct API action for Store {store_id} (UI disabled)...")

        # Direct XHR POST with explicit store_id query parameter.
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    var now = Date.now();
                    var end = {pause_end_time_ms if pause_end_time_ms is not None else f"now + ({pause_duration_minutes} * 60 * 1000)"};
                    fetch('https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id={store_id}', {{
                        method: 'POST',
                        credentials: 'include',
                        headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*' }},
                        body: JSON.stringify({{
                            "pause_start_time": now,
                            "pause_end_time": end,
                            "store_id": {target_num}
                        }}),
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                log.info(f"  🔍 [PAUSE API RESPONSE] Store {store_id} (Attempt {attempt}/2) | Response: {res}")
                if isinstance(res, dict) and res.get("code") == 0:
                    log.info(f"  ✅ [ACTION PAUSE SUCCESS] Store {store_id} berhasil di-pause (Tutup Toko via API).")
                    return True
            except Exception as async_err:
                log.warning(f"  ⚠️ [PAUSE API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

    except Exception as e:
        log.error(f"  ❌ Failed to execute pause action for store {store_id}: {e}")

    return False


def open_store_action(driver, store_id: str, merchant_id: str = "14367488") -> bool:
    """
    Triggers store reopen (Auto Open) for store_id.
    Uses the in-browser XHR POST API directly. UI interaction is intentionally
    disabled while this execution path is being evaluated.
    """
    if not driver or not store_id:
        return False

    try:
        ensure_business_hours_page(driver, store_id)

        log.info(f"🌐 [ACTION OPEN XHR] Executing direct API action for Store {store_id} (UI disabled)...")

        # Direct XHR POST with explicit store_id query parameter.
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    fetch('https://foody.shopee.co.id/api/seller/store/opening-status/action/open?store_id={store_id}', {{
                        method: 'POST',
                        credentials: 'include',
                        headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*' }},
                        body: JSON.stringify({{
                            "store_id": "{store_id}"
                        }}),
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                log.info(f"  🔍 [OPEN API RESPONSE] Store {store_id} (Attempt {attempt}/2) | Response: {res}")
                if isinstance(res, dict) and res.get("code") == 0:
                    log.info(f"  ✅ [ACTION OPEN SUCCESS] Store {store_id} berhasil dibuka (Buka Toko via API).")
                    return True
            except Exception as async_err:
                log.warning(f"  ⚠️ [OPEN API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

    except Exception as e:
        log.error(f"  ❌ Failed to execute open action for store {store_id}: {e}")

    return False
