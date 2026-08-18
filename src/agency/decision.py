"""
src/agency/decision.py
======================
Pure Decision Engine for Agency Force Close operations.
STRICT RULE: No OPEN actions. Only ACTION_CLOSE or ACTION_STOP.
"""

from dataclasses import dataclass

ACTION_CLOSE = "ACTION_CLOSE"
ACTION_STOP = "ACTION_STOP"

TARGET_CLOSE = "CLOSE"


@dataclass
class AgencyDecisionResult:
    target_state: str  # Always "CLOSE"
    action: str        # ACTION_CLOSE or ACTION_STOP
    reason: str        # Explanation string


def evaluate_agency_outlet_status(current_shopee_status: str) -> AgencyDecisionResult:
    """
    Evaluates Shopee actual status for an Agency Churn outlet.
    
    If store is currently OPEN -> Returns ACTION_CLOSE (Force Close required).
    If store is currently CLOSED/PAUSE/OFF -> Returns ACTION_STOP (No change needed).
    """
    status_raw = (current_shopee_status or "").strip().lower()
    is_open = status_raw in ["on", "open", "buka", "2"]

    if is_open:
        return AgencyDecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_CLOSE,
            reason="Outlet berstatus Churn terdeteksi Buka (OPEN) di ShopeeFood. Mengeksekusi Force Close."
        )
    else:
        return AgencyDecisionResult(
            target_state=TARGET_CLOSE,
            action=ACTION_STOP,
            reason="Outlet berstatus Churn sudah dalam keadaan Tutup/Pause di ShopeeFood. Menghentikan aksi (STOP)."
        )
