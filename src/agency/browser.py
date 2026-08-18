"""
src/agency/browser.py
=====================
Direct, exact 1:1 copy of core/browser.py configured for Agency Churn Bot.

Configured specifically to use:
  - Chrome Profile: src/data/chrome_profile (profile-directory: shopee_profile)
  - Session File:   src/data/session.json
  - Credentials:    src/data/credentials allvbadmin.json
  - Default Account: allvbadmin
"""

import os
import sys
import json
import time
import random
import signal
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

log = logging.getLogger("agency.browser")


def send_discord_error(platform: str, merchant: str, error_type: str, message: str, phone: str = None):
    try:
        from core.notifier import send_discord_error as _send
        _send(platform, merchant, error_type, message, phone)
    except Exception:
        log.warning(f"⚠️ [DISCORD ERROR] {platform} | {merchant} | {error_type}: {message}")


def send_discord_success(platform: str, merchant: str, action: str, message: str):
    try:
        from core.notifier import send_discord_success as _send
        _send(platform, merchant, action, message)
    except Exception:
        log.info(f"✅ [DISCORD SUCCESS] {platform} | {merchant} | {action}: {message}")


def cleanup_driver_process(driver) -> None:
    """
    Safely closes a Selenium WebDriver instance.
    If driver.quit() hangs or fails, forcibly terminates the specific ChromeDriver
    process (PID) bound to this driver instance to prevent zombie processes and memory leaks.
    """
    if driver is None:
        return

    pid = None
    try:
        if hasattr(driver, "service") and hasattr(driver.service, "process") and driver.service.process:
            pid = driver.service.process.pid
    except Exception:
        pass

    try:
        log.info(f"🧹 [BROWSER CLEANUP] Closing Selenium driver instance (PID: {pid})...")
        driver.quit()
        log.info("✅ [BROWSER CLEANUP] Selenium driver closed successfully.")
    except Exception as quit_err:
        log.warning(f"⚠️ [BROWSER CLEANUP] driver.quit() exception: {quit_err}. Forcibly cleaning PID {pid}...")
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                log.info(f"  👉 Sent SIGTERM to ChromeDriver process PID {pid}.")
            except Exception as kill_err:
                log.warning(f"  ⚠️ Could not kill PID {pid}: {kill_err}")


# ── Constants & Dynamic Paths ──────────────────────────────────────────────────
BASE_DIR         = Path(__file__).resolve().parent.parent
DATA_DIR         = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_FILE = DATA_DIR / "credentials allvbadmin.json"
PROJECT_ROOT     = BASE_DIR.parent

_thread_local = threading.local()


def get_session_file() -> Path:
    if not hasattr(_thread_local, "session_file"):
        _thread_local.session_file = DATA_DIR / "session.json"
    return _thread_local.session_file


def get_otp_code(username: str, phone: str) -> str:
    if sys.stdin.isatty():
        try:
            return input(f"🔑 Masukkan 6-digit OTP (atau tekan Enter jika Anda mengisinya langsung di browser): ").strip()
        except EOFError:
            log.warning("⚠️ [OTP] Stdin reached EOF. Waiting 10 seconds...")
            time.sleep(10)
            return ""
    log.warning("⚠️ [OTP] Stdin is not a TTY (running in background/Docker). Cannot prompt for OTP via terminal. Waiting 10 seconds...")
    time.sleep(10)
    return ""


def set_session_file(val):
    _thread_local.session_file = Path(val)


class ThreadLocalSessionFileProxy:
    def __getattr__(self, name):
        return getattr(get_session_file(), name)

    def __str__(self):
        return str(get_session_file())

    def __fspath__(self):
        return str(get_session_file())

    def __eq__(self, other):
        return get_session_file() == other


SESSION_FILE = ThreadLocalSessionFileProxy()


class ModuleWrapper(sys.modules[__name__].__class__):
    @property
    def SESSION_FILE(self):
        return get_session_file()

    @SESSION_FILE.setter
    def SESSION_FILE(self, value):
        set_session_file(value)


sys.modules[__name__].__class__ = ModuleWrapper

PARTNER_DASHBOARD     = "https://partner.shopee.co.id/food/dashboard"
TOKEN_TRIGGER_PAGE    = "https://partner.shopee.co.id/settings/shopee-food/business-hours-settings"
MERCHANT_SELECTOR_URL = "https://partner.shopee.co.id/food/dashboard"
VALIDATE_URL          = "https://api.partner.shopee.co.id/nb/mss/web-api/PartnerAccountServer/GetUserInfo"
SHOPEE_IMG_BASE       = "https://down-id.img.susercontent.com/file"
LOGOUT_KEYWORDS       = ["log out", "logout", "keluar", "sign out", "signout"]


# ── Helpers ────────────────────────────────────────────────────────────────────

def human_like_typing(element, text: str):
    element.send_keys(text)


def _is_safe_to_click(element) -> bool:
    try:
        text = (element.text or "").strip().lower()
        if not text:
            text = (element.get_attribute("innerText") or "").strip().lower()
        return not any(kw in text for kw in LOGOUT_KEYWORDS)
    except Exception:
        return True


def _detect_and_recover_logout(driver) -> bool:
    current = driver.current_url.lower()
    logged_out = (
        "/login" in current
        or "/authenticate/login" in current
        or "about:blank" in current
    )
    if not logged_out:
        return False

    log.warning("⚠️  [LOGOUT-RECOVERY] Accidental logout detected! Trying to recover via Chrome profile...")
    try:
        driver.get(PARTNER_DASHBOARD)
        time.sleep(5)
        recovered_url = driver.current_url.lower()
        if "dashboard" in recovered_url or "merchant-selector" in recovered_url:
            log.info("✅ [LOGOUT-RECOVERY] Recovered without OTP — Chrome profile cookies still valid.")
            return True
    except Exception as err:
        log.warning(f"⚠️  [LOGOUT-RECOVERY] Recovery attempt failed: {err}")

    log.warning("⚠️  [LOGOUT-RECOVERY] Could not recover automatically — full re-login may be needed.")
    return False


def _handle_onboarding_invitation(driver, timeout=15) -> bool:
    try:
        current_url = driver.current_url.lower()
        if "onboarding" not in current_url:
            return False

        page_info = driver.execute_script("""
            var allButtons = Array.from(document.querySelectorAll('button'));
            var gabungBtn = null;
            for (var btn of allButtons) {
                var text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                if (text.includes('gabung')) { gabungBtn = btn; break; }
            }
            var hasListItems = document.querySelectorAll(
                '.listItem, .merchant-item, li[class*="item"]'
            ).length > 0;
            return { hasGabung: !!gabungBtn, hasList: hasListItems };
        """)

        if not page_info or not page_info.get("hasGabung") or page_info.get("hasList"):
            return False

        log.info("📍 [ONBOARDING] Merchant invitation page detected. Clicking 'Gabung dengan Merchant'...")

        btn_xpath = "//button[contains(., 'Gabung dengan Merchant') or contains(., 'Gabung')]"
        gabung_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, btn_xpath))
        )
        gabung_btn.click()
        log.info("  👉 Clicked 'Gabung dengan Merchant' button.")
        time.sleep(3)

        for _ in range(20):
            new_url = driver.current_url.lower()
            if "/food/dashboard" in new_url:
                log.info("  ✅ [ONBOARDING] Invitation accepted → Dashboard loaded.")
                return True
            if new_url != current_url:
                log.info(f"  ✅ [ONBOARDING] Invitation accepted → Redirected to: {driver.current_url}")
                return True
            time.sleep(1)

        log.warning("  ⚠️ [ONBOARDING] Gabung clicked but no redirect detected within 20s.")
        return True

    except Exception as e:
        log.warning(f"  ⚠️ [ONBOARDING] Failed to handle invitation page: {e}")
        return False


