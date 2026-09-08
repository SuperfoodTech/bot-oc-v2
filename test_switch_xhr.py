#!/usr/bin/env python3
"""
test_switch_xhr.py
==================
Reach Shopee Partner dashboard using src/core/browser.py, fetch merchant list
via in-browser XHR, then test switch-merchant via the documented XHR flow.

Observed contract from src/switch merchant:
1. MerchantDetect
   - POST {}
   - uses current dashboard auth context (`x-merchant-token` + existing cookies)
   - returns `merchantList` entries with `merchantId`, `merchantName`,
     `staffTobUid`, and `isCurrentLoginUser`
2. SwitchMerchant
   - POST {"target_tob_uid": "..."}
   - target value comes from MerchantDetect.staffTobUid, not merchantId
   - returns `target_tob_token`, `target_tob_nonce`, and `target_tob_uid`

This script verifies whether calling SwitchMerchant from the browser context is
enough to move the active dashboard session, then optionally restores the
original merchant to avoid leaving the account on a different merchant.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core import browser


MERCHANT_DETECT_URL = (
    "https://api.partner.shopee.co.id/nb/mss/mer-detect-api/"
    "PartnerMerchantDetectServer/MerchantDetect"
)
SWITCH_MERCHANT_URL = (
    "https://api.partner.shopee.co.id/nb/mss/mer-detect-api/"
    "PartnerMerchantDetectServer/SwitchMerchant"
)
GET_USER_INFO_URL = (
    "https://api.partner.shopee.co.id/nb/mss/web-api/"
    "PartnerAccountServer/GetUserInfo"
)
MERCHANT_DETECT_PATH = (
    "/nb/mss/mer-detect-api/PartnerMerchantDetectServer/MerchantDetect"
)
DEFAULT_TIMEZONE = "Asia/Jakarta"
DEFAULT_TIMEOUT_MS = 15_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Shopee merchant switch flow via in-browser XHR.",
    )
    parser.add_argument("--username", default="auto7313")
    parser.add_argument("--target-merchant", default="")
    parser.add_argument("--target-uid", default="")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--keep-browser", action="store_true")
    parser.add_argument(
        "--skip-vibium",
        action="store_true",
        help="Lewati layer verifikasi Vibium.",
    )
    parser.add_argument(
        "--vibium-artifact-dir",
        default="",
        help="Direktori artefak Vibium. Default: direktori temporary baru di /tmp.",
    )
    parser.add_argument(
        "--no-restore",
        action="store_true",
        help="Do not try to switch back to the original merchant after the test.",
    )
    return parser.parse_args()


def print_title(title: str) -> None:
    line = "=" * 88
    print(f"\n{line}\n{title}\n{line}")


def parse_json_maybe(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return text
    try:
        return json.loads(text)
    except Exception:
        return value


def short_token(token: str | None) -> str:
    if not token:
        return "<empty>"
    if len(token) <= 32:
        return token
    return f"{token[:20]}...{token[-8:]}"


def get_cookie_token(driver) -> str:
    token, _ = browser.extract_tokens_from_driver(driver)
    return token or ""


def build_partner_headers(
    token: str,
    timezone: str,
    *,
    request_id: str | None = None,
    client_id: str = "undefined",
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://partner.shopee.co.id",
        "referer": "https://partner.shopee.co.id/",
        "shopee-baggage": "PFB=undefined",
        "x-merchant-from": "12",
        "x-merchant-language": "id",
        "x-merchant-login-from": "12",
        "x-merchant-requestid": request_id or str(uuid.uuid4()),
        "x-merchant-timezone": timezone,
        "x-merchant-tob-clientid": client_id,
        "x-merchant-token": token,
    }
    if extra:
        for key, value in extra.items():
            if value is None:
                continue
            headers[key] = str(value)
    return headers


def vibium_command(
    *args: str,
    input_text: str | None = None,
    allow_failure: bool = False,
) -> dict[str, Any]:
    if not shutil.which("vibium"):
        raise RuntimeError("Vibium tidak ditemukan di PATH.")

    completed = subprocess.run(
        ["vibium", "--json", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    raw = completed.stdout.strip() or completed.stderr.strip()
    payload = parse_json_maybe(raw)
    if not isinstance(payload, dict):
        payload = {
            "ok": completed.returncode == 0,
            "result": raw,
            "stderr": completed.stderr.strip(),
        }

    if not allow_failure and (completed.returncode != 0 or not payload.get("ok", False)):
        raise RuntimeError(
            f"Vibium command gagal: {' '.join(args)} | "
            f"stdout={completed.stdout.strip()} | stderr={completed.stderr.strip()}"
        )
    return payload


def vibium_stop_safely() -> None:
    try:
        vibium_command("stop", allow_failure=True)
    except Exception:
        pass


def capture_vibium_screenshot(output_path: Path) -> str:
    result = vibium_command(
        "screenshot",
        "-o",
        output_path.name,
        "--full-page",
    )
    message = str(result.get("result", ""))
    prefix = "Screenshot saved to "
    saved_path = None
    if prefix in message:
        saved_path = Path(message.split(prefix, 1)[1].strip())

    if saved_path and saved_path.exists():
        if saved_path.resolve() != output_path.resolve():
            shutil.copy2(saved_path, output_path)
        return str(output_path)

    if output_path.exists():
        return str(output_path)

    raise RuntimeError(f"Screenshot Vibium tidak ditemukan. result={message}")


def xhr_json(
    driver,
    *,
    url: str,
    method: str = "POST",
    payload: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, Any]:
    script = """
        const done = arguments[arguments.length - 1];
        const method = arguments[0];
        const url = arguments[1];
        const payload = arguments[2];
        const headers = arguments[3] || {};
        const timeoutMs = arguments[4];

        function currentToken() {
            const item = document.cookie
                .split('; ')
                .find((row) => row.startsWith('shopee_tob_token='));
            return item ? item.split('=').slice(1).join('=') : '';
        }

        try {
            const xhr = new XMLHttpRequest();
            xhr.open(method, url, true);
            xhr.withCredentials = true;
            xhr.timeout = timeoutMs;

            Object.entries(headers).forEach(([key, value]) => {
                if (value !== undefined && value !== null && String(value) !== '') {
                    xhr.setRequestHeader(key, String(value));
                }
            });

            xhr.onreadystatechange = function () {
                if (xhr.readyState !== 4) {
                    return;
                }
                let parsed = null;
                const raw = xhr.responseText || '';
                try {
                    parsed = raw ? JSON.parse(raw) : null;
                } catch (err) {
                    parsed = null;
                }
                done({
                    ok: xhr.status >= 200 && xhr.status < 300,
                    status: xhr.status,
                    response: parsed,
                    responseText: raw,
                    responseHeaders: xhr.getAllResponseHeaders(),
                    currentToken: currentToken(),
                    currentUrl: window.location.href,
                });
            };

            xhr.onerror = function () {
                done({
                    ok: false,
                    status: xhr.status || 0,
                    error: 'xhr.onerror',
                    responseText: xhr.responseText || '',
                    currentToken: currentToken(),
                    currentUrl: window.location.href,
                });
            };

            xhr.ontimeout = function () {
                done({
                    ok: false,
                    status: xhr.status || 0,
                    error: 'xhr.ontimeout',
                    responseText: xhr.responseText || '',
                    currentToken: currentToken(),
                    currentUrl: window.location.href,
                });
            };

            xhr.send(payload == null ? null : JSON.stringify(payload));
        } catch (err) {
            done({
                ok: false,
                status: 0,
                error: String(err),
                currentToken: currentToken(),
                currentUrl: window.location.href,
            });
        }
    """
    return driver.execute_async_script(
        script,
        method,
        url,
        payload,
        headers or {},
        timeout_ms,
    )


def get_user_info(
    driver,
    *,
    token: str,
    timezone: str,
    extra_headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return xhr_json(
        driver,
        url=GET_USER_INFO_URL,
        payload={},
        headers=build_partner_headers(token, timezone, extra=extra_headers),
    )


def get_merchant_list(driver, *, token: str, timezone: str) -> list[dict[str, Any]]:
    last_merchants: list[dict[str, Any]] = []
    for _ in range(3):
        result = xhr_json(
            driver,
            url=MERCHANT_DETECT_URL,
            payload={},
            headers=build_partner_headers(token, timezone),
        )
        response = result.get("response") or {}
        data = response.get("data") or {}
        select_merchant = data.get("selectMerchant") or {}
        merchants = select_merchant.get("merchantList") or []
        if isinstance(merchants, list) and merchants:
            return merchants
        if isinstance(merchants, list):
            last_merchants = merchants
        time.sleep(2)
    return last_merchants


def choose_target_merchant(
    merchants: list[dict[str, Any]],
    *,
    current_merchant_id: str,
    target_name: str,
    target_uid: str,
) -> dict[str, Any]:
    if target_uid:
        for merchant in merchants:
            if str(merchant.get("staffTobUid") or "") == str(target_uid):
                return merchant
        raise ValueError(f"Target uid '{target_uid}' tidak ditemukan di merchant list.")

    if target_name:
        wanted = target_name.strip().lower()
        for merchant in merchants:
            if str(merchant.get("merchantName") or "").strip().lower() == wanted:
                return merchant
        raise ValueError(f"Target merchant '{target_name}' tidak ditemukan di merchant list.")

    for merchant in merchants:
        merchant_id = str(merchant.get("merchantId") or "")
        if merchant.get("isCurrentLoginUser"):
            continue
        if current_merchant_id and merchant_id == current_merchant_id:
            continue
        return merchant

    raise ValueError("Tidak ada merchant target non-current yang bisa dipakai untuk test.")


def wait_for_dashboard(driver, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        current = str(driver.current_url or "")
        if "/food/dashboard" in current:
            return True
        time.sleep(0.5)
    return False


def read_ui_merchant_name(driver) -> str:
    try:
        element = driver.find_element(By.CSS_SELECTOR, ".merchantName")
        return (element.text or "").strip()
    except Exception:
        return ""


def summarize_merchant(merchant: dict[str, Any]) -> str:
    return (
        f"{merchant.get('merchantName')} | merchantId={merchant.get('merchantId')} | "
        f"staffTobUid={merchant.get('staffTobUid')} | "
        f"isCurrentLoginUser={merchant.get('isCurrentLoginUser')}"
    )


def switch_merchant(
    driver,
    *,
    current_token: str,
    target_tob_uid: str,
    timezone: str,
) -> dict[str, Any]:
    return xhr_json(
        driver,
        url=SWITCH_MERCHANT_URL,
        payload={"target_tob_uid": str(target_tob_uid)},
        headers=build_partner_headers(current_token, timezone),
    )


def verify_current_state(driver, *, timezone: str) -> dict[str, Any]:
    last_state = {
        "cookie_token": "",
        "user_info_result": {},
        "user_data": {},
        "ui_name": "",
    }
    for _ in range(3):
        current_token = get_cookie_token(driver)
        user_info_result = get_user_info(driver, token=current_token, timezone=timezone)
        response = user_info_result.get("response") or {}
        user_data = response.get("data") or {}
        ui_name = read_ui_merchant_name(driver)
        last_state = {
            "cookie_token": current_token,
            "user_info_result": user_info_result,
            "user_data": user_data,
            "ui_name": ui_name,
        }
        if user_data or ui_name:
            return last_state
        time.sleep(2)
    return last_state


def get_merchant_detect_resource_entries(driver) -> list[dict[str, Any]]:
    script = """
        return performance.getEntriesByType('resource')
            .filter((entry) => entry && entry.name && entry.name.includes(arguments[0]))
            .map((entry) => ({
                name: entry.name,
                initiatorType: entry.initiatorType || '',
                durationMs: Math.round(entry.duration || 0),
                responseStatus: typeof entry.responseStatus === 'number' ? entry.responseStatus : null,
            }));
    """
    result = driver.execute_script(script, MERCHANT_DETECT_PATH)
    return result if isinstance(result, list) else []


def collect_selector_overlay_state(driver) -> dict[str, Any]:
    script = """
        const generic = [
            'akun', 'pengaturan', 'log out', 'logout', 'keluar',
            'halaman utama', 'baru', 'menu', 'outlet', 'shopeefood',
            'terapkan', 'sembunyikan', 'notifikasi', 'pilih merchant lain',
            'switch merchant', 'ganti merchant', 'pusat bantuan',
            'transaksi berhasil', 'baris per halaman', 'ringkasan toko',
            'nama toko', 'jumlah total', 'laporan saya', 'penghasilan',
            'performa outlet', 'periode transaksi', 'ubah bahasa',
            'daftar merchant', 'daftar di sini', 'memulai bisnis baru?',
            'pilih merchant', 'gabung dengan merchant', 'buat merchant baru',
            'hubungi kami', 'faq', 'syarat & ketentuan', 'pusat edukasi seller'
        ];

        const candidates = Array.from(document.querySelectorAll(
            'li.ant-menu-item, li[role="menuitem"], .ant-dropdown-menu-item, '
            + '[class*="menu-item"], .listItem, .merchant-item, li, span, div, a'
        ));

        const texts = [];
        const merchantTexts = [];
        for (const el of candidates) {
            const rect = el.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const raw = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            if (!raw) continue;
            if (!texts.includes(raw)) texts.push(raw);

            const lowered = raw.toLowerCase();
            if (raw.length < 3 || raw.length > 60) continue;
            if (generic.some((item) => lowered === item || lowered.includes(item))) continue;
            if (!merchantTexts.includes(raw)) merchantTexts.push(raw);
        }

        return {
            currentUrl: window.location.href,
            visibleTexts: texts.slice(0, 25),
            merchantTexts: merchantTexts.slice(0, 20),
            bodyExcerpt: ((document.body || {}).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 260),
        };
    """
    result = driver.execute_script(script)
    return result if isinstance(result, dict) else {}


def click_profile_then_switch_menu_like_browser_switch(driver) -> bool:
    try:
        wait = WebDriverWait(driver, 15)
        quick_wait = WebDriverWait(driver, 3)
        actions = ActionChains(driver)

        profile_menu = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".merchantName"))
        )
        actions.move_to_element(profile_menu).click().perform()
        time.sleep(1)

        try:
            switch_trigger = quick_wait.until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//span[contains(text(), 'Pilih Merchant Lain') or contains(text(), 'Switch Merchant')]",
                    )
                )
            )
            actions.move_to_element(switch_trigger).click().perform()
            time.sleep(1)
            return True
        except Exception:
            js_found = driver.execute_script(
                """
                var spans = document.querySelectorAll('span, p, div');
                for (var s of spans) {
                    var text = (s.innerText || '').trim();
                    if (text.includes('Pilih Merchant Lain') || text.includes('Switch Merchant')) {
                        s.click();
                        return true;
                    }
                }
                return false;
                """
            )
            if js_found:
                time.sleep(1)
                return True
    except Exception:
        return False
    return False


def poll_selector_trigger_result(
    driver,
    *,
    before_count: int,
    timeout_seconds: float = 8.0,
) -> tuple[list[dict[str, Any]], dict[str, Any], bool, bool]:
    selector_state: dict[str, Any] = {}
    after_entries = get_merchant_detect_resource_entries(driver)
    detect_triggered = False
    selector_visible = False

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        after_entries = get_merchant_detect_resource_entries(driver)
        selector_state = collect_selector_overlay_state(driver)
        detect_triggered = len(after_entries) > before_count
        selector_visible = bool(selector_state.get("merchantTexts"))
        if detect_triggered or selector_visible:
            break
        time.sleep(1)

    return after_entries, selector_state, detect_triggered, selector_visible


def trigger_merchant_detect_via_browser_ui(driver) -> dict[str, Any]:
    before_entries = get_merchant_detect_resource_entries(driver)
    before_count = len(before_entries)
    helper_ok = bool(browser.return_to_selector(driver))
    after_entries, selector_state, detect_triggered, selector_visible = (
        poll_selector_trigger_result(driver, before_count=before_count)
    )
    exact_switch_path_used = False

    if not detect_triggered:
        exact_switch_path_used = click_profile_then_switch_menu_like_browser_switch(
            driver
        )
        if exact_switch_path_used:
            after_entries, selector_state, detect_triggered, selector_visible = (
                poll_selector_trigger_result(driver, before_count=before_count)
            )

    return {
        "helper_ok": helper_ok,
        "exact_switch_path_used": exact_switch_path_used,
        "before_count": before_count,
        "after_count": len(after_entries),
        "detect_triggered": detect_triggered,
        "selector_visible": selector_visible,
        "selector_state": selector_state,
        "cookie_token": get_cookie_token(driver),
    }


def current_origin_from_driver(driver) -> str:
    current_url = str(driver.current_url or "").strip()
    if not current_url:
        return "https://partner.shopee.co.id"
    parts = urlsplit(current_url)
    if not parts.scheme or not parts.netloc:
        return "https://partner.shopee.co.id"
    return f"{parts.scheme}://{parts.netloc}"


def export_storage_dict(driver, storage_name: str) -> dict[str, str]:
    script = """
        const target = window[arguments[0]];
        const data = {};
        for (let i = 0; i < target.length; i += 1) {
            const key = target.key(i);
            data[key] = target.getItem(key);
        }
        return data;
    """
    result = driver.execute_script(script, storage_name)
    return result if isinstance(result, dict) else {}


def build_vibium_storage_state(driver) -> dict[str, Any]:
    cookies_out: list[dict[str, Any]] = []
    for cookie in driver.get_cookies():
        item: dict[str, Any] = {
            "name": cookie.get("name", ""),
            "value": cookie.get("value", ""),
            "domain": cookie.get("domain", ""),
            "path": cookie.get("path", "/"),
        }
        if cookie.get("expiry") is not None:
            item["expires"] = int(cookie["expiry"])
        if cookie.get("httpOnly") is not None:
            item["httpOnly"] = bool(cookie["httpOnly"])
        if cookie.get("secure") is not None:
            item["secure"] = bool(cookie["secure"])
        same_site = cookie.get("sameSite")
        if same_site:
            item["sameSite"] = str(same_site).lower()
        cookies_out.append(item)

    storage_payload = {
        "origin": current_origin_from_driver(driver),
        "localStorage": export_storage_dict(driver, "localStorage"),
        "sessionStorage": export_storage_dict(driver, "sessionStorage"),
    }
    return {
        "cookies": cookies_out,
        "storage": json.dumps(storage_payload, ensure_ascii=True),
    }


def write_vibium_storage_state(driver, output_path: Path) -> Path:
    output_path.write_text(
        json.dumps(build_vibium_storage_state(driver), indent=2, ensure_ascii=True)
    )
    return output_path


def collect_vibium_ui_state() -> dict[str, Any]:
    expression = """
        JSON.stringify((() => {
            const pickTexts = (selector, limit = 12) => {
                const values = Array.from(document.querySelectorAll(selector))
                    .map((el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim())
                    .filter(Boolean);
                return Array.from(new Set(values)).slice(0, limit);
            };

            return {
                currentUrl: window.location.href,
                title: document.title,
                merchantName: ((document.querySelector('.merchantName') || {}).innerText || '').trim(),
                headings: pickTexts('h1, h2, h3, [role=\"heading\"]', 10),
                buttons: pickTexts('button', 12),
                statusTexts: pickTexts('.ant-alert, .ant-tag, [class*=\"status\"], [class*=\"badge\"], [role=\"alert\"]', 20),
                bodyTextExcerpt: ((document.body || {}).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 280),
            };
        })())
    """
    result = vibium_command("eval", "--stdin", input_text=expression)
    return parse_json_maybe(result.get("result")) or {}


def collect_vibium_resource_structure() -> dict[str, Any]:
    expression = """
        JSON.stringify((() => {
            const entries = performance.getEntriesByType('resource');
            const seen = new Set();
            const rows = [];

            for (const entry of entries) {
                if (!/shopee/i.test(entry.name)) {
                    continue;
                }
                let host = '';
                let path = entry.name;
                let queryKeys = [];
                try {
                    const url = new URL(entry.name);
                    host = url.host;
                    path = url.pathname;
                    queryKeys = Array.from(new Set(Array.from(url.searchParams.keys())));
                } catch (err) {}

                const key = `${host}|${path}|${entry.initiatorType || ''}`;
                if (seen.has(key)) {
                    continue;
                }
                seen.add(key);
                rows.push({
                    host,
                    path,
                    queryKeys,
                    initiatorType: entry.initiatorType || '',
                    transferSize: entry.transferSize || 0,
                    encodedBodySize: entry.encodedBodySize || 0,
                    decodedBodySize: entry.decodedBodySize || 0,
                    responseStatus: typeof entry.responseStatus === 'number' ? entry.responseStatus : null,
                    durationMs: Math.round(entry.duration || 0),
                });
            }

            return {
                totalResources: entries.length,
                shopeeResources: rows.slice(-40),
            };
        })())
    """
    result = vibium_command("eval", "--stdin", input_text=expression)
    return parse_json_maybe(result.get("result")) or {}


def collect_vibium_network_verification(timezone: str) -> dict[str, Any]:
    expression = f"""
        (async () => {{
            const tokenRow = document.cookie
                .split('; ')
                .find((row) => row.startsWith('shopee_tob_token='));
            const token = tokenRow ? tokenRow.split('=').slice(1).join('=') : '';

            const baseHeaders = {{
                'accept': 'application/json, text/plain, */*',
                'content-type': 'application/json',
                'origin': 'https://partner.shopee.co.id',
                'referer': 'https://partner.shopee.co.id/',
                'shopee-baggage': 'PFB=undefined',
                'x-merchant-from': '12',
                'x-merchant-language': 'id',
                'x-merchant-login-from': '12',
                'x-merchant-timezone': {json.dumps(timezone)},
                'x-merchant-tob-clientid': 'undefined',
                'x-merchant-token': token,
            }};

            const call = async (name, url) => {{
                const headers = {{
                    ...baseHeaders,
                    'x-merchant-requestid': `vibium-${{name}}-${{Date.now()}}`,
                }};
                const response = await fetch(url, {{
                    method: 'POST',
                    credentials: 'include',
                    headers,
                    body: '{{}}',
                }});
                let body = null;
                try {{
                    body = await response.json();
                }} catch (err) {{}}

                const merchantList = body?.data?.selectMerchant?.merchantList;
                const currentRows = Array.isArray(merchantList)
                    ? merchantList
                        .filter((item) => item && item.isCurrentLoginUser)
                        .map((item) => item.merchantName)
                    : [];

                return {{
                    name,
                    method: 'POST',
                    urlPath: new URL(url).pathname,
                    status: response.status,
                    ok: response.ok,
                    errorCode: body?.errorCode ?? body?.code ?? null,
                    errorMsg: body?.errorMsg ?? body?.message ?? body?.msg ?? '',
                    merchantName: body?.data?.merchantName ?? null,
                    merchantId: body?.data?.merchantId ?? null,
                    merchantCount: Array.isArray(merchantList) ? merchantList.length : null,
                    currentLoginMerchants: currentRows,
                }};
            }};

            const output = {{
                tokenPresent: Boolean(token),
                tokenLength: token.length,
                calls: [
                    await call('GetUserInfo', {json.dumps(GET_USER_INFO_URL)}),
                    await call('MerchantDetect', {json.dumps(MERCHANT_DETECT_URL)}),
                ],
            }};
            return JSON.stringify(output);
        }})()
    """
    result = vibium_command("eval", "--stdin", input_text=expression)
    return parse_json_maybe(result.get("result")) or {}


def run_vibium_verification(
    driver,
    *,
    stage_name: str,
    timezone: str,
    artifact_root: Path,
    dashboard_url: str,
) -> dict[str, Any]:
    if not shutil.which("vibium"):
        return {
            "status": "blocked",
            "reason": "CLI vibium tidak tersedia.",
        }

    stage_dir = artifact_root / stage_name
    stage_dir.mkdir(parents=True, exist_ok=True)
    state_fd, state_name = tempfile.mkstemp(
        prefix=f"vibium-{stage_name}-",
        suffix=".json",
    )
    os.close(state_fd)
    state_path = Path(state_name)
    write_vibium_storage_state(driver, state_path)

    screenshot_desktop = stage_dir / f"{stage_name}-desktop.png"
    screenshot_mobile = stage_dir / f"{stage_name}-mobile.png"
    map_path = stage_dir / "map.txt"
    a11y_path = stage_dir / "a11y_tree.txt"
    text_path = stage_dir / "page_text.txt"
    html_path = stage_dir / "page_html.html"
    ui_state_path = stage_dir / "ui_state.json"
    network_path = stage_dir / "network_structure.json"

    try:
        vibium_stop_safely()
        vibium_command("start", "--headless")
        vibium_command("go", "https://partner.shopee.co.id")
        vibium_command("wait", "load")
        vibium_command("storage", "restore", str(state_path))
        vibium_command("go", dashboard_url)
        vibium_command("wait", "load")
        time.sleep(2)

        vibium_command("viewport", "1440", "900")
        capture_vibium_screenshot(screenshot_desktop)
        desktop_map = vibium_command("map")
        desktop_a11y = vibium_command("a11y-tree", "--everything")
        page_text = vibium_command("text")
        page_html = vibium_command("html")

        vibium_command("viewport", "390", "844")
        capture_vibium_screenshot(screenshot_mobile)

        ui_state = {}
        resource_structure = {}
        verification_calls = {}
        for attempt in range(3):
            ui_state = collect_vibium_ui_state()
            resource_structure = collect_vibium_resource_structure()
            verification_calls = collect_vibium_network_verification(timezone)
            if ui_state.get("merchantName") or ui_state.get("buttons") or ui_state.get("bodyTextExcerpt"):
                break
            time.sleep(2)

        map_path.write_text(str(desktop_map.get("result", "")), encoding="utf-8")
        a11y_path.write_text(str(desktop_a11y.get("result", "")), encoding="utf-8")
        text_path.write_text(str(page_text.get("result", "")), encoding="utf-8")
        html_path.write_text(str(page_html.get("result", "")), encoding="utf-8")
        ui_state_path.write_text(
            json.dumps(ui_state, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        network_path.write_text(
            json.dumps(
                {
                    "resource_structure": resource_structure,
                    "verification_calls": verification_calls,
                },
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )

        return {
            "status": "verified",
            "stage_dir": str(stage_dir),
            "desktop_screenshot": str(screenshot_desktop),
            "mobile_screenshot": str(screenshot_mobile),
            "map_path": str(map_path),
            "a11y_path": str(a11y_path),
            "text_path": str(text_path),
            "html_path": str(html_path),
            "ui_state_path": str(ui_state_path),
            "network_path": str(network_path),
            "ui_state": ui_state,
            "resource_structure": resource_structure,
            "verification_calls": verification_calls,
        }
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": str(exc),
            "stage_dir": str(stage_dir),
        }
    finally:
        try:
            state_path.unlink(missing_ok=True)
        except Exception:
            pass
        vibium_stop_safely()


def print_vibium_summary(label: str, report: dict[str, Any]) -> None:
    print_title(f"VIBIUM VERIFICATION - {label}")
    print(f"Status           : {report.get('status')}")
    if report.get("stage_dir"):
        print(f"Artifact dir     : {report.get('stage_dir')}")
    if report.get("status") != "verified":
        print(f"Reason           : {report.get('reason')}")
        return

    ui_state = report.get("ui_state") or {}
    resources = (report.get("resource_structure") or {}).get("shopeeResources") or []
    verification_calls = (report.get("verification_calls") or {}).get("calls") or []

    print(f"UI current URL   : {ui_state.get('currentUrl')}")
    print(f"UI merchant      : {ui_state.get('merchantName') or '<tidak terbaca>'}")
    print(f"UI headings      : {', '.join((ui_state.get('headings') or [])[:4]) or '<kosong>'}")
    print(f"UI status texts  : {', '.join((ui_state.get('statusTexts') or [])[:4]) or '<kosong>'}")
    if ui_state.get("bodyTextExcerpt"):
        print(f"UI excerpt       : {ui_state.get('bodyTextExcerpt')[:180]}")
    print(f"Resource count   : {len(resources)} shopee resources terlihat")
    for row in resources[:6]:
        print(
            "Resource         : "
            f"{row.get('initiatorType') or 'unknown'} | "
            f"{row.get('host')}{row.get('path')}"
        )
    for call in verification_calls:
        print(
            "Verify call      : "
            f"{call.get('name')} | status={call.get('status')} | "
            f"errorCode={call.get('errorCode')} | "
            f"merchantName={call.get('merchantName') or ''} | "
            f"merchantCount={call.get('merchantCount')}"
        )


def run() -> int:
    args = parse_args()
    session_file_path = browser.DATA_DIR / f"session_{args.username}.json"
    browser.set_session_file(session_file_path)
    vibium_artifact_root = (
        Path(args.vibium_artifact_dir).resolve()
        if args.vibium_artifact_dir
        else Path(tempfile.mkdtemp(prefix="vibium-switch-xhr-"))
    )
    vibium_artifact_root.mkdir(parents=True, exist_ok=True)

    print_title("ANALISIS KONTRAK XHR SWITCH MERCHANT")
    print("1. Harus reach dashboard dulu agar sesi Chrome profile dan cookie partner aktif.")
    print("2. Merchant list diambil dari XHR MerchantDetect, bukan dari data hardcode.")
    print("3. Payload SwitchMerchant memakai staffTobUid dari MerchantDetect, bukan merchantId.")
    print("4. Hasil SwitchMerchant perlu diverifikasi lagi ke dashboard aktif, bukan hanya status 200.")
    print("5. Layer Vibium dipakai read-only untuk cross-check state UI dan struktur network.")
    print(f"\nAccount username  : {args.username}")
    print(f"Session file path : {session_file_path}")
    print(f"Vibium artifacts  : {vibium_artifact_root}")

    session = browser.get_session(
        username=args.username,
        headless=args.headless,
        close_browser=False,
        interactive=False,
    )
    if not session or not session.get("driver"):
        print("\n❌ Gagal reach dashboard lewat core/browser.py.")
        return 1

    driver = session["driver"]
    original_merchant = None
    switched = False

    try:
        driver.get(browser.PARTNER_DASHBOARD)
        wait_for_dashboard(driver)
        time.sleep(2)

        print_title("STATE AWAL DASHBOARD")
        state_before = verify_current_state(driver, timezone=args.timezone)
        if not state_before["user_data"] and not state_before["ui_name"]:
            driver.get(browser.PARTNER_DASHBOARD)
            wait_for_dashboard(driver)
            time.sleep(3)
            state_before = verify_current_state(driver, timezone=args.timezone)
        user_before = state_before["user_data"]
        original_merchant = {
            "merchantName": user_before.get("merchantName"),
            "merchantId": str(user_before.get("merchantId") or ""),
            "storeId": str(user_before.get("store_id") or ""),
            "tobUserId": str(user_before.get("tobUserId") or ""),
        }
        print(f"Current URL      : {driver.current_url}")
        print(f"Cookie token     : {short_token(state_before['cookie_token'])}")
        print(f"UI merchant      : {state_before['ui_name'] or '<tidak terbaca>'}")
        print(
            "API merchant     : "
            f"{original_merchant['merchantName']} | "
            f"merchantId={original_merchant['merchantId']} | "
            f"tobUserId={original_merchant['tobUserId']} | "
            f"storeId={original_merchant['storeId']}"
        )
        if args.skip_vibium:
            print("\nVibium verification dilewati via flag --skip-vibium.")
        else:
            vibium_before = run_vibium_verification(
                driver,
                stage_name="before-switch",
                timezone=args.timezone,
                artifact_root=vibium_artifact_root,
                dashboard_url=driver.current_url,
            )
            print_vibium_summary("BEFORE SWITCH", vibium_before)

        print_title("XHR MERCHANTDETECT")
        ui_trigger_result = trigger_merchant_detect_via_browser_ui(driver)
        print(
            "UI trigger       : "
            f"helper_ok={ui_trigger_result.get('helper_ok')} | "
            f"detect_triggered={ui_trigger_result.get('detect_triggered')} | "
            f"selector_visible={ui_trigger_result.get('selector_visible')} | "
            f"resource_count={ui_trigger_result.get('before_count')}->{ui_trigger_result.get('after_count')}"
        )
        selector_state = ui_trigger_result.get("selector_state") or {}
        if selector_state.get("merchantTexts"):
            print(
                "Selector sample  : "
                f"{', '.join((selector_state.get('merchantTexts') or [])[:4])}"
            )
        elif selector_state.get("bodyExcerpt"):
            print(f"Selector excerpt : {selector_state.get('bodyExcerpt')[:180]}")

        merchant_detect_token = (
            ui_trigger_result.get("cookie_token")
            or state_before["cookie_token"]
            or get_cookie_token(driver)
        )
        merchants = get_merchant_list(
            driver,
            token=merchant_detect_token,
            timezone=args.timezone,
        )
        if not merchants:
            print("❌ MerchantDetect tidak mengembalikan merchant list.")
            return 1

        print(f"Total merchants  : {len(merchants)}")
        current_flags = [
            merchant for merchant in merchants if merchant.get("isCurrentLoginUser")
        ]
        if current_flags:
            print(f"Current flag row : {summarize_merchant(current_flags[0])}")
            if not original_merchant["merchantId"]:
                current_flag = current_flags[0]
                original_merchant["merchantName"] = current_flag.get("merchantName")
                original_merchant["merchantId"] = str(current_flag.get("merchantId") or "")
                original_merchant["tobUserId"] = str(current_flag.get("staffTobUid") or "")
        else:
            print("Current flag row : <tidak ada isCurrentLoginUser=true>")

        target = choose_target_merchant(
            merchants,
            current_merchant_id=original_merchant["merchantId"],
            target_name=args.target_merchant,
            target_uid=args.target_uid,
        )
        print(f"Target merchant  : {summarize_merchant(target)}")

        print_title("XHR SWITCHMERCHANT")
        switch_result = switch_merchant(
            driver,
            current_token=state_before["cookie_token"],
            target_tob_uid=str(target.get("staffTobUid") or ""),
            timezone=args.timezone,
        )
        switch_body = switch_result.get("response") or {}
        switch_data = switch_body.get("data") or {}
        print(f"XHR status       : {switch_result.get('status')}")
        print(f"XHR ok           : {switch_result.get('ok')}")
        print(f"Cookie token now : {short_token(switch_result.get('currentToken') or '')}")
        if "errorCode" in switch_body or "errorMsg" in switch_body:
            print(
                "Switch gateway   : "
                f"errorCode={switch_body.get('errorCode')} | "
                f"errorMsg={switch_body.get('errorMsg') or ''}"
            )
        print(
            "Switch response  : "
            f"target_tob_uid={switch_data.get('target_tob_uid')} | "
            f"target_tob_nonce={short_token(str(switch_data.get('target_tob_nonce') or ''))} | "
            f"target_tob_token={short_token(str(switch_data.get('target_tob_token') or ''))}"
        )
        if not switch_data:
            print(f"Switch raw body  : {json.dumps(switch_body, ensure_ascii=True)[:800]}")

        time.sleep(2)
        driver.get(browser.PARTNER_DASHBOARD)
        wait_for_dashboard(driver)
        time.sleep(3)

        print_title("VERIFIKASI PASCA SWITCH")
        state_after = verify_current_state(driver, timezone=args.timezone)
        if not state_after["user_data"] and not state_after["ui_name"]:
            driver.get(browser.PARTNER_DASHBOARD)
            wait_for_dashboard(driver)
            time.sleep(3)
            state_after = verify_current_state(driver, timezone=args.timezone)
        user_after = state_after["user_data"]
        print(f"Cookie token     : {short_token(state_after['cookie_token'])}")
        print(f"UI merchant      : {state_after['ui_name'] or '<tidak terbaca>'}")
        print(
            "API merchant     : "
            f"{user_after.get('merchantName')} | "
            f"merchantId={user_after.get('merchantId')} | "
            f"tobUserId={user_after.get('tobUserId')} | "
            f"storeId={user_after.get('store_id')}"
        )
        if not args.skip_vibium:
            vibium_after = run_vibium_verification(
                driver,
                stage_name="after-switch",
                timezone=args.timezone,
                artifact_root=vibium_artifact_root,
                dashboard_url=driver.current_url,
            )
            print_vibium_summary("AFTER SWITCH", vibium_after)

        switched = (
            str(user_after.get("merchantId") or "") == str(target.get("merchantId") or "")
            or str(user_after.get("merchantName") or "").strip().lower()
            == str(target.get("merchantName") or "").strip().lower()
        )

        if switched:
            print("\n✅ XHR switch berhasil mengubah merchant aktif di dashboard.")
        else:
            print("\n⚠️ XHR SwitchMerchant mengembalikan response sukses, tetapi merchant aktif belum berubah.")
            target_token = str(switch_data.get("target_tob_token") or "")
            target_nonce = str(switch_data.get("target_tob_nonce") or "")
            target_uid = str(switch_data.get("target_tob_uid") or "")
            if target_token:
                print("\nMenjalankan diagnostic call memakai material hasil SwitchMerchant...")
                diagnostic = get_user_info(
                    driver,
                    token=target_token,
                    timezone=args.timezone,
                    extra_headers={
                        "x-merchant-tob-nonce": target_nonce,
                        "x-merchant-tob-userid": target_uid,
                    },
                )
                diag_body = diagnostic.get("response") or {}
                print(f"Diagnostic status: {diagnostic.get('status')}")
                print(f"Diagnostic body  : {json.dumps(diag_body, ensure_ascii=True)[:800]}")

        should_restore = bool(
            original_merchant
            and switched
            and not args.no_restore
            and str(original_merchant.get("merchantName") or "").strip()
        )
        if should_restore:
            print_title("RESTORE MERCHANT ASAL")
            restore_token = get_cookie_token(driver)
            restore_result = switch_merchant(
                driver,
                current_token=restore_token,
                target_tob_uid=original_merchant["tobUserId"],
                timezone=args.timezone,
            )
            print(f"Restore XHR status: {restore_result.get('status')}")
            time.sleep(2)
            driver.get(browser.PARTNER_DASHBOARD)
            wait_for_dashboard(driver)
            time.sleep(3)
            restored_state = verify_current_state(driver, timezone=args.timezone)
            restored_data = restored_state["user_data"]
            restored_ok = (
                str(restored_data.get("merchantId") or "") == original_merchant["merchantId"]
                or str(restored_data.get("merchantName") or "").strip().lower()
                == str(original_merchant.get("merchantName") or "").strip().lower()
            )
            print(
                "Restored merchant : "
                f"{restored_data.get('merchantName')} | merchantId={restored_data.get('merchantId')}"
            )
            print(f"Restore result    : {'SUCCESS' if restored_ok else 'FAILED'}")

        return 0 if switched else 2
    finally:
        if args.keep_browser:
            print("\nBrowser dibiarkan tetap terbuka sesuai flag --keep-browser.")
        else:
            browser.cleanup_driver_process(driver)


if __name__ == "__main__":
    raise SystemExit(run())
