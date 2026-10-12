import csv
import io
import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import requests
from core.logger import get_logger

log = get_logger("otp")

OTP_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRYSUnKOqk29LCktTxdb0wPLbWMbRaWRP3eC_UA4AwYod1FW6zDMhtLMC5ghIvot2B8upCDfBsn-TCP/pub?gid=213442295&single=true&output=csv"
WIB = ZoneInfo("Asia/Jakarta")

def extract_otp_from_text(text: str) -> str:
    """Extract a 6-digit (or 4-6 digit) numeric OTP code from SMS body."""
    if not text:
        return ""
    # Check for Shopee pattern like: 'Kode OTP 123456' or 'kode verifikasi 123456'
    m = re.search(r"(?:kode\s+otp|kode\s+verifikasi|otp)\s*:?\s*(\d{4,6})", text, re.IGNORECASE)
    if m:
        return m.group(1).zfill(6) if len(m.group(1)) <= 6 else m.group(1)
    
    # Check general 6-digit standalone sequence
    m6 = re.search(r"\b(\d{6})\b", text)
    if m6:
        return m6.group(1)
    return ""

def parse_sheet_timestamp(ts_str: str) -> datetime | None:
    """Parse timestamp string from sheet into WIB timezone-aware datetime."""
    if not ts_str:
        return None
    ts_str = ts_str.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=WIB)
        except ValueError:
            continue
    return None

def fetch_latest_otp(timeout_mins: float = 10.0, target_sender: str = "shopee") -> tuple[str, datetime | None, dict | None]:
    """
    Fetches the latest OTP from the Google Sheet CSV matching current date / recent time window.
    Returns: (otp_code, timestamp_dt, raw_row)
    """
    for attempt in range(3):
        try:
            # Aggressive cache-busting
            url = f"{OTP_SHEET_URL}&_ts={int(time.time())}&_r={int(time.time() * 1000) % 100000}"
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Bot-OC-OTP-Fetcher/1.0",
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                content = resp.content.decode("utf-8", errors="replace")
                break
            log.warning(f"⚠️ [OTP-SHEET] HTTP {resp.status_code} saat fetch sheet OTP (attempt {attempt+1}/3)")
        except Exception as e:
            log.warning(f"⚠️ [OTP-SHEET] Fetch error (attempt {attempt+1}/3): {e}")
        time.sleep(2)
    else:
        return "", None, None

    try:
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            return "", None, None

        now_wib = datetime.now(WIB)
        # Scan from newest to oldest
        for row in reversed(rows):
            sender = row.get("Pengirim", "").strip().lower()
            body = row.get("Body SMS", "").strip()
            otp_col = row.get("OTP", "").strip()
            ts_str = row.get("Timestamp", "").strip() or row.get("Dicatat Pada", "").strip()

            # Filter sender if specified
            if target_sender:
                if target_sender not in sender and target_sender not in body.lower():
                    continue

            dt_row = parse_sheet_timestamp(ts_str)
            if not dt_row:
                continue

            # Must match today's date in WIB
            if dt_row.date() != now_wib.date():
                continue

            diff_seconds = (now_wib - dt_row).total_seconds()
            # Allow up to 2 minutes clock drift in the future and within timeout_mins in the past
            if -120 <= diff_seconds <= (timeout_mins * 60):
                # Extract clean OTP code
                code = extract_otp_from_text(body)
                if not code and otp_col and otp_col != "-":
                    # If OTP column has leading zero dropped by sheet, pad to 6 if 4-5 digits
                    code = otp_col.zfill(6) if len(otp_col) < 6 else otp_col

                if code and len(code) >= 4:
                    log.info(f"🎯 [OTP-SHEET] Ditemukan OTP valid: {code} | Row Timestamp: {ts_str} ({int(diff_seconds)}s lalu)")
                    return code, dt_row, row

        # Log newest entry info if no match
        last_row = rows[-1]
        log.debug(f"ℹ️ [OTP-SHEET] Baris terakhir di sheet: {last_row.get('Timestamp')} | Pengirim: {last_row.get('Pengirim')} | OTP: {last_row.get('OTP')}")

    except Exception as err:
        log.error(f"❌ [OTP-SHEET] Parsing CSV error: {err}")

    return "", None, None

def poll_for_new_otp(
    max_wait_seconds: int = 180,
    poll_interval: int = 3,
    since_dt: datetime | None = None,
    target_sender: str = "shopee",
) -> str:
    """
    Polls the Google Sheet CSV until an OTP newer than `since_dt` (or within 5 minutes) appears.
    """
    start_time = time.time()
    ref_time = since_dt or datetime.now(WIB)
    log.info(f"⏳ [OTP-SHEET] Memulai polling OTP dari Google Sheet (max {max_wait_seconds}s, interval {poll_interval}s)...")
    log.info(f"   Target Pengirim: {target_sender or 'Semua'} | Referensi waktu mulai: {ref_time.strftime('%Y-%m-%d %H:%M:%S')} WIB")

    last_seen_ts = None
    while time.time() - start_time < max_wait_seconds:
        otp_code, dt_row, row = fetch_latest_otp(timeout_mins=5.0, target_sender=target_sender)
        if otp_code and dt_row:
            # Must be newer than our request reference time (allow 10s buffer)
            if (dt_row - ref_time).total_seconds() >= -10:
                log.info(f"✅ [OTP-SHEET] Berhasil mendapatkan OTP TERBARU: {otp_code} (waktu SMS: {dt_row.strftime('%Y-%m-%d %H:%M:%S')} WIB)")
                return otp_code
            else:
                if last_seen_ts != dt_row:
                    log.info(f"⏳ [OTP-SHEET] OTP di sheet ({otp_code} pd {dt_row.strftime('%H:%M:%S')}) adalah SMS lama. Menunggu SMS baru setelah {ref_time.strftime('%H:%M:%S')}...")
                    last_seen_ts = dt_row

        time.sleep(poll_interval)

    log.warning("⚠️ [OTP-SHEET] Batas waktu polling OTP habis tanpa menerima kode baru.")
    return ""