def _deliberate_logout_and_relogin(
    driver,
    username: str = None,
    password: str = None,
    phone: str = None,
) -> bool:
    log.info("🔄 [LOGOUT-RELOGIN] Initiating deliberate logout for clean session recovery...")
    try:
        url_now = driver.current_url.lower()
        if "login" in url_now or "authenticate" in url_now:
            log.info("  🛡️ Browser is already on the login/authenticate page. Skipping UI dropdown logout.")
            log.info("  🌐 Attempting direct login preserving all cookies/storage to leverage device trust...")
        if not (username and password) and not phone:
            username = "allvbadmin"
            if CREDENTIALS_FILE.exists():
                try:
                    cdata = json.loads(CREDENTIALS_FILE.read_text())
                    for k, v in cdata.items():
                        if isinstance(v, dict) and v.get("password"):
                            username = v.get("username") or "allvbadmin"
                            password = v.get("password")
                            break
                except Exception:
                    pass
            wait = WebDriverWait(driver, 30)
            login_ok = _perform_login(driver, wait, username=username, password=password, phone=phone)
            if login_ok:
                log.info("  ⏳ Menunggu pengalihan halaman setelah login recovery...")
                redirected_ok = False
                for _ in range(30):
                    curr_url = driver.current_url.lower()
                    if "onboarding" in curr_url or "merchant-selector" in curr_url or "dashboard" in curr_url:
                        redirected_ok = True
                        break
                    time.sleep(0.5)
                if redirected_ok:
                    log.info("  ✅ [LOGOUT-RELOGIN] Credential login succeeded directly from login page!")
                    return True
            return False

        if "/food/" not in driver.current_url and "/settings/" not in driver.current_url:
            driver.get(PARTNER_DASHBOARD)
            time.sleep(3)

        profile_clicked = False
        for attempt in range(3):
            driver.execute_script("""
                document.querySelectorAll('.ant-notification, .ant-modal, .ant-notification-notice, .ant-message').forEach(el => el.remove());
            """)
            profile_el = driver.execute_script("""
                var profileEl = null;
                for (var sel of ['.merchantName', '.user-info', '.ant-dropdown-trigger', '.ant-dropdown-link']) {
                    var el = document.querySelector(sel);
                    if (el && el.offsetHeight > 0) { profileEl = el; break; }
                }
                if (!profileEl) {
                    var elements = Array.from(document.querySelectorAll('span, p, div, li, a'));
                    for (var el of elements) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Admin:') && text.length < 30 && el.offsetHeight > 0) { profileEl = el; break; }
                    }
                }
                if (!profileEl) {
                    var triggers = Array.from(document.querySelectorAll('.ant-dropdown-trigger, .ant-dropdown-link'));
                    if (triggers.length > 0) profileEl = triggers[triggers.length - 1];
                }
                return profileEl;
            """)

            if profile_el:
                log.info(f"  📍 Found profile menu element (Attempt {attempt+1}). Dispatching JS click...")
                driver.execute_script("""
                    var el = arguments[0];
                    var ev1 = new MouseEvent('mouseover', { bubbles: true, cancelable: true });
                    var ev2 = new MouseEvent('mouseenter', { bubbles: true, cancelable: true });
                    var ev3 = new MouseEvent('mousedown', { bubbles: true, cancelable: true });
                    var ev4 = new MouseEvent('click', { bubbles: true, cancelable: true });
                    var ev5 = new MouseEvent('mouseup', { bubbles: true, cancelable: true });
                    el.dispatchEvent(ev1); el.dispatchEvent(ev2); el.dispatchEvent(ev3); el.dispatchEvent(ev4); el.dispatchEvent(ev5);
                """, profile_el)
                time.sleep(1.5)

                has_dropdown = driver.execute_script("""
                    var targets = ['log out', 'logout', 'keluar'];
                    var candidates = Array.from(document.querySelectorAll('li, span, div, a'));
                    for (var el of candidates) {
                        var rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) continue;
                        if (el.closest('.ant-dropdown-hidden, [style*="display: none"], [style*="visibility: hidden"]')) continue;
                        var text = (el.innerText || '').trim().toLowerCase();
                        if (targets.some(function(k){ return text.includes(k); })) return true;
                    }
                    return false;
                """)

                if not has_dropdown:
                    try:
                        actions = ActionChains(driver)
                        actions.move_to_element(profile_el).perform()
                        time.sleep(0.5)
                        actions.click(profile_el).perform()
                        time.sleep(1.5)
                        has_dropdown = driver.execute_script("""
                            var targets = ['log out', 'logout', 'keluar'];
                            var candidates = Array.from(document.querySelectorAll('li, span, div, a'));
                            for (var el of candidates) {
                                var rect = el.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) continue;
                                if (el.closest('.ant-dropdown-hidden, [style*="display: none"], [style*="visibility: hidden"]')) continue;
                                var text = (el.innerText || '').trim().toLowerCase();
                                if (targets.some(function(k){ return text.includes(k); })) return true;
                            }
                            return false;
                        """)
                    except Exception as e:
                        log.warning(f"  ⚠️ ActionChains failed: {e}")

                if has_dropdown:
                    log.info("  ✅ Dropdown is now visible.")
                    profile_clicked = True
                    break
            time.sleep(1.5)

        if not profile_clicked:
            log.warning("  ⚠️ Profile element or dropdown could not be opened.")
            return False

        logout_el = driver.execute_script("""
            var targets = ['log out', 'logout', 'keluar'];
            var candidates = Array.from(document.querySelectorAll(
                'li.ant-menu-item, li[role="menuitem"], .ant-dropdown-menu-item, [class*="menu-item"], span, div, a'
            ));
            for (var el of candidates) {
                var rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                if (el.closest('.ant-dropdown-hidden, [style*="display: none"], [style*="visibility: hidden"]')) continue;
                var text = (el.innerText || '').trim().toLowerCase();
                if (targets.some(function(k){ return text === k; })) {
                    return el.closest('li, button, a, [role="menuitem"], .ant-dropdown-menu-item') || el;
                }
            }
            return null;
        """)

        if not logout_el:
            log.warning("  ⚠️ 'Log Out' menu item not found in dropdown.")
            return False

        try:
            logout_el.click()
        except Exception:
            try:
                ActionChains(driver).move_to_element(logout_el).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", logout_el)

        time.sleep(1.5)

        confirm_clicked = False
        for confirm_attempt in range(5):
            confirm_el = driver.execute_script("""
                var targets = ['log out', 'logout', 'keluar'];
                var modal = document.querySelector('.ant-modal-content, .ant-modal, .ant-dialog, .ant-modal-wrap');
                if (!modal) return null;
                var candidates = Array.from(modal.querySelectorAll('button, .ant-btn, [role="button"]'));
                for (var btn of candidates) {
                    var rect = btn.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    var text = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (targets.some(function(k){ return text === k || text === ('confirm ' + k); })) {
                        return btn.closest('button, [role="button"], a, .ant-btn') || btn;
                    }
                }
                return null;
            """)

            if confirm_el:
                try:
                    confirm_el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", confirm_el)

                time.sleep(2)
                modal_present = driver.execute_script("""
                    var modal = document.querySelector('.ant-modal-content, .ant-modal, .ant-dialog, .ant-modal-wrap');
                    return !!(modal && modal.offsetHeight > 0);
                """)
                if not modal_present:
                    log.info("  ✅ Modal disappeared. Logout confirmed.")
                    confirm_clicked = True
                    break
            time.sleep(1.5)

        if not confirm_clicked:
            log.warning("  ⚠️ UI logout failed.")
            return False

        log.info("  ✅ Logout confirmed. Waiting for login page...")
        time.sleep(3)

        driver.get(PARTNER_DASHBOARD)
        time.sleep(5)
        url_now = driver.current_url.lower()
        if "dashboard" in url_now or "merchant-selector" in url_now or "onboarding" in url_now:
            log.info("  ✅ [LOGOUT-RELOGIN] Auto-login via Chrome profile succeeded!")
            return True

        if "login" not in driver.current_url.lower() and "authenticate" not in driver.current_url.lower():
            driver.get("https://partner.shopee.co.id/login")
            time.sleep(4)

        wait = WebDriverWait(driver, 30)
        login_ok = _perform_login(driver, wait, username=username, password=password, phone=phone)
        if not login_ok:
            return False

        time.sleep(3)
        for _ in range(10):
            url_after = driver.current_url.lower()
            if "dashboard" in url_after or "merchant-selector" in url_after or "onboarding" in url_after:
                return True
            time.sleep(1)

        return False

    except Exception as e:
        log.error(f"  ❌ [LOGOUT-RELOGIN] Failed: {e}")
        return False


