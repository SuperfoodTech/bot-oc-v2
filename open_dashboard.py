#!/usr/bin/env python3
"""
open_dashboard.py
=================
Script to launch Chrome, log in (or restore session) for account 'auto7313',
navigate to Shopee Partner Dashboard, and keep the browser open.
"""

import sys
import time
from pathlib import Path

# Add src to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
SYS_SRC = PROJECT_ROOT / "src"
if str(SYS_SRC) not in sys.path:
    sys.path.insert(0, str(SYS_SRC))

from core import browser

def main():
    username = "auto7313"
    target_merchant = "WonderFood"

    # Set session file dynamically
    session_file_path = browser.DATA_DIR / f"session_{username}.json"
    browser.set_session_file(session_file_path)

    print(f"🚀 Opening Shopee Dashboard for account '{username}'...")
    print(f"📁 Session file: {session_file_path}")

    # Launch browser session targeting WonderFood merchant
    session = browser.get_session(
        username=username,
        target_name=target_merchant,
        close_browser=False,
    )

    if session and session.get("driver"):
        driver = session["driver"]
        print(f"\n✅ Browser successfully opened & logged in!")
        print(f"📍 Current URL: {driver.current_url}")
        print("🌐 Keeping browser session OPEN. Press Ctrl+C to close.\n")
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Closing browser session gracefully...")
            try:
                driver.quit()
            except Exception:
                pass
            print("👋 Closed.")
    else:
        print(f"❌ Failed to get browser session for '{username}'.")

if __name__ == "__main__":
    main()
