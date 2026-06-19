"""WitnessServer — endpoint HTTP que un nodo testigo independiente expone.

Cierra el lado servidor del gossip RFC 9162 (ADR-053). Hasta ahora existían el
cliente (`HttpWitnessTransport`) y la lógica de testigo (`Witness.observe`,
detección de split-view, quórum), pero el broadcast llamaba a `observe()` sobre
referencias locales en proceso. Este módulo provee el receptor real:

  cliente POST GossipMessage  →  WitnessServer
                                   ├─ parse + Witness.observe(sth)
                                   │    (verifica firma + detecta split-view)
                                   ├─ OK      → counter-firma el STH → 200 (firma)
                                   ├─ split   → 409 (conflicto detectado)
                                   └─ inválido→ 400

La counter-firma prueba que ESTE testigo también vio `root_hash` para ese
`tree_size`; el operador la acumula como evidencia de quórum
(`WitnessNetwork.counter_signature_coverage`). Si el operador presenta un STH
conflictivo (split-view) a este testigo, `observe()` lo rechaza con 409.

Stdlib pura (`http.server`, `threading`); sin deps nuevas (regla 6).

Límite honesto: cerrar split-view en la práctica exige ≥2 de estos nodos
corriendo en hosts INDEPENDIENTES del operador. Esto es el código del nodo;
el despliegue de nodos independientes es infraestructura, no código.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from atlas.security.authorization import Signer
from atlas.transparency.gossip import GossipMessage
from atlas.transparency.witness import (
    InvalidSignatureError,
    SplitViewError,
    Witness,
)


class WitnessServer:
    """Servidor HTTP que envuelve un :class:`Witness` y counter-firma STH.

    Parameters
    ----------
    witness:
        El testigo que acumula STH y detecta split-view.
    signer:
        Firmante del nodo testigo; produce la counter-signature sobre el STH.
    host, port:
        Dirección de escucha. ``port=0`` elige un puerto efímero (útil en tests).
    """

    def __init__(
        self,
        witness: Witness,
        signer: Signer,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._witness = witness
        self._signer = signer
        self._httpd = ThreadingHTTPServer((host, port), self._make_handler())
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def url(self) -> str:
        host = str(self._httpd.server_address[0])
        port = int(self._httpd.server_address[1])
        return f"http://{host}:{port}"

    def start(self) -> None:
        """Arranca el servidor en un hilo daemon."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Detiene el servidor y libera el socket."""
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "WitnessServer":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ------------------------------------------------------------------

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        witness = self._witness
        signer = self._signer

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silencio en tests
                pass

            def _reply(self, code: int, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:  # noqa: N802 (API de http.server)
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b""
                try:
                    message = GossipMessage.from_bytes(raw)
                except (ValueError, KeyError) as exc:
                    self._reply(400, f"malformed gossip message: {exc}")
                    return
                try:
                    witness.observe(message.sth)
                except InvalidSignatureError as exc:
                    self._reply(400, f"invalid STH signature: {exc}")
                    return
                except SplitViewError as exc:
                    # Conflicto: el operador mostró un STH distinto para este tree_size.
                    self._reply(409, f"split-view detected: {exc}")
                    return
                # Observado y consistente → counter-firma el STH.
                counter_sig = signer.sign(message.sth._payload())
                self._reply(200, counter_sig)

        return _Handler