def build_img_url(img_id: str) -> str:
    if not img_id:
        return ""
    return f"{SHOPEE_IMG_BASE}/{img_id}"


# ── Session Persistence ────────────────────────────────────────────────────────

def save_session(tob_token: str, entity_id: str, extra_cookies: dict = None):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "shopee_tob_token": tob_token,
        "shopee_tob_entity_id": entity_id,
        "saved_at": datetime.now().isoformat(),
        "extra_cookies": extra_cookies or {},
    }
    SESSION_FILE.write_text(json.dumps(payload, indent=2))
    log.debug(f"✅ Session saved to {SESSION_FILE}")


def load_session() -> dict | None:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text())
        if data.get("shopee_tob_token"):
            log.info(f"📂 [SESSION] Found cached session (saved at {data.get('saved_at')})")
            return data
    except Exception:
        pass
    return None


def validate_session(tob_token: str, entity_id: str) -> bool:
    headers = {
        "Cookie": f"shopee_tob_entity_id={entity_id}; shopee_tob_token={tob_token}",
        "x-merchant-token": tob_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        resp = requests.post(VALIDATE_URL, json={}, headers=headers, timeout=8)
        data = resp.json()
        if data.get("message") == "success" or data.get("code") == 0:
            log.info("✅ [SESSION] Saved session is still valid.")
            return True
    except Exception:
        pass
    return False


# ── Token Extraction ───────────────────────────────────────────────────────────

def extract_tokens_from_driver(driver) -> tuple:
    tob_token = None
    entity_id = None
    for c in driver.get_cookies():
        name = c["name"]
        val = c["value"]
        if name == "shopee_tob_token":
            tob_token = val
        elif name.lower() in ["shopee_tob_entity_id", "shopee_foody_mid", "x-merchant-id", "spc_merchant_id", "merchant_id", "shopid", "shop_id"]:
            if val and not entity_id:
                entity_id = val

    if not entity_id:
        try:
            api_js = """
            var done = arguments[arguments.length - 1];
            let token = document.cookie.split('; ').find(row => row.startsWith('shopee_tob_token='))?.split('=')[1];
            fetch('https://api.partner.shopee.co.id/nb/mss/web-api/PartnerAccountServer/GetUserInfo', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-merchant-token': token || ''
                },
                body: '{}',
                credentials: 'include'
            })
            .then(r => r.json())
            .then(j => done(j.data ? j.data.merchantId : null))
            .catch(() => done(null));
            """
            entity_id = driver.execute_async_script(api_js)
        except Exception:
            pass

    return tob_token, (str(entity_id).strip() if entity_id else None)


def get_all_cookies_dict(driver) -> dict:
    return {c["name"]: c["value"] for c in driver.get_cookies()}


def _trigger_and_extract_tokens(driver) -> tuple:
    try:
        try:
            driver.delete_cookie("shopee_tob_token")
        except Exception:
            pass
        driver.get(TOKEN_TRIGGER_PAGE)
        for _ in range(10):
            tob_token, entity_id = extract_tokens_from_driver(driver)
            if tob_token:
                return tob_token, entity_id
            time.sleep(1)
    except Exception:
        pass
    return extract_tokens_from_driver(driver)


# ── Driver Initialization ──────────────────────────────────────────────────────

def is_headless_enabled() -> bool:
    val = os.getenv("HEADLESS", "false").strip().lower()
    return val in ("true", "1", "yes", "on")


def _init_driver(headless: bool = None):
    if headless is None:
        headless = is_headless_enabled()
    options = Options()
    options.page_load_strategy = "eager"
    options.add_argument("--log-level=3")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-component-update")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
    else:
        options.add_argument("--start-maximized")

    profile_dir = DATA_DIR / "chrome_profile"
    options.add_argument(f"--user-data-dir={profile_dir.resolve()}")
    profile_name = "shopee_profile" if (profile_dir / "shopee_profile").exists() else "Default"
    options.add_argument(f"--profile-directory={profile_name}")
    log.info(f"📂 [CHROME PROFILE] Loaded Profile Directory: {profile_dir} ({profile_name})")

    for lock_name in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_file = profile_dir / lock_name
        if lock_file.exists() or lock_file.is_symlink():
            try:
                lock_file.unlink(missing_ok=True)
                log.info(f"🧹 Removed Chrome lock at {lock_file}")
            except Exception as e:
                log.warning(f"⚠️ Failed to remove lock {lock_name}: {e}")

    chromedriver_bin = os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    try:
        if Path(chromedriver_bin).exists():
            log.info(f"🔧 Using system ChromeDriver binary: {chromedriver_bin}")
            driver = webdriver.Chrome(service=Service(chromedriver_bin), options=options)
        else:
            driver = webdriver.Chrome(options=options)
    except Exception as e:
        log.warning(f"⚠️ Native Chrome init failed: {e}. Trying ChromeDriverManager fallback...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.set_page_load_timeout(60)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception:
        pass
    return driver


init_agency_driver = _init_driver


def _load_agency_credentials() -> Tuple[str, str, str]:
    if CREDENTIALS_FILE.exists():
        try:
            cdata = json.loads(CREDENTIALS_FILE.read_text())
            for key, val in cdata.items():
                if isinstance(val, dict):
                    user = val.get("username") or "allvbadmin"
                    pwd = val.get("password")
                    phone = val.get("phone", "")
                    if pwd:
                        log.info(f"🔑 [AUTH] Auto-loaded credentials for '{user}' from {CREDENTIALS_FILE}")
                        return user, pwd, phone
        except Exception as e:
            log.error(f"Error reading agency credentials from {CREDENTIALS_FILE}: {e}")
    return "allvbadmin", "Master!00!", ""


# ── Login Logic ────────────────────────────────────────────────────────────────

def _perform_login(driver, wait, username: str = None, password: str = None, phone: str = None, is_retry: bool = False) -> bool:
    log.info("➡️  [AUTH] Starting login sequence...")
    if not (username and password):
        c_user, c_pass, c_phone = _load_agency_credentials()
        username = username or c_user
        password = password or c_pass
        phone = phone or c_phone
    if username == "auto7313":
        username = "allvbadmin"

    if not phone and (not username or not password):
        raise Exception(f"Shopee credentials are not configured! Please configure them in '{CREDENTIALS_FILE}'.")

    use_phone = phone and not (username and password)
    if use_phone:
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Log in dengan no. HP')]"))).click()
            time.sleep(1)
        except Exception:
            pass
        phone_input = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='tel']")))
        phone_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
        human_like_typing(phone_input, phone)
        wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Selanjutnya')]"))).click()
    else:
        time.sleep(2)
        user_input = None
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            for inp in inputs:
                p = (inp.get_attribute("placeholder") or "").lower()
                n = (inp.get_attribute("name") or "").lower()
                t = (inp.get_attribute("type") or "").lower()
                if inp.is_displayed() and (t == "text" or "user" in n or "phone" in n or "handphone" in p or "username" in p):
                    user_input = inp
                    break
        except Exception:
            pass

        if not user_input:
            for sel in ["input[name='userName']", "input[placeholder*='handphone']", "input[placeholder*='Username']", "input[type='text']"]:
                try:
                    el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                    if el.is_displayed():
                        user_input = el
                        break
                except Exception:
                    continue

        if not user_input:
            log.error(f"❌ Failed to find Username field. URL: {driver.current_url}")
            raise Exception("Could not find Username input field")

        pass_input = None
        for sel in ["input[type='password']", "input[placeholder='Password']"]:
            try:
                el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                if el.is_displayed():
                    pass_input = el
                    break
            except Exception:
                continue

        if not pass_input:
            raise Exception("Could not find Password input field")

        user_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
        human_like_typing(user_input, username)
        pass_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
        human_like_typing(pass_input, password)

        login_btn = None
        for btn_sel in ["//button[contains(., 'Masuk') or contains(., 'Log In')]", "//button[@type='submit']"]:
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, btn_sel)))
                if btn.is_displayed():
                    login_btn = btn
                    break
            except Exception:
                continue

        if login_btn:
            login_btn.click()
        else:
            raise Exception("Could not find Login button")

    time.sleep(3)
    try:
        error_texts = driver.execute_script("""
            var errs = Array.from(document.querySelectorAll('.shopee-form-item__error-message, .shopee-alert__title, .ant-message-custom-content span'));
            return errs.map(e => e.innerText).filter(t => t.length > 0);
        """)
        for err_text in error_texts:
            if "sandi" in err_text.lower() or "password" in err_text.lower() or "salah" in err_text.lower() or "nomor" in err_text.lower() or "username" in err_text.lower():
                log.error(f"❌ Login error detected: {err_text}")
                if is_retry:
                    send_discord_error("Shopee", username or phone, "WRONG_CREDENTIALS", f"Gagal login: {err_text}", phone)
                return False
            if "blokir" in err_text.lower() or "blocked" in err_text.lower() or "dibatasi" in err_text.lower():
                log.error(f"❌ Account block detected: {err_text}")
                if is_retry:
                    send_discord_error("Shopee", username or phone, "BLOCKED_ACCOUNT", f"Akun dibatasi/diblokir: {err_text}", phone)
                return False
    except Exception:
        pass

    log.debug("  ⏳ Waiting for post-login redirect or OTP...")
    start_wait = time.time()
    while time.time() - start_wait < 30:
        current_url = driver.current_url.lower()
        if "onboarding" in current_url or "merchant-selector" in current_url or "dashboard" in current_url:
            break
        try:
            otp_input = None
            for sel in ["input.shopee-otp-input__input", ".shopee-otp-input input", "input[maxlength='6']"]:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        otp_input = el
                        break
                if otp_input:
                    break

            is_verification_page = driver.execute_script("""
                var texts = [
                    "pilih cara verifikasi", "select verification method",
                    "pilih metode verifikasi", "verify to log in",
                    "verifikasi untuk masuk", "masukkan kode", "enter code",
                    "kode verifikasi", "verification code"
                ];
                var bodyText = (document.body.innerText || "").toLowerCase();
                return texts.some(function(t) { return bodyText.includes(t); });
            """)

        except Exception:
            pass

        try:
            btn_el = driver.find_element(By.XPATH, "//button[contains(., 'Lanjutkan') or contains(., 'Continue')] | //*[text()='Lanjutkan' or text()='Continue']")
            if btn_el.is_displayed():
                log.info("👉 [AUTH] Menemukan tombol 'Lanjutkan', mencoba mengklik...")
                try:
                    btn_el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", btn_el)
                time.sleep(2)
        except Exception:
            pass

        time.sleep(1)

    current_url = driver.current_url.lower()
    if "onboarding" not in current_url and "merchant-selector" not in current_url and "dashboard" not in current_url:
        log.error(f"❌ [AUTH] Login did not redirect to dashboard and is still on: {current_url}. Aborting.")
        return False

    return True


