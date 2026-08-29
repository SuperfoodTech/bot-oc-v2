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
    publish({
        "type": "outlet_state_changed",
        "store_id": str(transition["store_id"]),
        "store_name": transition.get("store_name", ""),
        "owner_name": transition.get("owner_name", ""),
        "vercel_status": transition["vercel_status"],
        "pause_until": transition.get("pause_until"),
        "action": action,
        "actor": actor,
        "changed_at": transition.get("changed_at"),
        "reason": transition.get("reason", ""),
    })
