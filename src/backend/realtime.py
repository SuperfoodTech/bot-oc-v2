"""Small in-process event hub used by the Admin and Mitra dashboards."""

import json
from queue import Empty, Full, Queue
from threading import Lock
from typing import Callable, Dict, Iterator, Optional


EventFilter = Optional[Callable[[Dict], bool]]
_subscribers: Dict[Queue, EventFilter] = {}
_lock = Lock()
_event_number = 0


def publish(event: Dict) -> None:
    """Fan out a committed state event to connected SSE clients."""
    global _event_number
    with _lock:
        _event_number += 1
        payload = dict(event)
        payload["event_id"] = str(_event_number)
        for queue, event_filter in list(_subscribers.items()):
            if event_filter and not event_filter(payload):
                continue
            try:
                queue.put_nowait(payload)
            except Full:
                # A slow browser should receive the newest state, not stale events.
                try:
                    queue.get_nowait()
                except Empty:
                    pass
                try:
                    queue.put_nowait(payload)
                except Full:
                    pass


def stream(event_filter: EventFilter = None) -> Iterator[str]:
    """Yield SSE frames until the client disconnects."""
    queue: Queue = Queue(maxsize=64)
    with _lock:
        _subscribers[queue] = event_filter
    try:
        yield ": connected\n\n"
        while True:
            try:
                event = queue.get(timeout=20)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            yield (
                "event: outlet-state-changed\n"
                f"id: {event['event_id']}\n"
                f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"
            )
    finally:
        with _lock:
            _subscribers.pop(queue, None)


def publish_outlet_state_changed(transition: Dict, action: str, actor: str) -> None:
    payload = {
        "type": "outlet_state_changed",
        "store_id": str(transition["store_id"]),
        "store_name": transition.get("store_name", ""),
        "owner_name": transition.get("owner_name", ""),
        "vercel_status": transition["vercel_status"],
        "shopee_status": transition.get("shopee_status"),
        "is_suspended": transition.get("is_suspended"),
        "alasan_penangguhan": transition.get("alasan_penangguhan", ""),
        "pause_until": transition.get("pause_until"),
        "desired_state": transition.get("desired_state"),
        "live_state": transition.get("live_state"),
        "bot_phase": transition.get("bot_phase"),
        "schedule_available": transition.get("schedule_available"),
        "schedule_fetch_status": transition.get("schedule_fetch_status"),
        "schedule_fetch_attempted_at": transition.get("schedule_fetch_attempted_at"),
        "schedule_fetch_succeeded_at": transition.get("schedule_fetch_succeeded_at"),
        "schedule_fetch_error": transition.get("schedule_fetch_error"),
        "within_operating_schedule": transition.get("within_operating_schedule"),
        "display_toggle_on": transition.get("display_toggle_on"),
        "display_toggle_disabled": transition.get("display_toggle_disabled"),
        "display_toggle_reason": transition.get("display_toggle_reason"),
        "display_status_bucket": transition.get("display_status_bucket"),
        "display_status_label": transition.get("display_status_label"),
        "display_status_tone": transition.get("display_status_tone"),
        "display_note": transition.get("display_note"),
        "action": action,
        "actor": actor,
        "changed_at": transition.get("changed_at"),
        "reason": transition.get("reason", ""),
    }
    publish(payload)