class MerchantNotFoundError(Exception):
    """Raised when a merchant is genuinely not found in the Shopee account dropdown after 3 scan attempts."""
    pass


def auto_switch_merchant(driver, target_name, is_retry=False):
    log.info(f"🔄 [MERCHANT] Switching to: {target_name}...")
    try:
        driver.execute_script("document.querySelectorAll('.ant-spin, [class*=\"loading\"], .shopee-loading').forEach(el => el.remove());")

        wait = WebDriverWait(driver, 15)

        js_selector_click = """
            var listItems = document.querySelectorAll('.listItem, .merchant-item, li[class*="item"]');
            for (var i = 0; i < listItems.length; i++) {
                var el = listItems[i];
                var text = (el.innerText || el.textContent || "").trim();
                if (text.length > 0) {
                    el.scrollIntoView({block: 'center'});
                    el.click();
                    return true;
                }
            }
            return false;
        """

        current_url = driver.current_url
        if "onboarding" in current_url or "merchant-selector" in current_url:
            log.debug(f"  📍 Detected Merchant Selector page (URL: {current_url}). Attempting to bypass...")
            time.sleep(3)

            for attempt in range(5):
                if driver.execute_script(js_selector_click):
                    log.debug("  ✅ Triggered selection on selector page. Waiting for dashboard or invitation...")
                    try:
                        pre_click_url = driver.current_url

                        def _page_transitioned(d):
                            cur = d.current_url
                            if "/food/dashboard" in cur or cur != pre_click_url:
                                return True
                            try:
                                btns = d.find_elements(By.XPATH, "//button[contains(., 'Gabung dengan Merchant') or contains(., 'Gabung')]")
                                if any(b.is_displayed() for b in btns):
                                    return True
                            except Exception:
                                pass
                            return False

                        WebDriverWait(driver, 30).until(_page_transitioned)
                        time.sleep(3)

                        if "/food/dashboard" not in driver.current_url:
                            if _handle_onboarding_invitation(driver):
                                time.sleep(3)

                        if "/food/dashboard" in driver.current_url:
                            try:
                                actual_name = driver.find_element(By.CSS_SELECTOR, ".merchantName").text.strip().lower()
                                if target_name.lower() in actual_name:
                                    return True
                                else:
                                    log.info(f"  📍 Landed on dashboard as '{actual_name}'. Will switch to target now.")
                                    break
                            except Exception:
                                break
                    except Exception:
                        pass
                driver.execute_script("window.scrollBy(0, 300);")
                time.sleep(1)

            if "onboarding" in driver.current_url or "merchant-selector" in current_url:
                raise Exception("Failed to bypass Merchant Selector page")

        if "/food/dashboard" not in driver.current_url:
            driver.get(PARTNER_DASHBOARD)
            time.sleep(2)

        for switch_attempt in range(3):
            dropdown_opened = False
            try:
                actions = ActionChains(driver)
                profile_menu = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".merchantName")))
                actions.move_to_element(profile_menu).click().perform()
                time.sleep(1)

                quick_wait = WebDriverWait(driver, 3)
                try:
                    switch_trigger = quick_wait.until(EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Pilih Merchant Lain') or contains(text(), 'Switch Merchant')]")))
                    actions.move_to_element(switch_trigger).click().perform()
                    dropdown_opened = True
                    time.sleep(1)
                except Exception:
                    js_found = driver.execute_script("""
                        var spans = document.querySelectorAll('span, p, div');
                        for (var s of spans) {
                            var text = (s.innerText || '').trim();
                            if (text.includes('Pilih Merchant Lain') || text.includes('Switch Merchant')) {
                                s.click();
                                return true;
                            }
                        }
                        return false;
                    """)
                    if js_found:
                        dropdown_opened = True
                        time.sleep(1)
            except Exception as e:
                err_str = str(e)
                log.warning(f"  ⚠️ Failed to trigger merchant menu: {err_str}")
                if "TimeoutException" in err_str or "merchantName" not in driver.page_source:
                    log.warning("  ⚠️ [STALE SESSION] Elemen profil (.merchantName) tidak ditemukan. Sesi kemungkinan kedaluwarsa.")
                    return False

                if switch_attempt == 2:
                    return False
                continue

            if not dropdown_opened:
                log.warning("  ⚠️ [STALE SESSION] Dropdown profil tidak terbuka setelah klik — sesi kemungkinan kedaluwarsa.")
                return False

            js_switch_script = """
                var targetName = arguments[0].toLowerCase().trim();
                var cleanTarget = targetName.replace(/_+$/, '').trim();
                var items = document.querySelectorAll('li.ant-menu-item, li[role="menuitem"], .ant-dropdown-menu-item, [class*="menu-item"]');
                for (var i = 0; i < items.length; i++) {
                    var text = (items[i].innerText || "").toLowerCase().trim();
                    var cleanText = text.replace(/_+$/, '').trim();
                    if (text === targetName || text.includes(targetName) || cleanText === cleanTarget || (cleanTarget.length >= 3 && cleanText.includes(cleanTarget))) {
                        items[i].scrollIntoView({block: 'center'});
                        items[i].click();
                        return true;
                    }
                }
                return false;
            """

            found_target = False
            for _ in range(5):
                if driver.execute_script(js_switch_script, target_name):
                    found_target = True
                    break
                try:
                    driver.execute_script("document.querySelectorAll('.ant-dropdown-menu, ul[role=\"menu\"], .ant-popover-inner-content').forEach(el => el.scrollTop += 600);")
                except Exception:
                    pass
                time.sleep(1)

            if found_target:
                log.debug(f"  ✅ Clicked {target_name} in menu.")
            else:
                log.warning(f"  ⚠️ Nama outlet '{target_name}' tidak ditemukan di dropdown (Attempt {switch_attempt+1}/3).")
                if switch_attempt == 2:
                    msg = f"Nama outlet '{target_name}' tidak terdaftar atau belum ditambahkan (invite) di akun Shopee ini."
                    log.warning(f"⚠️ {msg}")
                    raise MerchantNotFoundError(msg)
                continue

            time.sleep(3)
            current_url = driver.current_url.lower()
            if "onboarding" in current_url:
                log.info("📍 [MERCHANT] Onboarding page detected after selecting merchant. Accepting invitation...")
                if _handle_onboarding_invitation(driver):
                    log.info("  ✅ Invitation accepted via helper.")
                    time.sleep(3)
                    if "/food/dashboard" not in driver.current_url:
                        try:
                            WebDriverWait(driver, 15).until(lambda d: "/food/dashboard" in d.current_url)
                        except Exception:
                            pass
                else:
                    log.error("❌ Failed to accept onboarding invitation.")
                    if switch_attempt == 2:
                        msg = f"Nama outlet '{target_name}' gagal menerima undangan onboarding."
                        raise MerchantNotFoundError(msg)
                    continue

            try:
                log.info(f"  ⏳ Menunggu 5 detik melihat pembaruan nama menjadi {target_name} (Attempt {switch_attempt+1}/3)...")

                clean_target = target_name.rstrip('_').strip().lower()

                def is_name_updated(d):
                    try:
                        header_name = d.find_element(By.CSS_SELECTOR, ".merchantName").text.strip().lower()
                        clean_header = header_name.rstrip('_').strip()
                        return clean_target in header_name or header_name in clean_target or clean_target in clean_header or clean_header in clean_target
                    except Exception:
                        return False

                WebDriverWait(driver, 5).until(is_name_updated)
                log.info(f"✅ [MERCHANT] Switched to: {target_name}")
                return True
            except Exception:
                log.warning(f"⚠️ [MERCHANT] UI name belum berubah ke {target_name}.")
                if switch_attempt == 2:
                    log.warning(f"❌ [MERCHANT] Gagal melakukan switch ke {target_name} setelah 3x percobaan klik.")
                    msg = f"Nama outlet '{target_name}' terkonfirmasi gagal di-switch ke header UI Shopee."
                    raise MerchantNotFoundError(msg)


    except MerchantNotFoundError:
        raise
    except Exception as e:
        log.error(f"❌ Auto-switch failed: {e}")
        return False



def _handle_merchant_selection(driver, active_id_forced=None, interactive=True):
    log.info("===========================================================================")
    try:
        active_id = active_id_forced
        if not active_id:
            _, active_id = extract_tokens_from_driver(driver)

        if active_id:
            log.info(f"📍 [MERCHANT] Active ID: {active_id}")

        all_found = {}
        all_merchants_data = {}
        try:
            api_response_path = BASE_DIR / "API" / "response.json"
            if api_response_path.exists():
                with open(api_response_path, "r") as f:
                    data = json.load(f)
                    for m in data.get("data", {}).get("selectMerchant", {}).get("merchantList", []):
                        all_merchants_data[m["merchantName"].lower()] = str(m["merchantId"])
        except Exception:
            pass

        for attempt in range(10):
            log.debug(f"  📥 Scanning for merchants (Attempt {attempt+1}/10)...")
            scan_result = driver.execute_script("""
                var results = [];
                var items = document.querySelectorAll('.listItem, .merchant-item, li[class*="item"], li, [class*="merchant"], [class*="shop"]');
                for (var i = 0; i < items.length; i++) {
                    var el = items[i];
                    if (el.children.length > 3) continue;
                    var text = (el.innerText || "").trim().split('\\n')[0];
                    if (!text || text.length < 3 || text.length > 50) continue;
                    
                    var name_key = text.toLowerCase();
                    var generic = [
                        "akun", "pengaturan", "log out", "halaman utama", "baru", "menu", "outlet", 
                        "shopeefood", "terapkan", "sembunyikan", "notifikasi", "pilih merchant lain", 
                        "pusat bantuan", "transaksi berhasil", "baris per halaman", "ringkasan toko", 
                        "nama toko", "jumlah total", "laporan saya", "penghasilan", "performa outlet", 
                        "periode transaksi", "ubah bahasa", "daftar merchant", "daftar di sini", 
                        "memulai bisnis baru?", "pilih merchant", "gabung dengan merchant", 
                        "buat merchant baru", "hubungi kami", "faq", "syarat & ketentuan",
                        "pusat edukasi seller"
                    ];
                    if (generic.some(g => name_key === g || name_key.includes(g))) continue;

                    let rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        results.push({ name: text, index: i });
                    }
                }
                return results;
            """)

            if scan_result:
                all_els = driver.find_elements(By.CSS_SELECTOR, '.listItem, .merchant-item, li[class*="item"], li, [class*="merchant"], [class*="shop"]')
                for r in scan_result:
                    name = r['name']
                    name_key = name.lower()
                    m_id = all_merchants_data.get(name_key) or "Unknown"

                    if all_merchants_data and m_id == "Unknown":
                        continue

                    generic_texts = [
                        "akun", "pengaturan", "log out", "halaman utama", "baru", "menu", "outlet", 
                        "shopeefood", "terapkan", "sembunyikan", "notifikasi", "pilih merchant lain", 
                        "pusat bantuan", "transaksi berhasil", "baris per halaman", "ringkasan toko", 
                        "nama toko", "jumlah total", "laporan saya", "penghasilan", "performa outlet", 
                        "periode transaksi", "ubah bahasa", "daftar merchant", "daftar di sini", 
                        "memulai bisnis baru?", "pilih merchant", "gabung dengan merchant", 
                        "buat merchant baru", "hubungi kami", "faq", "syarat & ketentuan", 
                        "pusat edukasi seller"
                    ]
                    if m_id == "Unknown" and (len(name) < 4 or any(g == name_key or g in name_key for g in generic_texts) or "diupdate pada" in name_key):
                        continue

                    if m_id != active_id and name not in all_found:
                        all_found[name] = {"name": name, "element": all_els[r['index']], "id": m_id}

            if len(all_found) >= 20:
                break
            driver.execute_script("document.querySelectorAll('div[class*=\"menu\"], ul[class*=\"menu\"], .ant-popover-content').forEach(el => el.scrollTop += 300);")
            time.sleep(1.5)

        merchants = list(all_found.values())
        if not merchants:
            if "/food/dashboard" in driver.current_url:
                return True
            log.warning("⚠️ No merchants found in scan.")
            return False

        if interactive and sys.stdin.isatty():
            print("\n" + "=" * 75 + f"\n  DAFTAR MERCHANT ({len(merchants)} ditemukan):\n" + "=" * 75)
            for i, m in enumerate(merchants, 1):
                print(f"  {i:2}. {m['name']} (ID: {m['id']})")
            choice = input(f"\nPilih nomor (1-{len(merchants)}) atau Enter untuk lanjut: ").strip()
        else:
            log.info("⏭️  [MERCHANT] Mode otomatis (tanpa timeout), memilih secara otomatis...")
            if "/food/dashboard" not in driver.current_url:
                matched_idx = None
                if active_id_forced:
                    for i, m in enumerate(merchants):
                        if str(m["id"]) == str(active_id_forced):
                            matched_idx = i + 1
                            break
                if matched_idx:
                    log.info(f"👉 Ditemukan indeks merchant yang cocok: {matched_idx} ({merchants[matched_idx-1]['name']})")
                    choice = str(matched_idx)
                else:
                    log.info("👉 [MERCHANT] Onboarding/Selector page detected. Automatically choosing the first merchant to proceed.")
                    choice = "1"
            else:
                choice = ""

        if not choice:
            return True

        idx = int(choice) - 1
        if 0 <= idx < len(merchants):
            sel = merchants[idx]
            log.info(f"👉 Memilih: {sel['name']}")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sel["element"])
            time.sleep(0.5)
            try:
                sel["element"].click()
            except Exception:
                driver.execute_script("arguments[0].click();", sel["element"])

            log.info("  ⏳ Waiting for dashboard redirect...")
            WebDriverWait(driver, 30).until(EC.url_contains("/food/dashboard"))
            time.sleep(2)
            return True
        return False
    except Exception as e:
        log.error(f"Selection error: {e}")
        return False


