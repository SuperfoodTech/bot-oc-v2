#!/usr/bin/env python3
"""
login_otp.py
============
Interactive / Scripted Login & OTP Injection for close-bot.

Features:
- Launches isolated Chrome session for close-bot
- Detached from main-bot/main-vb production sessions
- Automatically detects Shopee OTP challenge
- Prompts for OTP via terminal, --otp argument, or close-bot/src/data/otp_code.txt
- Extracts Shopee TOB token and entity ID
- Saves session into close-bot/src/data/session_{username}.json
"""

import sys
import os
import argparse
import time
import json
from pathlib import Path

# Paths setup
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SRC_DIR = SCRIPT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.append(str(PROJECT_ROOT / "src"))

# Load environment files
env_main = PROJECT_ROOT / ".env"
env_close = PROJECT_ROOT / ".env.close"

if env_main.exists():
    from dotenv import load_dotenv
    load_dotenv(env_main)
if env_close.exists():
    from dotenv import load_dotenv
    load_dotenv(env_close, override=True)

# Force ALLOW_OTP for this execution
os.environ["ALLOW_OTP"] = "true"

import browser
from logger import get_logger

log = get_logger("login_otp")


def main():
    parser = argparse.ArgumentParser(description="Shopee Partner Login & OTP Handler for close-bot")
    parser.add_argument("--username", "-u", default=os.getenv("SHOPEE_BOT_USERNAME", "allvb"), help="Shopee username (default: allvb)")
    parser.add_argument("--password", "-p", default="Shopee@123", help="Shopee password (default: Shopee@123)")
    parser.add_argument("--otp", "-o", default="", help="6-digit OTP code (optional, can be inputted interactively)")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    parser.add_argument("--keep-open", action="store_true", help="Keep browser open after login")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password.strip()
    if args.otp:
        os.environ["SHOPEE_OTP_CODE"] = args.otp.strip()

    # Define dedicated close-bot data paths
    data_dir = SRC_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    session_file = data_dir / f"session_{username}.json"
    chrome_profile_dir = data_dir / "chrome_profile"
    chrome_profile_dir.mkdir(parents=True, exist_ok=True)

    # Set environment variables for browser module
    os.environ["SHOPEE_SESSION_FILE"] = str(session_file)
    os.environ["VB_SESSION_FILE"] = str(session_file)
    os.environ["SHOPEE_CHROME_PROFILE_DIR"] = str(chrome_profile_dir)
    os.environ["VB_CHROME_PROFILE_DIR"] = str(chrome_profile_dir)
    os.environ["SHOPEE_CHROME_PROFILE_NAME"] = "profile_closebot"
    os.environ["VB_CHROME_PROFILE_NAME"] = "profile_closebot"

    browser.set_session_file(session_file)

    print("=" * 75)
    print("🚀 [CLOSE-BOT] SHOPEE LOGIN & OTP INJECTION")
    print("=" * 75)
    print(f"👤 Akun Target    : {username}")
    print(f"📁 Session File    : {session_file}")
    print(f"📂 Chrome Profile  : {chrome_profile_dir} (profile_closebot)")
    print(f"🌐 Mode Headless   : {args.headless or browser.is_headless_enabled()}")
    print("=" * 75)

    # Execute login sequence
    try:
        session = browser.get_session(
            username=username,
            password=password,
            close_browser=not args.keep_open,
            interactive=True,
            headless=args.headless if args.headless else None,
        )

        if session and session.get("shopee_tob_token"):
            token = session["shopee_tob_token"]
            entity_id = session.get("shopee_tob_entity_id", "")
            print("\n" + "=" * 75)
            print("🎉 LOGIN SHOPEE BERHASIL 100%!")
            print("=" * 75)
            print(f"✅ TOB Token Prefix : {token[:35]}...")
            print(f"✅ Entity ID        : {entity_id}")
            print(f"✅ Sesi Tersimpan di: {session_file}")
            print("=" * 75)

            if args.keep_open and session.get("driver"):
                driver = session["driver"]
                print("\n🌐 Browser tetap terbuka. Tekan Ctrl+C untuk menutup...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\n🛑 Menutup browser...")
                    try:
                        driver.quit()
                    except Exception:
                        pass
            return 0
        else:
            print("\n❌ Gagal mendapatkan sesi Shopee. Silakan periksa log di atas.")
            return 1

    except Exception as e:
        print(f"\n❌ Terjadi exception saat proses login/OTP: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
