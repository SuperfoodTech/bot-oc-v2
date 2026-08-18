"""
main-agency/src/agency_api.py
==============================
Internal HTTP Control API untuk fm-agency container.

Berjalan di port 8082 (internal, tidak di-expose ke host).
Digunakan oleh fm-backend untuk memicu:
  - Manual force close satu outlet (tombol "Close" di dashboard)
  - Query status patrol

Pola identik dengan main-bot/src/bot_api.py.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable

log = logging.getLogger(__name__)

AGENCY_API_PORT = 8082

# Shared state — diisi oleh daemon.py
AGENCY_STATE: dict = {
    "status": "running",          # "running" | "stopped"
    "cycle_count": 0,
    "last_cycle_at": None,
    "next_cycle_in_seconds": 0,
    "last_actions": [],
}

# Callback yang diisi oleh daemon.py pada startup
_force_close_callback: Callable | None = None


def register_force_close_callback(fn: Callable) -> None:
    """Mendaftarkan fungsi yang dipanggil saat POST /force-close diterima."""
    global _force_close_callback
    _force_close_callback = fn


class _AgencyAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Redirect ke logger standar, bukan stderr
        log.debug("[AGENCY-API] %s", fmt % args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send_json({
                "success": True,
                "agency_state": AGENCY_STATE,
            })
        elif self.path == "/health":
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/force-close":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(body)
            except Exception:
                self._send_json({"error": "Invalid JSON"}, 400)
                return

            store_id = payload.get("store_id", "")
            if not store_id:
                self._send_json({"error": "store_id is required"}, 400)
                return

            if _force_close_callback is None:
                self._send_json({"error": "Force close handler not registered"}, 503)
                return

            try:
                result = _force_close_callback(store_id)
                self._send_json({"success": True, "result": result})
            except Exception as e:
                log.error("[AGENCY-API] Force close error: %s", e)
                self._send_json({"success": False, "error": str(e)}, 500)

        else:
            self._send_json({"error": "Not found"}, 404)


def start_agency_api_server_background(port: int = AGENCY_API_PORT) -> None:
    """Starts the agency control API server in a daemon background thread."""
    server = HTTPServer(("0.0.0.0", port), _AgencyAPIHandler)

    def _serve():
        log.info("[AGENCY-API] Internal control server listening on port %d.", port)
        server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True, name="agency-api-server")
    t.start()