def return_to_selector(driver) -> bool:
    log.debug("🔄 Opening merchant selector via UI menu (safe mode)...")
    try:
        if "/food/dashboard" not in driver.current_url:
            driver.get(PARTNER_DASHBOARD)
            time.sleep(3)

        wait = WebDriverWait(driver, 10)
        actions = ActionChains(driver)

        profile_menu = None
        for sel in [".merchantName", ".user-info", "li.ant-menu-item:last-child"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    profile_menu = el
                    break
            except Exception:
                continue

        if not profile_menu:
            log.warning("⚠️ Profile menu not found — using direct URL fallback.")
            driver.get(MERCHANT_SELECTOR_URL)
            return True

        try:
            actions.move_to_element(profile_menu).perform()
            time.sleep(1)
        except Exception:
            pass

        safe_click_done = driver.execute_script("""
            var keywords = ['pilih merchant', 'switch merchant', 'ganti merchant'];
            var blacklist = ['log out', 'logout', 'keluar', 'sign out'];

            var candidates = Array.from(document.querySelectorAll(
                'li.ant-menu-item, li[role="menuitem"], .ant-dropdown-menu-item, '
                + '[class*="menu-item"], span, div, a'
            ));

            for (var el of candidates) {
                var rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                var text = (el.innerText || '').trim().toLowerCase();
                if (!text) continue;

                if (blacklist.some(function(k){ return text.includes(k); })) continue;

                if (keywords.some(function(k){ return text.includes(k); })) {
                    el.click();
                    return true;
                }
            }
            return false;
        """)

        if safe_click_done:
            log.debug("  ✅ Clicked 'Pilih Merchant Lain' safely via JS scan.")
            time.sleep(2)
            return True

        log.warning("  ⚠️ 'Pilih Merchant Lain' not found in dropdown — using direct URL fallback.")
        driver.get(MERCHANT_SELECTOR_URL)
        time.sleep(3)
        return True

    except Exception as e:
        log.error(f"❌ return_to_selector failed: {e} — falling back to direct URL.")
        try:
            driver.get(MERCHANT_SELECTOR_URL)
        except Exception:
            pass
        return True


def get_session(username=None, password=None, phone=None, headless=None, close_browser=True, target_name=None, interactive=True) -> dict | None:
    if headless is None:
        headless = is_headless_enabled()

    if not (username and password):
        c_user, c_pass, c_phone = _load_agency_credentials()
        username = username or c_user
        password = password or c_pass
        phone = phone or c_phone
    if username == "auto7313":
        username = "allvbadmin"

    for attempt in range(3):
        is_headless = headless if headless is not None else is_headless_enabled()
        log.info(f"🌐 [BROWSER] Launching (headless={is_headless}, attempt={attempt+1}/3)...")
        driver = _init_driver(headless=is_headless)
        wait = WebDriverWait(driver, 30)
        session_success = False

        try:
            driver.get(PARTNER_DASHBOARD)
            time.sleep(4)

            is_logged_in = False
            current_url = driver.current_url.lower()

            if "dashboard" in current_url or "merchant-selector" in current_url or "onboarding" in current_url:
                log.info("✅ [SESSION] Browser is already logged in.")
                is_logged_in = True

            if not is_logged_in and attempt == 0:
                saved = load_session()
                if saved:
                    log.debug("🔍 Attempting to restore session from saved tokens...")
                    try:
                        driver.add_cookie({"name": "shopee_tob_token", "value": saved["shopee_tob_token"]})
                        if saved.get("shopee_tob_entity_id"):
                            driver.add_cookie({"name": "shopee_tob_entity_id", "value": saved["shopee_tob_entity_id"]})
                        for n, v in saved.get("extra_cookies", {}).items():
                            try:
                                driver.add_cookie({"name": n, "value": v})
                            except Exception:
                                pass

                        driver.refresh()
                        time.sleep(4)
                        current_url = driver.current_url.lower()
                        if "dashboard" in current_url or "merchant-selector" in current_url:
                            log.info("✅ [SESSION] Restored from saved tokens.")
                            is_logged_in = True
                    except Exception:
                        pass

            if not is_logged_in and attempt > 0:
                log.info(f"🔄 [SESSION] Attempt {attempt+1}: trying saved tokens before fresh login...")
                saved = load_session()
                if saved and saved.get("shopee_tob_token"):
                    try:
                        driver.add_cookie({"name": "shopee_tob_token", "value": saved["shopee_tob_token"]})
                        if saved.get("shopee_tob_entity_id"):
                            driver.add_cookie({"name": "shopee_tob_entity_id", "value": saved["shopee_tob_entity_id"]})
                        for n, v in saved.get("extra_cookies", {}).items():
                            try:
                                driver.add_cookie({"name": n, "value": v})
                            except Exception:
                                pass
                        driver.refresh()
                        time.sleep(4)
                        current_url = driver.current_url.lower()
                        if "dashboard" in current_url or "merchant-selector" in current_url:
                            log.info(f"✅ [SESSION] Restored from saved tokens on retry {attempt+1} — no fresh login needed.")
                            is_logged_in = True
                    except Exception as _cookie_err:
                        log.warning(f"  ⚠️ Cookie injection on retry failed: {_cookie_err}")

            if not is_logged_in:
                log.info("⚠️ [SESSION] No active session. Navigating to login...")
                if "/login" not in driver.current_url.lower() and "authenticate" not in driver.current_url.lower():
                    driver.get("https://partner.shopee.co.id/login")
                    time.sleep(5)

                current_url = driver.current_url.lower()
                if "login" in current_url or "authenticate" in current_url or "about:blank" in current_url:
                    success = _perform_login(driver, wait, username, password, phone, is_retry=(attempt == 2))
                    if not success:
                        log.error("❌ [AUTH] _perform_login failed.")
                        cleanup_driver_process(driver)
                        continue

                log.info("  ⏳ Menunggu pengalihan halaman setelah login...")
                redirected_ok = False
                for _ in range(30):
                    curr_url = driver.current_url.lower()
                    if "onboarding" in curr_url or "merchant-selector" in curr_url or "dashboard" in curr_url:
                        redirected_ok = True
                        break
                    time.sleep(0.5)

                if redirected_ok and ("onboarding" in driver.current_url.lower() or "merchant-selector" in driver.current_url.lower()):
                    log.info("📍 [SESSION] Detected Onboarding page. Checking page type...")
                    bypass_success = False

                    if _handle_onboarding_invitation(driver):
                        time.sleep(3)
                        if "/food/dashboard" in driver.current_url:
                            log.info("  ✅ [SESSION] Invitation accepted during session init. Continuing...")
                            bypass_success = True

                    if not bypass_success:
                        log.info("📍 [SESSION] Merchant selector detected. Selecting first available merchant...")
                        bypass_js = """
                            var loaders = document.querySelectorAll('.ant-spin, [class*="loading"], .shopee-loading, .ant-spin-nested-loading');
                            loaders.forEach(el => el.remove());
                            var target = document.querySelector('.listItem, .merchant-item, li[class*="item"], [class*="merchant-item"], .ant-list-item');
                            if (target) {
                                target.scrollIntoView({block: 'center'});
                                try { target.click(); } catch(e) {}
                                var clickEvent = new MouseEvent('click', {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window
                                });
                                target.dispatchEvent(clickEvent);
                                return true;
                            }
                            return false;
                        """
                        for _ in range(10):
                            if driver.execute_script(bypass_js):
                                log.debug("  ✅ Selection triggered via JS.")
                                try:
                                    log.debug("  ⏳ Waiting for redirect (either dashboard or onboarding)...")
                                    start_redirect_wait = time.time()
                                    is_onboard_route = False

                                    while time.time() - start_redirect_wait < 15:
                                        curr_url = driver.current_url.lower()
                                        if "/food/dashboard" in curr_url:
                                            break
                                        if "onboarding" in curr_url:
                                            is_onboard_route = True
                                            break
                                        try:
                                            btns = driver.find_elements(By.XPATH, "//button[contains(., 'Gabung dengan Merchant') or contains(., 'Gabung') or contains(text(), 'Gabung')]")
                                            if any(b.is_displayed() for b in btns):
                                                is_onboard_route = True
                                                break
                                        except Exception:
                                            pass
                                        time.sleep(0.5)

                                    if is_onboard_route:
                                        log.info("📍 [SESSION] Onboarding page/modal detected. Accepting invitation...")
                                        try:
                                            btn_xpath = "//button[contains(., 'Gabung dengan Merchant') or contains(., 'Gabung') or contains(text(), 'Gabung')]"
                                            onboard_btn = WebDriverWait(driver, 10).until(
                                                EC.element_to_be_clickable((By.XPATH, btn_xpath))
                                            )
                                            onboard_btn.click()
                                            log.info("  👉 Clicked 'Gabung' button during session init onboarding")
                                            time.sleep(5)
                                        except Exception as err:
                                            log.warning(f"  ⚠️ Could not click Gabung button: {err}")

                                    wait.until(lambda d: "/food/dashboard" in d.current_url)
                                    log.debug("  ✅ Landed on dashboard.")
                                    bypass_success = True
                                    break
                                except Exception as e:
                                    log.warning(f"  ⚠️ Onboarding selector bypass attempt failed: {e}")
                            try:
                                container = driver.find_element(By.CSS_SELECTOR, ".ant-list-items, [role='list']")
                                driver.execute_script("arguments[0].scrollTop += 300;", container)
                            except Exception:
                                pass
                            time.sleep(1)
                    if bypass_success:
                        time.sleep(2)

            log.debug("🔍 Fetching active merchant info via API...")
            active_id = None
            active_name = "Unknown Merchant"
            try:
                api_js = """
                var done = arguments[arguments.length - 1];
                let token = document.cookie.split('; ').find(row => row.startsWith('shopee_tob_token='))?.split('=')[1];
                fetch('https://api.partner.shopee.co.id/nb/mss/web-api/PartnerAccountServer/GetUserInfo', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'x-merchant-token': token || '',
                        'x-merchant-language': 'id',
                        'x-merchant-login-from': '12'
                    },
                    body: '{}',
                    credentials: 'include'
                })
                .then(r => r.json())
                .then(j => done(j.data || null))
                .catch(() => done(null));
                """
                driver.set_script_timeout(10)
                user_data = driver.execute_async_script(api_js)
                if user_data:
                    active_id = str(user_data.get("merchantId") or "")
                    active_name = user_data.get("merchantName") or "Unknown Merchant"
            except Exception:
                pass

            if not active_id or active_id == "None":
                try:
                    log.debug("  ⏳ Menunggu sinkronisasi UI merchant (Maks 10 detik)...")

                    def get_ui_name(d):
                        try:
                            t = d.find_element(By.CLASS_NAME, "merchantName").text.strip()
                            return t if t else False
                        except Exception:
                            return False

                    ui_name = WebDriverWait(driver, 10).until(get_ui_name)
                    if ui_name:
                        active_name = ui_name
                        api_response_path = BASE_DIR / "API" / "response.json"
                        if api_response_path.exists():
                            with open(api_response_path, "r") as f:
                                m_data = json.load(f)
                                for m in m_data.get("data", {}).get("selectMerchant", {}).get("merchantList", []):
                                    if m["merchantName"].lower() == ui_name.lower():
                                        active_id = str(m["merchantId"])
                                        log.info(f"📍 [MERCHANT] Detected UI: {active_name} (ID: {active_id})")
                                        break
                except Exception:
                    pass

            if not active_id:
                _, active_id = extract_tokens_from_driver(driver)

            do_switch = False
            if target_name:
                if active_name.lower() != target_name.lower():
                    log.info(f"📍 [MERCHANT] Current: {active_name} | Target: {target_name}. Switching...")
                    do_switch = True
                elif not active_id or active_id == "None":
                    log.info(f"⚠️ [MERCHANT] Target is {active_name}, but active_id is missing! Forcing switch to hydrate session cookies...")
                    do_switch = True
                else:
                    log.info(f"✅ [MERCHANT] Already as target: {active_name}")
            else:
                is_invalid_name = (
                    not active_name or
                    active_name.lower().strip() == "unknown merchant" or
                    active_name.lower().strip() == "admin"
                )
                if not is_invalid_name:
                    log.info(f"📍 [MERCHANT] Current: {active_name} (ID: {active_id or 'unknown'}). Accepted.")
                    do_switch = False
                else:
                    log.info(f"📍 [MERCHANT] Invalid active merchant detected (Name: {active_name}, ID: {active_id}). Redirecting/Switching...")
                    do_switch = True

            if do_switch:
                if target_name:
                    success = auto_switch_merchant(driver, target_name, is_retry=(attempt == 2))
                    if not success:
                        log.warning(f"⚠️ [MERCHANT] auto_switch_merchant failed for target {target_name}. Initiating logout/relogin recovery...")
                        recovered = _deliberate_logout_and_relogin(
                            driver,
                            username=username,
                            password=password,
                            phone=phone,
                        )
                        if recovered:
                            log.info("🔄 [MERCHANT] Recovery successful. Retrying merchant switch...")
                            success = auto_switch_merchant(driver, target_name, is_retry=(attempt == 2))
                        else:
                            log.error("❌ Recovery failed.")
                            success = False
                else:
                    log.info("🔄 [MERCHANT] Unknown/Admin/Missing merchant — initiating logout/relogin recovery...")
                    recovered = _deliberate_logout_and_relogin(
                        driver,
                        username=username,
                        password=password,
                        phone=phone,
                    )
                    if recovered:
                        success = _handle_merchant_selection(driver, active_id_forced=None, interactive=interactive)
                    else:
                        log.error("❌ Logout/relogin recovery failed. Cannot proceed.")
                        success = False
                if not success:
                    log.error("❌ Merchant selection failed.")
                    cleanup_driver_process(driver)
                    continue
            else:
                if "/food/dashboard" not in driver.current_url:
                    driver.get(PARTNER_DASHBOARD)
                    time.sleep(2)

            t, eid = _trigger_and_extract_tokens(driver)
            if not eid and active_id and active_id != "None":
                log.info(f"⚠️ [SESSION] Token extraction returned empty entity_id. Using fallback active_id: {active_id}")
                eid = active_id

            if not t:
                log.warning("⚠️ Token extraction failed.")
                cleanup_driver_process(driver)
                continue

            all_c = get_all_cookies_dict(driver)
            save_session(t, eid or "", extra_cookies=all_c)
            res = {"shopee_tob_token": t, "shopee_tob_entity_id": eid or "", "extra_cookies": all_c}
            if not close_browser:
                res["driver"] = driver
            session_success = True
            return res

        except Exception as e:
            err_msg = str(e)
            log.error(f"Browser session error on attempt {attempt+1}: {err_msg}")
            if "MERCHANT_NOT_FOUND" in err_msg:
                log.error("❌ Fatal Error: Merchant belum ditambahkan. Membatalkan antrean tanpa login ulang.")
                raise e
        finally:
            if (close_browser or not session_success) and driver is not None:
                cleanup_driver_process(driver)

    log.error("❌ Max login retries reached.")
    return None


def refresh_tokens(driver, fallback_entity_id=None) -> dict:
    t, eid = _trigger_and_extract_tokens(driver)
    if not eid and fallback_entity_id and fallback_entity_id != "None":
        log.info(f"⚠️ [SESSION] refresh_tokens: Using fallback_entity_id: {fallback_entity_id}")
        eid = fallback_entity_id
    all_c = get_all_cookies_dict(driver)
    save_session(t, eid or "", extra_cookies=all_c)
    return {"shopee_tob_token": t, "shopee_tob_entity_id": eid or "", "extra_cookies": all_c}


# Agency Aliases
get_agency_session = get_session
cleanup_agency_driver = cleanup_driver_process
init_agency_driver = _init_driver
switch_to_merchant = auto_switch_merchant


# ── Outlet Status Inspection & Action (Agency Specific — Matches bot-oc logic) ─

def ensure_business_hours_page(driver, store_id: str) -> bool:
    if not driver or not store_id:
        return False
    target_url = f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}"
    current_url = str(driver.current_url or "").lower()

    if f"storeid={store_id}".lower() not in current_url:
        log.info(f"🌐 Navigating to business hours page for store {store_id}: {target_url}")
        driver.get(target_url)
        time.sleep(2.0)

    for attempt in range(1, 4):
        try:
            check_res = driver.execute_script("""
                var bodyText = (document.body ? document.body.innerText : '').toLowerCase();
                var hasKeywords = bodyText.includes('jam operasional') || bodyText.includes('tutup outlet') || bodyText.includes('buka outlet') || bodyText.includes('tutup sementara');
                var currUrl = window.location.href.toLowerCase();
                return { url_match: currUrl.includes('business-hours') || currUrl.includes('storeid='), has_keywords: hasKeywords };
            """)
            if check_res and check_res.get("url_match") and check_res.get("has_keywords"):
                return True
            time.sleep(1.5)
        except Exception:
            time.sleep(1.0)
    return True


