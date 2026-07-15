"""Regresiones de transporte HTTP para el sink SSRF de AtlasExecutor."""

from __future__ import annotations

import socket
import threading
import urllib.parse
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from atlas.governance.permission_profile import PermissionProfile
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.capabilities import CapabilityIssuer, NetworkCapability
from atlas.security.executor import AtlasExecutor, ExecutorError
from atlas.security.sandbox import LayeredIsolationSandbox
from atlas.security.ssrf_bridge import BridgeDecision, SSRFBridge


ResponseWriter = Callable[[BaseHTTPRequestHandler], None]


@contextmanager
def _http_server(write_response: ResponseWriter) -> Iterator[ThreadingHTTPServer]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
            write_response(self)

        def log_message(self, _format: str, *args: object) -> None:
            del args

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _send(handler: BaseHTTPRequestHandler, body: bytes = b"ok") -> None:
    handler.send_response(200)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler: BaseHTTPRequestHandler, target: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", target)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _make_executor(tmp_path: Path, bridge: SSRFBridge) -> AtlasExecutor:
    workspace = tmp_path / "workspace"
    (workspace / "tmp").mkdir(parents=True)
    (workspace / "memory" / "merkle").mkdir(parents=True)
    (workspace / "config").mkdir()
    permissions = workspace / "config" / "permissions.yaml"
    permissions.write_text(
        "workspace:\n  auto_write:\n    - tmp/\n  confirm_write: []\n"
        "  read_only: []\n  read_extended: []\n"
        "absolute_blocks: []\nsystem_read_allowed: []\n"
        "telegram:\n  authorized_chat_ids: []\n"
        "shell_allowlist: []\n"
    )
    profile = PermissionProfile(permissions, workspace)
    issuer = CapabilityIssuer(profile, bridge)
    return AtlasExecutor(
        issuer,
        MerkleLogger(workspace / "memory" / "merkle"),
        LayeredIsolationSandbox(workspace),
        ssrf_bridge=bridge,
    )


def _cap(url: str) -> NetworkCapability:
    return NetworkCapability(url=url, method="GET", domain="safe.example")


class _PinnedLocalBridge(SSRFBridge):
    """Seam local: sólo el hostname señuelo queda fijado al servidor del test."""

    def __init__(self, hostname: str = "safe.example") -> None:
        super().__init__(extra_allowed={hostname})
        self.hostname = hostname
        self.checked: list[str] = []

    def check(self, url: str) -> BridgeDecision:
        self.checked.append(url)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in {"http", "https"} and parsed.hostname == self.hostname:
            return BridgeDecision(
                allowed=True,
                url=url,
                reason="host local fijado por el test",
                domain=self.hostname,
                pinned_ip="127.0.0.1",
            )
        return super().check(url)


class _PinnedHostsBridge(SSRFBridge):
    def __init__(self, *hostnames: str) -> None:
        super().__init__(extra_allowed=set(hostnames))
        self.hostnames = frozenset(hostnames)

    def check(self, url: str) -> BridgeDecision:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.hostname or ""
        if parsed.scheme in {"http", "https"} and domain in self.hostnames:
            return BridgeDecision(
                allowed=True,
                url=url,
                reason="host local fijado por el test",
                domain=domain,
                pinned_ip="127.0.0.1",
            )
        return super().check(url)


def _resolve_safe_host_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    real_getaddrinfo = socket.getaddrinfo

    def local_getaddrinfo(host: str, port: int | str | None, *args: object, **kwargs: object):
        if host == "safe.example":
            return real_getaddrinfo("127.0.0.1", port, *args, **kwargs)
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_getaddrinfo)


