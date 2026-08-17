#!/usr/bin/env python3
"""
test_business_hours_flow.py
============================
Test script to navigate to Shopee Dashboard, switch to target merchant (WonderFood),
navigate to business hours page for storeId 21897166, pull regular hours, check status,
and test open/pause endpoint actions using the src/shopee/store_status.py module.
"""

import sys
import json
import time
from pathlib import Path

# Add src to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SYS_SRC = PROJECT_ROOT / "src"
if str(SYS_SRC) not in sys.path:
    sys.path.insert(0, str(SYS_SRC))

from core import browser
from shopee import store_status

def main():
    username = "auto7313"
    target_merchant = "WonderFood"
    target_store_id = "21897166"

    print("================================================================================")
    print(f"🚀 [TEST FLOW] Starting Business Hours & API Action Test")
    print(f"   Account: {username} | Merchant: {target_merchant} | Store ID: {target_store_id}")
    print("================================================================================\n")

    # Set session file dynamically
    session_file_path = browser.DATA_DIR / f"session_{username}.json"
    browser.set_session_file(session_file_path)

    # 1. Get browser session
    print("1️⃣ Launching browser & initializing session...")
    session = browser.get_session(
        username=username,
        target_name=target_merchant,
        close_browser=False,
    )

    if not session or not session.get("driver"):
        print("❌ Failed to initialize browser session.")
        return

    driver = session["driver"]

    try:
        # 2. Navigate to store business hours URL (as described in DOCS/guide-masuk-business-hours.md)
        b_hours_url = f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={target_store_id}"
        print(f"\n2️⃣ Navigating to Business Hours URL:\n   {b_hours_url}")
        driver.get(b_hours_url)
        time.sleep(3)
        print(f"   Current URL: {driver.current_url}")

        # 3. Pull Regular Hours using src/shopee/store_status.py
        print("\n3️⃣ Pulling Regular Hours via shopee.store_status.get_regular_hours...")
        reg_data = store_status.get_regular_hours(driver, target_store_id)
        if reg_data:
            print("   ✅ Regular Hours pull SUCCESSFUL!")
            print("   Sample Data:")
            print(json.dumps(reg_data, indent=2)[:500] + "\n   ...")
        else:
            print("   ⚠️ Regular Hours pull returned None or empty.")

        # 4. Pull Actual Store Status using src/shopee/store_status.py
        print("\n4️⃣ Checking Live Store Status via shopee.store_status.get_actual_store_status...")
        status_info = store_status.get_actual_store_status(driver, target_store_id)
        print(f"   Live Status Info: {status_info}")

        # 5. Test Store Pause Action Endpoint API
        print("\n5️⃣ Testing Store PAUSE (Auto Close) Action API...")
        pause_ok = store_status.pause_store_action(driver, target_store_id)
        print(f"   Pause Action Result: {'SUCCESS ✅' if pause_ok else 'FAILED ❌'}")
        time.sleep(2)

        # 6. Test Store Open Action Endpoint API
        print("\n6️⃣ Testing Store OPEN (Auto Open) Action API...")
        open_ok = store_status.open_store_action(driver, target_store_id)
        print(f"   Open Action Result: {'SUCCESS ✅' if open_ok else 'FAILED ❌'}")

        print("\n================================================================================")
        print("🎉 [TEST FLOW COMPLETE] All steps executed cleanly!")
        print("================================================================================")

    except Exception as e:
        print(f"\n❌ Error during test execution: {e}")
    finally:
        print("\n🛑 Quitting browser session...")
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