def get_outlet_shopee_status(driver, store_id: str) -> str:
    log.info(f"📊 Inspecting live status for store_id: {store_id}")
    try:
        if _detect_and_recover_logout(driver):
            log.info("✅ Session recovered during status inspection.")

        ensure_business_hours_page(driver, store_id)

        res = driver.execute_async_script("""
            var done = arguments[arguments.length - 1];
            fetch('https://foody.shopee.co.id/api/seller/store', {
                method: 'GET',
                credentials: 'include',
                headers: { 'Accept': 'application/json, text/plain, */*' }
            })
            .then(function(r) { return r.json(); })
            .then(function(d) { done(d); })
            .catch(function(e) { done({code: -1, msg: e.message || String(e)}); });
        """)

        if isinstance(res, dict) and res.get("code") == 0 and res.get("data"):
            data = res["data"]
            store_data = data.get("store", {})
            op_data = data.get("opening_status", {})

            display_status = op_data.get("display_opening_status", op_data.get("opening_status", store_data.get("opening_status", 0)))
            order_enabled = op_data.get("order_enabled", 0)
            pause_time = op_data.get("pause_time") or {}
            pause_start = pause_time.get("pause_start_time", 0) if isinstance(pause_time, dict) else 0

            if (display_status == 2 or order_enabled == 1) and pause_start == 0:
                log.info(f"✅ Store {store_id} live status via API: OPEN")
                return "OPEN"
            else:
                log.info(f"✅ Store {store_id} live status via API: CLOSED")
                return "CLOSED"

        body_text = (driver.find_element(By.TAG_NAME, "body").text or "").lower()
        if "tutup outlet sementara" in body_text:
            log.info(f"✅ Store {store_id} live status via DOM: OPEN")
            return "OPEN"
        elif "buka outlet" in body_text:
            log.info(f"✅ Store {store_id} live status via DOM: CLOSED")
            return "CLOSED"

        status_raw = driver.execute_script("""
            var sw = document.querySelector('.ant-switch');
            if (sw) return sw.classList.contains('ant-switch-checked') ? 'OPEN' : 'CLOSED';
            return null;
        """)
        if status_raw in ("OPEN", "CLOSED"):
            return status_raw

    except Exception as e:
        log.warning(f"⚠️ Error inspecting status for store {store_id}: {e}")

    return "UNKNOWN"


