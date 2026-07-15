"""Security and contract tests for the repository-owned Hermes twin skill."""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from atlas.interfaces.exec_api import _verify_signature


REPO = Path(__file__).resolve().parents[1]
CLIENT_PATH = REPO / "scripts" / "hermes_skill_atlas_twin" / "atlas_twin.py"
SKILL_PATH = CLIENT_PATH.with_name("SKILL.md")


@pytest.fixture(scope="module")
def twin_client_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("atlas_twin_skill_client", CLIENT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_is_a_real_hermes_skill_with_no_fictitious_tool_contract() -> None:
    raw = SKILL_PATH.read_text(encoding="utf-8")
    assert raw.startswith("---\nname: atlas-twin\n")
    assert "${HERMES_SKILL_DIR}/atlas_twin.py" in raw
    assert "tool atlas_twin" not in raw.lower()
    assert "health" in raw
    assert "No afirmes" in raw


@pytest.mark.parametrize(
    "url",
    [
        "http://100.85.236.58:7331",
        "https://atlas.tailnet-name.ts.net",
        "http://127.0.0.1:7331/",
        "http://10.0.0.2:7331",
        "http://[fd00::1]:7331",
    ],
)
def test_private_or_tailnet_atlas_urls_are_accepted(
    twin_client_module: ModuleType, url: str,
) -> None:
    assert twin_client_module.validate_base_url(url).startswith(("http://", "https://"))


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://203.0.113.8:7331",
        "http://user:pass@100.85.236.58:7331",
        "http://100.85.236.58:7331/api/exec",
        "file:///etc/passwd",
        "http://100.85.236.58:7331?next=evil",
    ],
)
def test_public_ambiguous_or_credentialed_atlas_urls_are_rejected(
    twin_client_module: ModuleType, url: str,
) -> None:
    with pytest.raises(twin_client_module.TwinClientError):
        twin_client_module.validate_base_url(url)


def test_signature_is_byte_exact_with_atlas_contract(
    twin_client_module: ModuleType,
) -> None:
    secret = "a" * 64
    body = twin_client_module.encode_body({"intent": "área exacta", "n": 1})
    timestamp = "2026-07-16T00:00:00+00:00"
    nonce = "0123456789abcdef0123456789abcdef"

    headers = twin_client_module.signed_headers(
        secret=secret,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )

    expected = hmac.new(
        secret.encode(),
        timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body,
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Hermes-Signature"] == expected
    assert _verify_signature(secret.encode(), timestamp, nonce, body, expected)


def test_client_disables_proxies_and_redirects(
    twin_client_module: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Headers:
        def get(self, _name: str, default: str | None = None) -> str | None:
            return default

    class _Response:
        headers = _Headers()
        status = 200

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b'{"ok":true}'

    class _Opener:
        def open(self, request: object, timeout: float) -> _Response:
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response()

    def _build_opener(*handlers: object) -> _Opener:
        captured["handlers"] = handlers
        return _Opener()

    monkeypatch.setattr(twin_client_module.urllib.request, "build_opener", _build_opener)
    client = twin_client_module.AtlasTwinClient(
        base_url="http://100.85.236.58:7331",
        secret="b" * 64,
        timeout=3,
    )
    assert client.post("health", {}) == {"ok": True}

    handlers = captured["handlers"]
    assert any(
        isinstance(handler, twin_client_module.urllib.request.ProxyHandler)
        and handler.proxies == {}
        for handler in handlers
    )
    assert any(isinstance(handler, twin_client_module.NoRedirectHandler) for handler in handlers)
    request = captured["request"]
    assert request.full_url == "http://100.85.236.58:7331/api/exec/health"
    assert "b" * 64 not in json.dumps(dict(request.header_items()))


def test_endpoint_is_an_allowlist_not_an_arbitrary_path(
    twin_client_module: ModuleType,
) -> None:
    client = twin_client_module.AtlasTwinClient(
        base_url="http://100.85.236.58:7331",
        secret="c" * 64,
    )
    with pytest.raises(twin_client_module.TwinClientError):
        client.post("../../admin", {})


def test_response_size_is_bounded(
    twin_client_module: ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Headers:
        def get(self, name: str, default: str | None = None) -> str | None:
            if name.lower() == "content-length":
                return str(twin_client_module.MAX_RESPONSE_BYTES + 1)
            return default

    class _Response:
        headers = _Headers()
        status = 200

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    class _Opener:
        def open(self, _request: object, timeout: float) -> _Response:
            assert timeout == 10
            return _Response()

    monkeypatch.setattr(
        twin_client_module.urllib.request,
        "build_opener",
        lambda *_handlers: _Opener(),
    )
    client = twin_client_module.AtlasTwinClient(
        base_url="http://100.85.236.58:7331",
        secret="d" * 64,
    )
    with pytest.raises(twin_client_module.TwinClientError, match="too large"):
        client.post("health", {})


def test_env_file_is_parsed_as_data_and_requires_private_permissions(
    twin_client_module: ModuleType, tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'ATLAS_DASHBOARD_URL="http://100.85.236.58:7331"\n'
        f'HERMES_API_KEY="{"e" * 64}"\n',
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    client = twin_client_module.AtlasTwinClient(env_file=str(env_file))
    assert client.base_url == "http://100.85.236.58:7331"

    env_file.chmod(0o644)
    with pytest.raises(twin_client_module.TwinClientError, match="group or others"):
        twin_client_module.AtlasTwinClient(env_file=str(env_file))


def test_env_file_symlink_is_rejected(
    twin_client_module: ModuleType, tmp_path: Path,
) -> None:
    target = tmp_path / "target.env"
    target.write_text(
        'ATLAS_DASHBOARD_URL="http://100.85.236.58:7331"\n'
        f'HERMES_API_KEY="{"f" * 64}"\n',
        encoding="utf-8",
    )
    target.chmod(0o600)
    link = tmp_path / ".env"
    link.symlink_to(target)
    with pytest.raises(twin_client_module.TwinClientError, match="securely open"):
        twin_client_module.AtlasTwinClient(env_file=str(link))
