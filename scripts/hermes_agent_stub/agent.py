"""
Hermes Agent — stub HTTP server.

Implementa el contrato REST que espera HermesRestAdapter (Atlas Core, Gate C):
  GET    /health
  POST   /tasks
  GET    /tasks/{id}
  GET    /queue
  DELETE /tasks/{id}

NO ejecuta tareas reales. Devuelve respuestas simuladas para que Atlas Core
pueda hacer end-to-end por la red Tailscale en Gate C / C5.
La logica real de ejecucion vendra en Gate D (Hermes real con LLMs propios).

Variables de entorno:
  HERMES_API_KEY     secreto compartido para HMAC-SHA256 (obligatorio)
  HERMES_BIND_ADDR   default 0.0.0.0
  HERMES_PORT        default 8443
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


VERSION = "stub-0.1.0"
SIGNATURE_MAX_SKEW_S = 300


class State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.queue: dict[str, dict] = {}
        self.results: dict[str, dict] = {}


def verify_signature(secret: bytes, ts: str, body: bytes, sig_hex: str) -> bool:
    if not ts.isdigit():
        return False
    skew = abs(int(time.time()) - int(ts))
    if skew > SIGNATURE_MAX_SKEW_S:
        return False
    msg = ts.encode("utf-8") + b"\n" + body
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_hex)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_handler(secret: bytes, state: State):

    class Handler(BaseHTTPRequestHandler):
        server_version = f"hermes-agent-stub/{VERSION}"

        def log_message(self, fmt, *args):
            sys.stderr.write(f"[{now_iso()}] {self.address_string()} {fmt % args}\n")

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _check_auth(self, body: bytes) -> bool:
            ts = self.headers.get("X-Atlas-Timestamp", "")
            sig = self.headers.get("X-Atlas-Signature", "")
            return bool(ts and sig and verify_signature(secret, ts, body, sig))

        def _reply(self, status: int, payload: dict | None) -> None:
            self.send_response(status)
            if payload is None:
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raw = json.dumps(payload).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _unauth(self) -> None:
            self._reply(401, {"error": "invalid signature"})

        # --- routing ---

        def do_GET(self):
            body = b""
            if not self._check_auth(body):
                return self._unauth()
            if self.path == "/health":
                with state.lock:
                    depth = len(state.queue)
                return self._reply(200, {
                    "reachable": True, "mode": "live", "queue_depth": depth,
                    "last_seen": now_iso(), "version": VERSION,
                })
            if self.path == "/queue":
                with state.lock:
                    depth = len(state.queue)
                    next_id = next(iter(state.queue), None)
                return self._reply(200, {
                    "depth": depth, "oldest_task_age_seconds": None,
                    "next_task_id": next_id, "processing": False,
                })
            if self.path.startswith("/tasks/"):
                task_id = self.path.split("/", 2)[2]
                with state.lock:
                    result = state.results.get(task_id)
                if result is None:
                    return self._reply(404, {"error": "not found"})
                return self._reply(200, result)
            return self._reply(404, {"error": "no route"})

        def do_POST(self):
            body = self._read_body()
            if not self._check_auth(body):
                return self._unauth()
            if self.path == "/tasks":
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception:
                    return self._reply(400, {"error": "bad JSON"})
                delegation_id = payload.get("id") or str(uuid.uuid4())
                task_id = payload.get("task_id", "")
                with state.lock:
                    state.queue[delegation_id] = payload
                    state.results[task_id] = {
                        "delegation_id": delegation_id, "task_id": task_id,
                        "status": "queued", "completed_at": None,
                        "result": {"note": "stub: not executed"},
                        "skill_generated": False,
                    }
                return self._reply(200, {
                    "delegation_id": delegation_id, "accepted": True,
                    "queue_position": len(state.queue),
                    "estimated_eta_seconds": 0,
                })
            return self._reply(404, {"error": "no route"})

        def do_DELETE(self):
            body = b""
            if not self._check_auth(body):
                return self._unauth()
            if self.path.startswith("/tasks/"):
                task_id = self.path.split("/", 2)[2]
                with state.lock:
                    # task_id puede ser delegation_id o task_id; intentamos ambos
                    removed = state.queue.pop(task_id, None)
                    if removed is None:
                        for did, p in list(state.queue.items()):
                            if p.get("task_id") == task_id:
                                state.queue.pop(did)
                                removed = p
                                break
                if removed is None:
                    return self._reply(404, {"error": "not found"})
                return self._reply(204, None)
            return self._reply(404, {"error": "no route"})

    return Handler


def main() -> int:
    secret = os.environ.get("HERMES_API_KEY", "").encode()
    if not secret:
        print("ERROR: HERMES_API_KEY env var required", file=sys.stderr)
        return 2
    addr = os.environ.get("HERMES_BIND_ADDR", "0.0.0.0")
    port = int(os.environ.get("HERMES_PORT", "8443"))

    state = State()
    server = HTTPServer((addr, port), make_handler(secret, state))
    print(f"hermes-agent-stub {VERSION} listening on {addr}:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