def execute_force_close(driver, store_id: str, pause_duration_minutes: int = 1440) -> bool:
    log.info(f"⚡ Executing Force Close action for store_id: {store_id}")
    try:
        if _detect_and_recover_logout(driver):
            log.info("✅ Session recovered prior to force close execution.")

        current_st = get_outlet_shopee_status(driver, store_id)
        if current_st == "CLOSED":
            log.info(f"✅ Store {store_id} is already CLOSED. Skipping action.")
            return True

        ensure_business_hours_page(driver, store_id)

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
            log.info("👉 Clicked 'Tutup Outlet Sementara' button on UI. Confirming modal...")
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
                log.info("✅ Confirmed 'Tutup Outlet' modal successfully.")
                time.sleep(2.0)
                final_check = get_outlet_shopee_status(driver, store_id)
                return final_check == "CLOSED" or final_check == "UNKNOWN"

        log.info(f"🌐 UI button fallback: executing XHR POST action/pause for store {store_id}...")
        target_num = int(store_id) if str(store_id).isdigit() else store_id
        res = driver.execute_async_script(f"""
            var done = arguments[arguments.length - 1];
            var now = Date.now();
            var end = now + ({pause_duration_minutes} * 60 * 1000);
            fetch('https://foody.shopee.co.id/api/seller/store/opening-status/action/pause?store_id={store_id}', {{
                method: 'POST',
                credentials: 'include',
                headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*' }},
                body: JSON.stringify({{
                    "pause_start_time": now,
                    "pause_end_time": end,
                    "store_id": {target_num}
                }})
            }})
            .then(function(r) {{ return r.json(); }})
            .then(function(d) {{ done(d); }})
            .catch(function(e) {{ done({{code: -1, msg: e.message || String(e)}}); }});
        """)

        log.info(f"🔍 Action pause API response for store {store_id}: {res}")
        if isinstance(res, dict) and res.get("code") == 0:
            log.info(f"✅ Store {store_id} successfully force closed via API.")
            return True

    except Exception as e:
        log.error(f"❌ Force close execution failed for store {store_id}: {e}")

    return False