def test_http_connection_uses_validated_ip_not_rebound_hostname(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una segunda resolución host->loopback no debe alcanzar el servidor local."""
    hits: list[str] = []

    def serve(handler: BaseHTTPRequestHandler) -> None:
        hits.append(handler.path)
        _send(handler, b"internal")

    with _http_server(serve) as server:
        port = int(server.server_address[1])
        url = f"http://api.groq.com:{port}/private"
        bridge = SSRFBridge()
        executor = _make_executor(tmp_path, bridge)

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *_args, **_kwargs: [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
            ],
        )

        def guarded_create_connection(
            address: tuple[str, int],
            timeout: float | object = socket._GLOBAL_DEFAULT_TIMEOUT,
            source_address: tuple[str, int] | None = None,
            **_kwargs: object,
        ) -> socket.socket:
            host, destination_port = address
            if host == "93.184.216.34":
                raise OSError("IP señuelo: salida externa deshabilitada en el test")
            if host != "api.groq.com":
                raise AssertionError(f"destino inesperado: {host}")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                sock.settimeout(float(timeout))
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(("127.0.0.1", destination_port))
            return sock

        monkeypatch.setattr(socket, "create_connection", guarded_create_connection)

        with pytest.raises(ExecutorError):
            executor.execute_network(_cap(url), timeout_s=1)

    assert hits == []


def test_redirect_to_loopback_is_revalidated_before_second_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_hits: list[str] = []

    def target(handler: BaseHTTPRequestHandler) -> None:
        target_hits.append(handler.path)
        _send(handler, b"secret")

    with _http_server(target) as target_server:
        target_port = int(target_server.server_address[1])

        def source(handler: BaseHTTPRequestHandler) -> None:
            _redirect(handler, f"http://127.0.0.1:{target_port}/secret")

        with _http_server(source) as source_server:
            source_port = int(source_server.server_address[1])
            url = f"http://safe.example:{source_port}/start"
            bridge = _PinnedLocalBridge()
            executor = _make_executor(tmp_path, bridge)
            _resolve_safe_host_locally(monkeypatch)

            with pytest.raises(ExecutorError, match="SSRF.*redirect|redirect.*SSRF"):
                executor.execute_network(_cap(url), timeout_s=1)

    assert target_hits == []


def test_cross_scheme_redirect_is_blocked_without_second_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def source(handler: BaseHTTPRequestHandler) -> None:
        _redirect(handler, "https://safe.example/next")

    with _http_server(source) as server:
        port = int(server.server_address[1])
        url = f"http://safe.example:{port}/start"
        bridge = _PinnedLocalBridge()
        executor = _make_executor(tmp_path, bridge)
        _resolve_safe_host_locally(monkeypatch)

        real_create_connection = socket.create_connection
        destinations: list[tuple[str, int]] = []

        def record_connection(address: tuple[str, int], *args: object, **kwargs: object):
            destinations.append(address)
            return real_create_connection(address, *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", record_connection)

        with pytest.raises(ExecutorError, match="cambio de esquema"):
            executor.execute_network(_cap(url), timeout_s=1)

    assert len(destinations) == 1


def test_same_scheme_redirect_is_revalidated_and_preserves_host_header(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_hosts: list[str] = []

    def serve(handler: BaseHTTPRequestHandler) -> None:
        if handler.path == "/start":
            _redirect(handler, "/final")
            return
        received_hosts.append(handler.headers["Host"])
        _send(handler, b"done")

    with _http_server(serve) as server:
        port = int(server.server_address[1])
        start_url = f"http://safe.example:{port}/start"
        final_url = f"http://safe.example:{port}/final"
        bridge = _PinnedLocalBridge()
        executor = _make_executor(tmp_path, bridge)
        _resolve_safe_host_locally(monkeypatch)

        response = executor.execute_network(_cap(start_url), timeout_s=1)

    assert response.body == b"done"
    assert bridge.checked == [start_url, final_url]
    assert received_hosts == [f"safe.example:{port}"]


def test_user_host_header_cannot_override_original_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_hosts: list[str] = []

    def serve(handler: BaseHTTPRequestHandler) -> None:
        received_hosts.append(handler.headers["Host"])
        _send(handler)

    with _http_server(serve) as server:
        port = int(server.server_address[1])
        url = f"http://safe.example:{port}/"
        bridge = _PinnedLocalBridge()
        executor = _make_executor(tmp_path, bridge)
        _resolve_safe_host_locally(monkeypatch)

        executor.execute_network(
            _cap(url),
            headers={"Host": "internal-admin.invalid"},
            timeout_s=1,
        )

    assert received_hosts == [f"safe.example:{port}"]


def test_redirect_cannot_expand_capability_to_another_allowed_host(
    tmp_path: Path,
) -> None:
    target_hits: list[str] = []

    def target(handler: BaseHTTPRequestHandler) -> None:
        target_hits.append(handler.path)
        _send(handler, b"other origin")

    with _http_server(target) as target_server:
        target_port = int(target_server.server_address[1])

        def source(handler: BaseHTTPRequestHandler) -> None:
            _redirect(handler, f"http://other.example:{target_port}/final")

        with _http_server(source) as source_server:
            source_port = int(source_server.server_address[1])
            url = f"http://safe.example:{source_port}/start"
            bridge = _PinnedHostsBridge("safe.example", "other.example")
            executor = _make_executor(tmp_path, bridge)

            with pytest.raises(ExecutorError, match="cambio de host"):
                executor.execute_network(
                    _cap(url),
                    headers={"Authorization": "Bearer must-not-leak"},
                    timeout_s=1,
                )

    assert target_hits == []


def test_redirect_loop_stops_at_a_small_fixed_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    def loop(handler: BaseHTTPRequestHandler) -> None:
        requests.append(handler.path)
        _redirect(handler, "/loop")

    with _http_server(loop) as server:
        port = int(server.server_address[1])
        url = f"http://safe.example:{port}/loop"
        bridge = _PinnedLocalBridge()
        executor = _make_executor(tmp_path, bridge)
        _resolve_safe_host_locally(monkeypatch)

        with pytest.raises(ExecutorError, match="demasiados redirects"):
            executor.execute_network(_cap(url), timeout_s=1)

    assert len(requests) <= 6
