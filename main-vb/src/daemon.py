"""Long-running VB patrol scheduler."""

from __future__ import annotations

import time

from config import PATROL_INTERVAL_SECONDS
from core.logger import get_logger
# The VB worker intentionally follows bot-OC and exposes sync_all_stores.
# Keep the daemon's legacy local name for compatibility without changing the
# shared worker implementation.
from worker import sync_all_stores as patrol_once

log = get_logger("vb_daemon")


def run() -> None:
    while True:
        started = time.monotonic()
        try:
            result = patrol_once(execute_actions=True)
            log.info("VB patrol selesai: %s", result)
        except Exception as exc:
            log.exception("VB patrol gagal: %s", exc)
        elapsed = time.monotonic() - started
        time.sleep(max(0, PATROL_INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    run()
