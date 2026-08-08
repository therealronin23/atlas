"""
ADR-024 — Minimal Prometheus text exposition from TelemetryBus snapshot.
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atlas.logging.telemetry_bus import TelemetryBus

_log = logging.getLogger(__name__)


class PrometheusExporter:
    """Serves /metrics on localhost only.

    Accesorio, no dependencia: si el puerto no se puede tomar, el exportador se
    queda apagado y lo declara en `running`/`last_error`. NUNCA propaga el fallo
    de bind. Propagarlo costó el incidente del 2026-08-02 — 4.872 reinicios en
    23 h y 9.744 registros basura en el ledger Merkle, porque un `OSError`
    [Errno 98] subía hasta el CLI y mataba el orquestador entero, y systemd lo
    relanzaba contra el mismo puerto ocupado sin límite de reintentos.
    """

    def __init__(self, telemetry: TelemetryBus, host: str = "127.0.0.1", port: int = 9091) -> None:
        self._telemetry = telemetry
        self._host = host
        self._port = port
        self._thread: threading.Thread | None = None
        self._httpd: HTTPServer | None = None
        self._last_error: str | None = None

    @property
    def running(self) -> bool:
        """True sólo si el servidor tomó el puerto y su hilo está vivo."""
        return self._httpd is not None and self._thread is not None and self._thread.is_alive()

    @property
    def last_error(self) -> str | None:
        """Motivo del último arranque fallido, o None si arrancó bien."""
        return self._last_error

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

        try:
            self._httpd = HTTPServer((self._host, self._port), Handler)
        except OSError as exc:
            # EADDRINUSE, EACCES sobre puerto privilegiado, familia no
            # disponible: todas son "no hay métricas", ninguna es "no hay Atlas".
            self._httpd = None
            self._thread = None
            self._last_error = f"{type(exc).__name__}: {exc}"
            _log.warning(
                "Prometheus deshabilitado en %s:%s — %s. El runtime continúa sin métricas.",
                self._host, self._port, self._last_error,
            )
            return
        self._last_error = None
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="atlas-prometheus",
        )
        self._thread.start()

    def stop(self) -> None:
        # Idempotente y seguro sobre un exportador que nunca llegó a arrancar:
        # `start()` puede haber degradado y dejado ambos en None.
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
