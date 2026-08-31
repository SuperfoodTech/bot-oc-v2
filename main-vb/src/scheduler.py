"""Merchant-aware in-memory patrol scheduler.

The scheduler deliberately owns ordering only.  Decision and action execution
remain in the existing worker so the state contract stays in one place.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from decision import (
    ACTION_CLOSE,
    ACTION_OPEN,
    evaluate_outlet_status,
    get_active_pause_until,
    get_next_schedule_start,
    is_within_operating_hours,
    outlet_timezone,
)
from sheets import MerchantOutlet, WEEKDAY_MAP

LOCAL_TZ = ZoneInfo("Asia/Jakarta")
OPEN_HEARTBEAT_SECONDS = 180
INACTIVE_HEARTBEAT_SECONDS = 600
SCHEDULE_RETRY_SECONDS = 60

P0_ACTIONABLE_OPEN = 100
P0_ACTIONABLE_CLOSE = 95
P0_VERIFY = 90
P1_BOUNDARY = 80
P1_PAUSE_EXPIRY = 70
P2_NEXT_SCHEDULE = 60
P3_OPEN_HEARTBEAT = 40
P4_SCHEDULE_UNAVAILABLE = 30
P5_INACTIVE = 10


@dataclass(frozen=True)
class OutletDueState:
    store_id: str
    merchant_key: tuple[str, str]
    due_at: datetime
    priority: int
    reason: str
    desired_state: str
    live_state: str
    actionable: bool


@dataclass(frozen=True)
class MerchantQueueItem:
    merchant_key: tuple[str, str]
    username: str
    portal_name: str
    due_at: datetime
    priority: int
    due_store_ids: tuple[str, ...]
    outlet_count: int
    actionable_count: int
    reasons: tuple[str, ...]


def merchant_key(outlet: MerchantOutlet) -> tuple[str, str]:
    return ((outlet.username or "").strip(), (outlet.nama_portal or "").strip())


def _now(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(LOCAL_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=LOCAL_TZ)
    return value.astimezone(LOCAL_TZ)


def _schedule(outlet: MerchantOutlet) -> dict:
    return getattr(outlet, "regular_hours", None) or getattr(outlet, "shopee_regular_hours", None) or {}


def _today_is_open(outlet: MerchantOutlet, now: datetime) -> tuple[bool, bool]:
    schedule = _schedule(outlet)
    day_name = WEEKDAY_MAP.get(now.weekday(), "Senin")
    today_hours = schedule.get(day_name, "") if isinstance(schedule, dict) else ""
    return bool(today_hours), is_within_operating_hours(today_hours, now.time())


def derive_outlet_due(outlet: MerchantOutlet, now: Optional[datetime] = None) -> OutletDueState:
    now = _now(now).astimezone(outlet_timezone(outlet))
    key = merchant_key(outlet)
    live = (outlet.status_aktual or "UNKNOWN").strip().upper()
    has_schedule, within_schedule = _today_is_open(outlet, now)
    decision = evaluate_outlet_status(outlet, current_time=now, require_regular_schedule=True)

    if decision.action == ACTION_OPEN:
        return OutletDueState(
            outlet.store_id, key, now, P0_ACTIONABLE_OPEN,
            "desired OPEN tetapi Shopee masih tutup", "OPEN", live, True,
        )
    if decision.action == ACTION_CLOSE:
        return OutletDueState(
            outlet.store_id, key, now, P0_ACTIONABLE_CLOSE,
            "desired tutup tetapi Shopee masih buka", "PAUSE", live, True,
        )

    pause_until = get_active_pause_until(outlet, current_time=now)
    if pause_until:
        next_start = get_next_schedule_start(_schedule(outlet), now, not_after=pause_until, timezone=outlet_timezone(outlet))
        if next_start:
            return OutletDueState(
                outlet.store_id, key, next_start, P1_BOUNDARY,
                "menunggu boundary sesi reguler saat pause aktif", "PAUSE", live, False,
            )
        return OutletDueState(
            outlet.store_id, key, pause_until, P1_PAUSE_EXPIRY,
            "menunggu pause berakhir", "PAUSE", live, False,
        )

    if not has_schedule:
        return OutletDueState(
            outlet.store_id, key, now + timedelta(seconds=SCHEDULE_RETRY_SECONDS),
            P4_SCHEDULE_UNAVAILABLE, "jadwal Shopee belum tersedia", "UNKNOWN", live, False,
        )

    if not within_schedule:
        next_start = get_next_schedule_start(_schedule(outlet), now, timezone=outlet_timezone(outlet))
        if next_start:
            return OutletDueState(
                outlet.store_id, key, next_start, P2_NEXT_SCHEDULE,
                "menunggu jadwal reguler berikutnya", "OPEN", live, False,
            )

    status_utama = (outlet.status_utama or "OFF").strip().upper()
    if status_utama in {"OFF", "CLOSE", "CLOSED"} or outlet.penangguhan.strip().lower() == "ya":
        return OutletDueState(
            outlet.store_id, key, now + timedelta(seconds=INACTIVE_HEARTBEAT_SECONDS),
            P5_INACTIVE, "outlet tutup dan tidak membutuhkan aksi", "MANUAL_OFF", live, False,
        )

    return OutletDueState(
        outlet.store_id, key, now + timedelta(seconds=OPEN_HEARTBEAT_SECONDS),
        P3_OPEN_HEARTBEAT, "heartbeat outlet buka", "OPEN", live, False,
    )


def build_queue(outlets: Iterable[MerchantOutlet], now: Optional[datetime] = None) -> list[MerchantQueueItem]:
    now = _now(now)
    grouped: dict[tuple[str, str], list[OutletDueState]] = {}
    for outlet in outlets or []:
        state = derive_outlet_due(outlet, now)
        grouped.setdefault(state.merchant_key, []).append(state)

    queue = []
    for key, states in grouped.items():
        earliest = min(state.due_at for state in states)
        priority = max(state.priority for state in states)
        due_states = [state for state in states if state.due_at <= now]
        queue.append(MerchantQueueItem(
            merchant_key=key,
            username=key[0],
            portal_name=key[1],
            due_at=earliest,
            priority=priority,
            due_store_ids=tuple(state.store_id for state in due_states),
            outlet_count=len(states),
            actionable_count=sum(state.actionable for state in states if state.due_at <= now),
            reasons=tuple(dict.fromkeys(state.reason for state in states)),
        ))
    return sorted(queue, key=lambda item: (-item.priority, item.due_at, -item.actionable_count, item.merchant_key))


def select_next_group(queue: Iterable[MerchantQueueItem], now: Optional[datetime] = None, current_key=None) -> Optional[MerchantQueueItem]:
    now = _now(now)
    due = [item for item in queue if item.due_at <= now]
    if not due:
        return None
    due.sort(key=lambda item: (-item.priority, item.due_at, -item.actionable_count, item.merchant_key != current_key, item.merchant_key))
    return due[0]


def seconds_until_next(queue: Iterable[MerchantQueueItem], now: Optional[datetime] = None, fallback_seconds: int = 60) -> int:
    now = _now(now)
    future = [max(1, int((item.due_at - now).total_seconds())) for item in queue if item.due_at > now]
    return max(1, min(future or [int(fallback_seconds or 1)]))
