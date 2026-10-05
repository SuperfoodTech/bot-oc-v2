import time
import json
import logging
from typing import Dict, Any, Optional
from selenium.webdriver.common.by import By

try:
    from core.logger import get_logger
    log = get_logger("shopee.store_status")
except ImportError:
    log = logging.getLogger("shopee.store_status")


class StoreIdentityMismatch(Exception):
    """Raised when Shopee returns data for a different store than requested."""


def is_on_shopee_partner(driver) -> bool:
    """Checks if the browser driver is currently on the Shopee Partner portal domain."""
    if not driver:
        return False
    try:
        url = str(getattr(driver, "current_url", "") or "").lower()
        return "partner.shopee.co.id" in url or "foody.shopee.co.id" in url
    except Exception:
        return False


def ensure_business_hours_page(driver, store_id: str) -> bool:
    """
    Navigates Chrome browser to the exact Business Hours URL for store_id and verifies if the Business Hours menu is fully loaded.
    URL: https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}
    Acts as the reliable fallback mechanism when virtual switch requires full page hydration.
    """
    if not driver or not store_id:
        return False

    sid = str(store_id).strip()
    target_url = f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={sid}"
    try:
        current_url = str(getattr(driver, "current_url", "") or "").lower()
    except Exception as exc:
        log.warning(f"  ⚠️ [NAVIGATE BUSINESS HOURS] Tidak bisa membaca current_url untuk Store {sid}: {exc}")
        return False
    
    if f"storeid={sid}".lower() not in current_url:
        log.info(f"🌐 [NAVIGATE BUSINESS HOURS] Navigasi browser ke menu business hours untuk store {sid}: {target_url}")
        try:
            driver.get(target_url)
        except Exception as exc:
            log.warning(f"  ⚠️ [NAVIGATE BUSINESS HOURS] Navigasi gagal untuk Store {sid}: {exc}")
            return False
        time.sleep(2.0)

    # Verifikasi langsung keterdeteksian menu Business Hours untuk target store_id
    is_loaded = False
    for attempt in range(1, 4):
        try:
            check_res = driver.execute_script("""
                var targetStoreId = String(arguments[0] || '').trim().toLowerCase();
                var bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                var validKeywords = [
                    'jam operasional', 'tutup outlet', 'buka outlet', 'jadwal operasional', 'jadwal khusus', 'jadwal reguler',
                    'business hours', 'regular hours', 'special hours', 'pause store', 'close store', 'open store', 'order settings'
                ];
                var hasKeywords = validKeywords.some(function(k) { return bodyText.includes(k); });
                var currUrl = window.location.href.toLowerCase();
                var storeParam = '';
                try {
                    storeParam = String(new URL(window.location.href).searchParams.get('storeId') || '').trim().toLowerCase();
                } catch (e) {}
                return {
                    url_match: currUrl.includes('business-hours'),
                    store_match: !!targetStoreId && storeParam === targetStoreId,
                    has_keywords: hasKeywords
                };
            """, sid)
            
            if check_res and check_res.get("url_match") and check_res.get("store_match") and check_res.get("has_keywords"):
                is_loaded = True
                log.info(f"  ✅ [VERIFY BUSINESS HOURS] Outlet Store {sid} BERHASIL TERDETEKSI & TER-LOAD di menu Business Hours! (URL: {getattr(driver, 'current_url', '')})")
                break
            else:
                log.warning(f"  ⚠️ [VERIFY BUSINESS HOURS] Percobaan {attempt}/3: Halaman Business Hours Store {sid} belum ter-load sempurna. Menunggu hidrasi React SPA...")
                time.sleep(2.0)
        except Exception as e:
            log.warning(f"  ⚠️ [VERIFY BUSINESS HOURS] Error saat verifikasi hidrasi halaman: {e}")
            time.sleep(1.5)

    return is_loaded


