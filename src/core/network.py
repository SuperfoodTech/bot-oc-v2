"""
core/network.py
===============
Utilities for checking internet connectivity and Shopee API reachability.
Used by daemon and worker loops to prevent unnecessary retries or Selenium
launches when office internet is down.
"""

import socket
import requests
from core.logger import get_logger

log = get_logger("network")

# Public DNS servers used for lightweight socket connectivity check
CHECK_HOSTS = [("1.1.1.1", 53), ("8.8.8.8", 53)]
SHOPEE_VALIDATE_URL = "https://api.partner.shopee.co.id/nb/mss/web-api/PartnerAccountServer/GetUserInfo"


def is_internet_available(timeout: float = 3.0) -> bool:
    """
    Checks if internet connectivity is available by attempting a rapid socket
    connection to public DNS servers (Cloudflare/Google).
    """
    for host, port in CHECK_HOSTS:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, socket.error):
            continue
    return False


def is_shopee_api_reachable(timeout: float = 4.0) -> bool:
    """
    Lightweight HTTP check to verify if api.partner.shopee.co.id is reachable.
    """
    try:
        resp = requests.options("https://api.partner.shopee.co.id", timeout=timeout)
        return resp.status_code < 500
    except Exception:
        # Fallback HEAD / GET if OPTIONS fails
        try:
            resp = requests.head("https://partner.shopee.co.id", timeout=timeout)
            return resp.status_code < 500
        except Exception:
            return False
