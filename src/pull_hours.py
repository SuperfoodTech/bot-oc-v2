"""
pull_hours.py
=============
Pull regular hours & special hours for stores grouped by Merchant Portal (nama_portal).
Performs merchant portal switch ONCE per portal group, then pulls all store IDs under that portal.
"""

import os
import sys
import json
import time
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from core.logger import get_logger
from core.sheets import fetch_merchant_outlets
from core import browser

log = get_logger("pull_hours")

ACCOUNT_NAME = "auto7313"
OUTPUT_DIR = SCRIPT_DIR / "data" / "pulled_hours"


def pull_store_hours():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"🚀 [PULL HOURS] Starting grouped extraction for account '{ACCOUNT_NAME}'...")

    # Fetch stores for auto7313 from Google Sheets
    all_outlets = fetch_merchant_outlets()
    user_outlets = [o for o in all_outlets if ACCOUNT_NAME in (o.username or "")]

    if not user_outlets:
        log.warning(f"⚠️ No stores found in spreadsheet for account '{ACCOUNT_NAME}'.")
        return

    log.info(f"📊 Found {len(user_outlets)} store(s) under account '{ACCOUNT_NAME}'.")

    # Group stores by Nama Portal / Merchant Name
    outlets_by_portal = defaultdict(list)
    for out in user_outlets:
        # Normalize portal name (e.g. SuperFood, WonderFood, LOKARASA, Do Eat, Gurame Bakar)
        portal_key = (out.nama_portal or "default").strip()
        outlets_by_portal[portal_key].append(out)

    log.info(f"🏢 Portals grouped ({len(outlets_by_portal)}): {list(outlets_by_portal.keys())}")

    session_file = SCRIPT_DIR / "data" / f"session_{ACCOUNT_NAME}.json"
    browser.set_session_file(session_file)

    log.info(f"🌐 Launching Chrome session for account '{ACCOUNT_NAME}'...")
    first_outlet = user_outlets[0]
    session_data = browser.get_session(
        username=first_outlet.username or "auto7313",
        password=first_outlet.password or "Auto@7313",
        phone=first_outlet.hp or "",
        headless=False,       # GUI mode to ensure smooth profile load & merchant switch
        close_browser=False,
        interactive=True,
    )

    if not session_data:
        log.error("❌ Failed to initialize browser session.")
        return

    driver = session_data.get("driver")
    if not driver:
        log.error("❌ Driver not available.")
        return

    summary_results = []

    try:
        # Grouped processing: 1 Merchant Switch per Portal Group
        for portal_name, portal_stores in outlets_by_portal.items():
            log.info(f"\n=========================================================================")
            log.info(f"🏢 [GROUP] Processing Merchant Portal: '{portal_name}' ({len(portal_stores)} store(s))...")
            log.info(f"=========================================================================")

            # Attempt merchant switch for this portal group
            switch_ok = False
            try:
                # Try exact portal_name first, then try primary brand prefix (e.g. "Do Eat" from "Do Eat, Gurame Bakar")
                try:
                    switch_ok = browser.auto_switch_merchant(driver, target_name=portal_name)
                except ValueError:
                    if "," in portal_name:
                        brand_prefix = portal_name.split(",")[0].strip()
                        log.info(f"🔄 Retrying portal switch with primary brand name: '{brand_prefix}'...")
                        switch_ok = browser.auto_switch_merchant(driver, target_name=brand_prefix)
                time.sleep(3)
            except Exception as e:
                log.warning(f"⚠️ Portal switch warning for '{portal_name}': {e}")

            # Iterate over all stores in this portal group
            for store in portal_stores:
                store_id = store.store_id
                store_name = store.nama_pendek_outlet
                log.info(f"  🏪 [STORE] Pulling hours for Store ID {store_id} ({store_name})...")

                # Direct navigate to store business hours URL
                store_url = (
                    f"https://partner.shopee.co.id/settings/shopee-food/business-hours-settings/business-hours?storeId={store_id}"
                )
                driver.get(store_url)
                time.sleep(4)

                # Execute JS fetch for regular-hours
                regular_js = """
                var callback = arguments[arguments.length - 1];
                fetch('https://foody.shopee.co.id/api/seller/store/regular-hours', {
                    headers: { 'accept': 'application/json, text/plain, */*' },
                    credentials: 'include'
                })
                .then(r => r.json())
                .then(data => callback(data))
                .catch(err => callback({error: err.toString()}));
                """
                regular_data = driver.execute_async_script(regular_js)

                # Execute JS fetch for special-hours
                special_js = """
                var callback = arguments[arguments.length - 1];
                fetch('https://foody.shopee.co.id/api/seller/store/special-hours', {
                    headers: { 'accept': 'application/json, text/plain, */*' },
                    credentials: 'include'
                })
                .then(r => r.json())
                .then(data => callback(data))
                .catch(err => callback({error: err.toString()}));
                """
                special_data = driver.execute_async_script(special_js)

                # Save JSON files locally
                reg_file = OUTPUT_DIR / f"store_{store_id}_regular.json"
                spec_file = OUTPUT_DIR / f"store_{store_id}_special.json"

                reg_file.write_text(json.dumps(regular_data, indent=2))
                spec_file.write_text(json.dumps(special_data, indent=2))

                reg_success = isinstance(regular_data, dict) and regular_data.get("code") == 0
                spec_success = isinstance(special_data, dict) and special_data.get("code") == 0
                spec_items = len(special_data.get("data", {}).get("special_hours", [])) if spec_success else 0

                status_label = "OK" if reg_success else f"FAIL ({regular_data.get('msg', 'Err') if isinstance(regular_data, dict) else 'Err'})"
                log.info(f"    -> Regular Hours: {status_label}")
                log.info(f"    -> Special Hours: {'OK' if spec_success else 'FAIL'} ({spec_items} item(s))")

                summary_results.append({
                    "store_id": store_id,
                    "portal": portal_name,
                    "name": store_name,
                    "regular_status": status_label,
                    "special_count": spec_items
                })

    finally:
        log.info("\n🔒 Closing Chrome session...")
        try:
            driver.quit()
        except Exception:
            pass

    print("\n" + "=" * 90)
    print(f"{'STORE ID':<12} | {'PORTAL':<18} | {'STORE NAME':<24} | {'REGULAR':<15} | {'SPECIAL HOURS'}")
    print("=" * 90)
    for res in summary_results:
        print(f"{res['store_id']:<12} | {res['portal'][:18]:<18} | {res['name'][:24]:<24} | {res['regular_status']:<15} | {res['special_count']} item(s)")
    print("=" * 90)
    log.info(f"🎉 Successfully pulled hours for {len(summary_results)} store(s)! Saved to '{OUTPUT_DIR}'")


if __name__ == "__main__":
    pull_store_hours()
