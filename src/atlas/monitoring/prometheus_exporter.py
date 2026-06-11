"""
ADR-024 — Minimal Prometheus text exposition from TelemetryBus snapshot.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.logging.telemetry_bus import TelemetryBus


class PrometheusExporter:
    """Serves /metrics on localhost only."""

    def __init__(self, telemetry: TelemetryBus, host: str = "127.0.0.1", port: int = 9091) -> None:
        self._telemetry = telemetry
        self._host = host
        self._port = port
        self._thread: threading.Thread | None = None
        self._httpd: HTTPServer | None = None

    def render_metrics(self) -> str:
        snap = self._telemetry.snapshot()
        lines: list[str] = []
        for item in snap.get("counters", []):
            name = item["name"].replace(".", "_")
            labels = ",".join(f'{k}="{v}"' for k, v in item["labels"].items())
            lbl = f"{{{labels}}}" if labels else ""
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{lbl} {item['value']}")
        for item in snap.get("gauges", []):
            name = item["name"].replace(".", "_")
            labels = ",".join(f'{k}="{v}"' for k, v in item["labels"].items())
            lbl = f"{{{labels}}}" if labels else ""
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{lbl} {item['value']}")
        # Always expose a basic up metric so monitoring can detect the exporter process
        lines.append("# TYPE atlas_up gauge")
        lines.append("atlas_up 1")
        return "\n".join(lines) + "\n"

    def start(self) -> None:
        exporter = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                try:
                    if self.path not in ("/metrics", "/"):
                        self.send_response(404)
                        self.end_headers()
                        return
                    body = exporter.render_metrics().encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # El scraper cortó la conexión a mitad de respuesta: ruido,
                    # no fallo — sin esto socketserver vuelca un traceback entero.
                    pass

            def log_message(self, *_: object) -> None:
                pass

        self._httpd = HTTPServer((self._host, self._port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="atlas-prometheus",
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
        if self._thread:
            self._thread.join(timeout=3)