def switch_store_context(driver, store_id: str, merchant_id: Optional[str] = None) -> bool:
    """
    Switches active store context instantly in-browser (<1ms) via context cookie injection.
    Sets 'shopee_foody_mid' to target merchant_id and 'shopee_tob_entity_id' to store_id.
    Ensures browser is on Shopee Partner portal before injecting.
    """
    if not driver or not store_id:
        return False

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    if not sid:
        return False

    if not is_on_shopee_partner(driver):
        log.info(f"🌐 [INITIAL CONTEXT LOAD] Navigasi awal browser ke partner portal untuk Store {sid}...")
        return ensure_business_hours_page(driver, sid)

    try:
        driver.execute_script("""
            var sid = String(arguments[0] || '').trim();
            var targetMid = String(arguments[1] || '').trim();
            var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
            var mid = (targetMid || existingMid || sid).trim();
            if (sid) {
                // Clear any conflicting host-only cookies to prevent multi-domain collisions
                document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                // Inject MID exclusively on .shopee.co.id domain scope
                if (mid) {
                    document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                }
                // Neutralize entity ID: must be empty string on .shopee.co.id domain
                document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                try {
                    if (mid) localStorage.setItem("shopee_foody_mid", mid);
                    localStorage.setItem("current_store_id", sid);
                } catch(e) {}
            }
            return true;
        """, sid, mid)
        return True
    except Exception as exc:
        log.warning(f"  ⚠️ [VIRTUAL SWITCH] Injeksi cookie konteks gagal untuk Store {sid}: {exc}")
        return ensure_business_hours_page(driver, sid)


