"""El exportador Prometheus es un ACCESORIO: no puede tumbar el orquestador.

Incidente medido (2026-08-02): el daemon se reinició 4.872 veces en 23 h, cada
13 s, y escribió 9.744 registros al ledger Merkle — el 40% del ledger entero.
Causa única: `HTTPServer((host, port))` lanzaba `OSError: [Errno 98] Address
already in use`, la excepción subía por `_start_prometheus_if_enabled` ->
`ServiceRunner.start()` -> `run_forever()` -> CLI, y mataba el proceso. Con
`Restart=always` y sin `StartLimitBurst`, systemd lo relanzaba contra el mismo
puerto ocupado, para siempre. 832 de los 836 tracebacks de `.atlas.err` son ese
`OSError`.

Ninguno de los 5.121 tests verdes tocaba este camino: el exportador no tenía
test alguno.

Invariante que fija este módulo: métricas caídas degradan la observabilidad,
nunca la disponibilidad.
"""

from __future__ import annotations

import socket
import threading

import pytest

from atlas.monitoring.prometheus_exporter import PrometheusExporter


class _FakeTelemetry:
    def snapshot(self) -> dict[str, list[dict[str, object]]]:
        return {"counters": [], "gauges": []}


def _puerto_ocupado() -> tuple[socket.socket, int]:
    """Un socket que ya escucha, para forzar EADDRINUSE de verdad (sin mocks)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    return sock, sock.getsockname()[1]


def test_puerto_ocupado_no_lanza() -> None:
    """El caso exacto del incidente: el puerto está tomado y `start()` NO lanza."""
    ocupante, port = _puerto_ocupado()
    try:
        exporter = PrometheusExporter(_FakeTelemetry(), host="127.0.0.1", port=port)

        exporter.start()  # antes: OSError [Errno 98] -> proceso muerto

        assert exporter.running is False
        assert exporter.last_error is not None
        assert "98" in exporter.last_error or "in use" in exporter.last_error.lower()
    finally:
        ocupante.close()


def test_puerto_ocupado_deja_el_runtime_utilizable() -> None:
    """Tras el fallo de bind no queda hilo huérfano ni servidor a medias, y
    `stop()` es seguro — el runtime sigue su curso."""
    ocupante, port = _puerto_ocupado()
    hilos_antes = threading.active_count()
    try:
        exporter = PrometheusExporter(_FakeTelemetry(), host="127.0.0.1", port=port)
        exporter.start()

        exporter.stop()  # idempotente sobre un exportador que nunca arrancó

        assert threading.active_count() == hilos_antes
    finally:
        ocupante.close()


def test_puerto_libre_sigue_sirviendo_metricas() -> None:
    """La degradación no puede haberse llevado por delante el camino feliz."""
    import urllib.request

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    exporter = PrometheusExporter(_FakeTelemetry(), host="127.0.0.1", port=port)
    exporter.start()
    try:
        assert exporter.running is True
        assert exporter.last_error is None
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as r:
            body = r.read().decode()
        assert "atlas_up 1" in body
    finally:
        exporter.stop()


def test_render_metrics_no_depende_del_servidor() -> None:
    """Renderizar métricas es puro: funciona aunque el bind haya fallado."""
    ocupante, port = _puerto_ocupado()
    try:
        exporter = PrometheusExporter(_FakeTelemetry(), host="127.0.0.1", port=port)
        exporter.start()

        assert "atlas_up 1" in exporter.render_metrics()
    finally:
        ocupante.close()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_solo_escucha_en_loopback(host: str) -> None:
    """ADR-024: /metrics no sale de loopback. Un exportador degradado tampoco
    puede relajar eso por accidente."""
    exporter = PrometheusExporter(_FakeTelemetry(), host=host, port=0)
    assert exporter._host in ("127.0.0.1", "localhost")
