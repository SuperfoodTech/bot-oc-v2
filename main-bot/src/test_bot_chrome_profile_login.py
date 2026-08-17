"""
test_bot_chrome_profile_login.py
================================
Tests whether main-bot can successfully load chrome_profile_auto7313 and session_auto7313.json,
validate Shopee dashboard session, or perform headless Chrome login.
"""

import sys
import os
import json
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from logger import get_logger
import browser

log = get_logger("chrome_profile_test")

def run_test():
    log.info("=" * 80)
    log.info("🧪 [CHROME PROFILE LOGIN TEST] Checking bot execution with existing profile...")
    log.info("=" * 80)

    username = "auto7313"
    profile_dir = Path(__file__).resolve().parent / "data" / f"chrome_profile_{username}"
    session_file = Path(__file__).resolve().parent / "data" / f"session_{username}.json"

    log.info(f"📂 Profile Directory: {profile_dir} (Exists: {profile_dir.exists()})")
    log.info(f"📄 Session File: {session_file} (Exists: {session_file.exists()})")

    if session_file.exists():
        session_data = json.loads(session_file.read_text())
        log.info(f"   -> Found Saved Token: {session_data.get('shopee_tob_token', '')[:25]}...")
        log.info(f"   -> Found Entity ID: {session_data.get('shopee_tob_entity_id', '')}")

    # Set thread session file
    browser.set_session_file(session_file)

    log.info(f"\n🔑 Executing get_session for '{username}' using Chrome Profile...")
    try:
        session = browser.get_session(
            username=username,
            close_browser=True
        )
        if session and session.get("shopee_tob_token"):
            log.info(f"   -> Session Result: SUCCESS 🎉")
            log.info(f"   -> Shopee TOB Token: {session['shopee_tob_token'][:25]}...")
            log.info(f"   -> Entity ID: {session['shopee_tob_entity_id']}")
            log.info("=" * 80)
            log.info("🎉 CHROME PROFILE & SESSION VALIDATION TEST PASSED 100%!")
            log.info("=" * 80)
            return True
        else:
            log.warning("⚠️ Session returned empty token.")
            return False
    except Exception as e:
        log.error(f"❌ Session Validation Error: {e}")
        return False

if __name__ == "__main__":
    run_test()