def get_actual_store_status(
    driver,
    store_id: str,
    merchant_id: Optional[str] = None,
    use_virtual_switch: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Fetches exact real-time opening status directly from Shopee Partner Dashboard API (`/api/seller/store`).
    Exact real-time condition matching DOCS/store-response.json & UI Screenshot:
    - display_opening_status: 2 (OPEN / BUKA) vs 3 (PAUSE / TUTUP SEMENTARA)
    - order_enabled: 1 (CAN RECEIVE ORDERS) vs 0 (PAUSED / CANNOT RECEIVE ORDERS)
    - pause_time: pause_start_time > 0 indicates active pause
    Includes instant virtual switch with automated fallback to full page navigation on mismatch.
    """
    if not driver or not store_id:
        return None

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    try:
        if use_virtual_switch:
            if not switch_store_context(driver, sid, merchant_id=mid):
                log.warning(f"  ⚠️ [LIVE STORE API] Context switch gagal untuk Store {sid}. Skip fetch live state.")
                return None
        else:
            if not ensure_business_hours_page(driver, sid):
                log.warning(f"  ⚠️ [LIVE STORE API] Business Hours page untuk Store {sid} belum tervalidasi. Skip fetch live state.")
                return None

        log.info(f"📊 [LIVE STORE API] Fetching real-time store state via /api/seller/store for Store {sid} (virtual_switch={use_virtual_switch})...")

        res = None
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var targetSid = "{sid}";
                    var targetMid = "{mid}";
                    var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
                    var mid = (targetMid || existingMid || targetSid).trim();
                    var sid = targetSid;
                    if (sid) {{
                        document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                        document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                        if (mid) {{
                            document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                        }}
                        document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                        try {{
                            if (mid) localStorage.setItem("shopee_foody_mid", mid);
                            localStorage.setItem("current_store_id", sid);
                        }} catch(e) {{}}
                    }}
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    var url = 'https://foody.shopee.co.id/api/seller/store' + (targetSid ? ('?store_id=' + targetSid) : '');
                    fetch(url, {{
                        method: 'GET',
                        credentials: 'include',
                        headers: {{ 'Accept': 'application/json, text/plain, */*' }},
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
                    break
                else:
                    log.warning(f"  ⚠️ [LIVE STORE API] Percobaan {attempt}/2 respon API: {res}")
            except Exception as async_err:
                log.warning(f"  ⚠️ [LIVE STORE API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        log.info(f"  🔍 [LIVE STORE API RAW RESPONSE] Store {sid} | Raw Res: {res}")

        if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
            data = res["data"]
            store_data = data.get("store", {})
            requested_store_id = sid
            response_store_id = str(store_data.get("id") or "").strip() if isinstance(store_data, dict) else ""
            log.info(
                f"  🔍 [LIVE STORE IDENTITY] requested_store_id={requested_store_id} "
                f"response_store_id={response_store_id or 'missing'}"
            )
            if response_store_id != requested_store_id:
                if use_virtual_switch:
                    log.warning(
                        f"  ⚠️ [VIRTUAL SWITCH MISMATCH] Store {requested_store_id} returned {response_store_id or 'missing'}. "
                        "Mencoba fallback via full navigation..."
                    )
                    return get_actual_store_status(driver, sid, merchant_id=mid, use_virtual_switch=False)

                log.error(
                    f"  ❌ [LIVE STORE REJECTED] Store ID mismatch: "
                    f"requested={requested_store_id}, response={response_store_id or 'missing'}. "
                    "Live state tidak dipakai."
                )
                raise StoreIdentityMismatch(
                    f"live-store requested={requested_store_id}, response={response_store_id or 'missing'}"
                )

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
                f"  ✅ [REALTIME LIVE STATE] Store {sid} | "
                f"Status: {status_str} | display_opening_status: {display_status} | "
                f"order_enabled: {order_enabled} | "
                f"pause_start_time: {pause_start}"
            )

            store_name = (store_data.get("name") or "").strip() if isinstance(store_data, dict) else ""

            return {
                "opening_status": display_status,
                "order_enabled": order_enabled,
                "status_str": status_str,
                "pause_info": pause_time,
                "timezone": store_data.get("timezone"),
                "store_name": store_name,
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

    except StoreIdentityMismatch:
        raise
    except Exception as e:
        log.warning(f"⚠️ Pengecekan status toko gagal untuk store {sid}: {e}")

    return None


def get_regular_hours(
    driver,
    store_id: str,
    merchant_id: Optional[str] = None,
    use_virtual_switch: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Pulls regular business hours for a specific storeId using instant in-browser virtual switch.
    Endpoint: GET https://foody.shopee.co.id/api/seller/store/regular-hours
    """
    if not driver or not store_id:
        return None

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    try:
        if use_virtual_switch:
            if not switch_store_context(driver, sid, merchant_id=mid):
                log.warning(f"  ⚠️ [REGULAR HOURS API] Context switch gagal untuk Store {sid}. Skip fetch schedule.")
                return None
        else:
            if not ensure_business_hours_page(driver, sid):
                log.warning(f"  ⚠️ [REGULAR HOURS API] Business Hours page untuk Store {sid} belum tervalidasi. Skip fetch schedule.")
                return None

        log.info(f"🕒 [PULL REGULAR HOURS] Menarik data jadwal reguler Store {sid} (virtual_switch={use_virtual_switch})...")
        res = None
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var targetSid = "{sid}";
                    var targetMid = "{mid}";
                    var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
                    var mid = (targetMid || existingMid || targetSid).trim();
                    var sid = targetSid;
                    if (sid) {{
                        document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                        document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                        if (mid) {{
                            document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                        }}
                        document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                        try {{
                            if (mid) localStorage.setItem("shopee_foody_mid", mid);
                            localStorage.setItem("current_store_id", sid);
                        }} catch(e) {{}}
                    }}
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    var url = 'https://foody.shopee.co.id/api/seller/store/regular-hours' + (targetSid ? ('?store_id=' + targetSid) : '');
                    fetch(url, {{
                        method: 'GET',
                        credentials: 'include',
                        headers: {{ 'Accept': 'application/json, text/plain, */*' }},
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                if isinstance(res, dict) and res.get("code") == 0:
                    break
            except Exception as async_err:
                log.warning(f"  ⚠️ [REGULAR HOURS API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        log.info(f"  🔍 [REGULAR HOURS API RESPONSE] Store {sid} | Response: {res.get('code') if isinstance(res, dict) else None}")
        if isinstance(res, dict) and res.get("code") == 0:
            data = res.get("data")
            response_store_id = str(data.get("store_id") or "").strip() if isinstance(data, dict) else ""
            requested_store_id = sid
            log.info(
                f"  🔍 [REGULAR HOURS IDENTITY] requested_store_id={requested_store_id} "
                f"response_store_id={response_store_id or 'missing'}"
            )
            if response_store_id != requested_store_id:
                if use_virtual_switch:
                    log.warning(
                        f"  ⚠️ [VIRTUAL SWITCH MISMATCH] Regular hours requested={requested_store_id}, response={response_store_id or 'missing'}. "
                        "Mencoba fallback via full navigation..."
                    )
                    return get_regular_hours(driver, sid, merchant_id=mid, use_virtual_switch=False)

                log.error(
                    f"  ❌ [REGULAR HOURS REJECTED] Store ID mismatch: "
                    f"requested={requested_store_id}, response={response_store_id or 'missing'}. "
                    "Jadwal tidak disimpan dan jadwal terakhir yang valid tetap dipakai."
                )
                raise StoreIdentityMismatch(
                    f"regular-hours requested={requested_store_id}, response={response_store_id or 'missing'}"
                )

            reg_hours = data.get("regular_hours", [])
            log.info(f"  ✅ [PULL REGULAR HOURS SUCCESS] Berhasil menarik data jadwal reguler ({len(reg_hours)} hari terkonfigurasi).")
            return data
    except StoreIdentityMismatch:
        raise
    except Exception as e:
        log.warning(f"⚠️ Gagal menarik data jadwal reguler untuk store {sid}: {e}")

    return None


def get_special_hours(
    driver,
    store_id: str,
    merchant_id: Optional[str] = None,
    use_virtual_switch: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Pulls special business hours for a specific storeId using instant in-browser virtual switch.
    Endpoint: GET https://foody.shopee.co.id/api/seller/store/special-hours
    """
    if not driver or not store_id:
        return None

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    try:
        if use_virtual_switch:
            if not switch_store_context(driver, sid, merchant_id=mid):
                log.warning(f"  ⚠️ [SPECIAL HOURS API] Context switch gagal untuk Store {sid}. Skip fetch special schedule.")
                return None
        else:
            if not ensure_business_hours_page(driver, sid):
                log.warning(f"  ⚠️ [SPECIAL HOURS API] Business Hours page untuk Store {sid} belum tervalidasi. Skip fetch special schedule.")
                return None

        log.info(f"🕒 [PULL SPECIAL HOURS] Menarik data jadwal khusus Store {sid} (virtual_switch={use_virtual_switch})...")
        res = None
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var targetSid = "{sid}";
                    var targetMid = "{mid}";
                    var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
                    var mid = (targetMid || existingMid || targetSid).trim();
                    var sid = targetSid;
                    if (sid) {{
                        document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                        document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                        if (mid) {{
                            document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                        }}
                        document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                        try {{
                            if (mid) localStorage.setItem("shopee_foody_mid", mid);
                            localStorage.setItem("current_store_id", sid);
                        }} catch(e) {{}}
                    }}
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    var url = 'https://foody.shopee.co.id/api/seller/store/special-hours' + (targetSid ? ('?store_id=' + targetSid) : '');
                    fetch(url, {{
                        method: 'GET',
                        credentials: 'include',
                        headers: {{ 'Accept': 'application/json, text/plain, */*' }},
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                if isinstance(res, dict) and res.get("code") == 0:
                    break
            except Exception as async_err:
                log.warning(f"  ⚠️ [SPECIAL HOURS API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        log.info(f"  🔍 [SPECIAL HOURS API RESPONSE] Store {sid} | Response: {res.get('code') if isinstance(res, dict) else None}")
        if isinstance(res, dict) and res.get("code") == 0:
            data = res.get("data")
            response_store_id = str(data.get("store_id") or "").strip() if isinstance(data, dict) else ""
            requested_store_id = sid
            log.info(
                f"  🔍 [SPECIAL HOURS IDENTITY] requested_store_id={requested_store_id} "
                f"response_store_id={response_store_id or 'missing'}"
            )
            if response_store_id != requested_store_id:
                if use_virtual_switch:
                    log.warning(
                        f"  ⚠️ [VIRTUAL SWITCH MISMATCH] Special hours requested={requested_store_id}, response={response_store_id or 'missing'}. "
                        "Mencoba fallback via full navigation..."
                    )
                    return get_special_hours(driver, sid, merchant_id=mid, use_virtual_switch=False)

                log.error(
                    f"  ❌ [SPECIAL HOURS REJECTED] Store ID mismatch: "
                    f"requested={requested_store_id}, response={response_store_id or 'missing'}. "
                    "Jadwal khusus tidak disimpan."
                )
                raise StoreIdentityMismatch(
                    f"special-hours requested={requested_store_id}, response={response_store_id or 'missing'}"
                )

            spec_hours = data.get("special_hours", []) if isinstance(data, dict) else []
            log.info(f"  ✅ [PULL SPECIAL HOURS SUCCESS] Berhasil menarik data jadwal khusus ({len(spec_hours)} jadwal khusus terkonfigurasi).")
            return data
    except StoreIdentityMismatch:
        raise
    except Exception as e:
        log.warning(f"⚠️ Gagal menarik data jadwal khusus untuk store {sid}: {e}")

    return None


def pause_store_action(
    driver,
    store_id: str,
    merchant_id: Optional[str] = None,
    pause_duration_minutes: int = 1440,
    pause_end_time_ms: Optional[int] = None,
    use_virtual_switch: bool = True,
) -> bool:
    """
    Triggers store pause (Auto Close) for store_id using instant in-browser virtual switch.
    Uses the in-browser XHR POST API directly with automatic fallback to full navigation.
    """
    if not driver or not store_id:
        return False

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    try:
        if use_virtual_switch:
            if not switch_store_context(driver, sid, merchant_id=mid):
                log.warning(f"  ⚠️ [ACTION PAUSE XHR] Context switch gagal untuk Store {sid}. Skip pause action.")
                return False
        else:
            if not ensure_business_hours_page(driver, sid):
                log.warning(f"  ⚠️ [ACTION PAUSE XHR] Business Hours page untuk Store {sid} belum tervalidasi. Skip pause action.")
                return False

        log.info(f"🌐 [ACTION PAUSE XHR] Executing direct API action for Store {sid} (virtual_switch={use_virtual_switch})...")

        target_num = int(sid) if sid.isdigit() else sid
        success = False
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var targetSid = "{sid}";
                    var targetMid = "{mid}";
                    var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
                    var mid = (targetMid || existingMid || targetSid).trim();
                    var sid = targetSid;
                    if (sid) {{
                        document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                        document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                        if (mid) {{
                            document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                        }}
                        document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                        try {{
                            if (mid) localStorage.setItem("shopee_foody_mid", mid);
                            localStorage.setItem("current_store_id", sid);
                        }} catch(e) {{}}
                    }}
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    var now = Date.now();
                    var end = {pause_end_time_ms if pause_end_time_ms is not None else f"now + ({pause_duration_minutes} * 60 * 1000)"};
                    fetch('https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id=' + targetSid, {{
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
                log.info(f"  🔍 [PAUSE API RESPONSE] Store {sid} (Attempt {attempt}/2) | Response: {res}")
                if isinstance(res, dict) and res.get("code") == 0:
                    log.info(f"  ✅ [ACTION PAUSE SUCCESS] Store {sid} berhasil di-pause (Tutup Toko via API).")
                    return True
            except Exception as async_err:
                log.warning(f"  ⚠️ [PAUSE API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        if not success and use_virtual_switch:
            log.warning(f"  ⚠️ [ACTION PAUSE] Virtual switch gagal untuk Store {sid}. Mencoba fallback via full navigation...")
            return pause_store_action(
                driver,
                sid,
                merchant_id=mid,
                pause_duration_minutes=pause_duration_minutes,
                pause_end_time_ms=pause_end_time_ms,
                use_virtual_switch=False,
            )

    except Exception as e:
        log.error(f"  ❌ Failed to execute pause action for store {sid}: {e}")

    return False


def open_store_action(
    driver,
    store_id: str,
    merchant_id: Optional[str] = None,
    use_virtual_switch: bool = True,
) -> bool:
    """
    Triggers store reopen (Auto Open) for store_id using instant in-browser virtual switch.
    Uses the in-browser XHR POST API directly with automatic fallback to full navigation.
    """
    if not driver or not store_id:
        return False

    sid = str(store_id).strip()
    mid = str(merchant_id).strip() if merchant_id else ""
    try:
        if use_virtual_switch:
            if not switch_store_context(driver, sid, merchant_id=mid):
                log.warning(f"  ⚠️ [ACTION OPEN XHR] Context switch gagal untuk Store {sid}. Skip open action.")
                return False
        else:
            if not ensure_business_hours_page(driver, sid):
                log.warning(f"  ⚠️ [ACTION OPEN XHR] Business Hours page untuk Store {sid} belum tervalidasi. Skip open action.")
                return False

        log.info(f"🌐 [ACTION OPEN XHR] Executing direct API action for Store {sid} (virtual_switch={use_virtual_switch})...")

        success = False
        for attempt in range(1, 3):
            try:
                res = driver.execute_async_script(f"""
                    var done = arguments[arguments.length - 1];
                    var targetSid = "{sid}";
                    var targetMid = "{mid}";
                    var existingMid = (document.cookie.match(/(?:^|;\\s*)shopee_foody_mid=([^;]+)/) || [])[1] || '';
                    var mid = (targetMid || existingMid || targetSid).trim();
                    var sid = targetSid;
                    if (sid) {{
                        document.cookie = "shopee_foody_mid=; path=/; max-age=0;";
                        document.cookie = "shopee_tob_entity_id=; path=/; max-age=0;";
                        if (mid) {{
                            document.cookie = "shopee_foody_mid=" + mid + "; path=/; domain=.shopee.co.id;";
                        }}
                        document.cookie = "shopee_tob_entity_id=; path=/; domain=.shopee.co.id;";
                        try {{
                            if (mid) localStorage.setItem("shopee_foody_mid", mid);
                            localStorage.setItem("current_store_id", sid);
                        }} catch(e) {{}}
                    }}
                    var controller = new AbortController();
                    var timer = setTimeout(function() {{
                        controller.abort();
                        done({{code: -1, msg: 'Client timeout (5s)'}});
                    }}, 5000);
                    fetch('https://foody.shopee.co.id/api/seller/store/opening-status/action/open?store_id=' + targetSid, {{
                        method: 'POST',
                        credentials: 'include',
                        headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*' }},
                        body: JSON.stringify({{
                            "store_id": "{sid}"
                        }}),
                        signal: controller.signal
                    }})
                    .then(function(r) {{ return r.json(); }})
                    .then(function(d) {{ clearTimeout(timer); done(d); }})
                    .catch(function(e) {{ clearTimeout(timer); done({{code: -1, msg: e.message || String(e)}}); }});
                """)
                log.info(f"  🔍 [OPEN API RESPONSE] Store {sid} (Attempt {attempt}/2) | Response: {res}")
                if isinstance(res, dict) and res.get("code") == 0:
                    log.info(f"  ✅ [ACTION OPEN SUCCESS] Store {sid} berhasil dibuka (Buka Toko via API).")
                    return True
            except Exception as async_err:
                log.warning(f"  ⚠️ [OPEN API] Percobaan {attempt}/2 error: {async_err}")
            time.sleep(1.0)

        if not success and use_virtual_switch:
            log.warning(f"  ⚠️ [ACTION OPEN] Virtual switch gagal untuk Store {sid}. Mencoba fallback via full navigation...")
            return open_store_action(
                driver,
                sid,
                merchant_id=mid,
                use_virtual_switch=False,
            )

    except Exception as e:
        log.error(f"  ❌ Failed to execute open action for store {sid}: {e}")

    return False
