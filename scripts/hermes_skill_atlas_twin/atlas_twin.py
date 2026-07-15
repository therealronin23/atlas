#!/usr/bin/env python3
"""Hermes-side client for Atlas's signed and audited twin API.

The client is deliberately stdlib-only. It accepts only private/Tailscale
Atlas endpoints, bypasses ambient HTTP proxies, refuses redirects, signs the
exact request bytes and bounds response memory.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import hmac
import ipaddress
import json
import os
import stat
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


MAX_RESPONSE_BYTES = 1_048_576
MAX_WRITE_BYTES = 1_048_576
MIN_SECRET_BYTES = 32
ALLOWED_ENDPOINTS = frozenset({"health", "shell", "file", "intent", "audit", "browser"})
_ALLOWED_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "::1/128",
        "fc00::/7",
    )
)


class TwinClientError(RuntimeError):
    """Safe, operator-facing twin transport failure."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Treat every redirect as a refusal so signed bodies never change origin."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _read_env_file(path_value: str | None) -> dict[str, str]:
    """Read only the two twin variables from a secured dotenv file.

    The file is parsed as data, never sourced. This supports direct operator
    probes where there is no gateway parent process to inject EnvironmentFile.
    """
    if not path_value:
        return {}
    path = os.path.abspath(os.path.expanduser(path_value))
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise TwinClientError("could not securely open the twin env file") from exc
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(fd)
        raise TwinClientError("twin env file must be a regular non-symlink file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        os.close(fd)
        raise TwinClientError("twin env file must not be readable by group or others")
    if metadata.st_size > MAX_RESPONSE_BYTES:
        os.close(fd)
        raise TwinClientError("twin env file is too large")
    selected: dict[str, str] = {}
    with os.fdopen(fd, encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, raw_value = line.partition("=")
            key = key.strip()
            if not separator or key not in {"ATLAS_DASHBOARD_URL", "HERMES_API_KEY"}:
                continue
            if key in selected:
                raise TwinClientError(f"duplicate twin env key at line {line_number}")
            value = raw_value.strip()
            if value[:1] in {"'", '"'}:
                try:
                    decoded = ast.literal_eval(value)
                except (SyntaxError, ValueError) as exc:
                    raise TwinClientError(
                        f"invalid quoted twin env value at line {line_number}"
                    ) from exc
                if not isinstance(decoded, str):
                    raise TwinClientError("twin env values must be strings")
                value = decoded
            if "\x00" in value or "\n" in value or "\r" in value:
                raise TwinClientError("twin env values must be single-line strings")
            selected[key] = value
    return selected


def _host_is_allowed(hostname: str) -> bool:
    normalized = hostname.casefold().rstrip(".")
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    if normalized.endswith(".ts.net"):
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return any(address in network for network in _ALLOWED_NETWORKS)


def validate_base_url(value: str) -> str:
    """Return a normalized private Atlas origin or reject it fail-closed."""
    candidate = value.strip()
    if not candidate or any(char.isspace() for char in candidate):
        raise TwinClientError("ATLAS_DASHBOARD_URL is required and must not contain whitespace")
    try:
        parsed = urlsplit(candidate)
        _ = parsed.port
    except ValueError as exc:
        raise TwinClientError("invalid Atlas URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise TwinClientError("Atlas URL must use http or https")
    if (
        parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise TwinClientError("Atlas URL must be a credential-free origin")
    if not _host_is_allowed(parsed.hostname):
        raise TwinClientError("Atlas URL must be loopback, private, or a Tailscale address")
    return candidate.rstrip("/")


def encode_body(payload: dict[str, Any]) -> bytes:
    """Canonical request bytes; these exact bytes are signed and transmitted."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def signed_headers(
    *, secret: str, timestamp: str, nonce: str, body: bytes,
) -> dict[str, str]:
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise TwinClientError("HERMES_API_KEY must contain at least 32 bytes")
    signed = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body
    signature = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Hermes-Signature": signature,
        "X-Hermes-Timestamp": timestamp,
        "X-Hermes-Nonce": nonce,
    }


def _bounded_read(response: Any) -> bytes:
    length_raw = response.headers.get("Content-Length")
    if length_raw:
        try:
            if int(length_raw) > MAX_RESPONSE_BYTES:
                raise TwinClientError("Atlas response is too large")
        except ValueError as exc:
            raise TwinClientError("Atlas returned an invalid Content-Length") from exc
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise TwinClientError("Atlas response is too large")
    return data


class AtlasTwinClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        secret: str | None = None,
        timeout: float = 10.0,
        env_file: str | None = None,
    ) -> None:
        if env_file is None:
            hermes_home = os.environ.get("HERMES_HOME", "").strip()
            env_file = os.path.join(hermes_home, ".env") if hermes_home else None
        file_values = _read_env_file(env_file)
        self.base_url = validate_base_url(
            base_url
            if base_url is not None
            else os.environ.get("ATLAS_DASHBOARD_URL", "")
            or file_values.get("ATLAS_DASHBOARD_URL", "")
        )
        self.secret = (
            secret
            if secret is not None
            else os.environ.get("HERMES_API_KEY", "")
            or file_values.get("HERMES_API_KEY", "")
        ).strip()
        if len(self.secret.encode("utf-8")) < MIN_SECRET_BYTES:
            raise TwinClientError("HERMES_API_KEY must contain at least 32 bytes")
        if not 0.1 <= timeout <= 60:
            raise TwinClientError("timeout must be between 0.1 and 60 seconds")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirectHandler(),
        )

    def post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise TwinClientError("unsupported Atlas endpoint")
        body = encode_body(payload)
        timestamp = datetime.now(timezone.utc).isoformat()
        nonce = uuid.uuid4().hex
        request = urllib.request.Request(
            f"{self.base_url}/api/exec/{endpoint}",
            data=body,
            method="POST",
            headers=signed_headers(
                secret=self.secret,
                timestamp=timestamp,
                nonce=nonce,
                body=body,
            ),
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = _bounded_read(response)
        except urllib.error.HTTPError as exc:
            # A redirect also arrives here because NoRedirectHandler refuses it.
            try:
                detail = exc.read(4096).decode("utf-8", "replace")
            except Exception:
                detail = ""
            suffix = f": {detail}" if detail else ""
            raise TwinClientError(f"Atlas refused the request ({exc.code}){suffix}") from exc
        except urllib.error.URLError as exc:
            raise TwinClientError(f"Atlas is unreachable: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TwinClientError("Atlas request timed out") from exc

        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TwinClientError("Atlas returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise TwinClientError("Atlas returned a non-object JSON response")
        return decoded


def _payload_from_args(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    command = args.operation
    if command == "health":
        return "health", {}
    if command == "intent":
        return "intent", {"intent": args.intent}
    if command == "shell":
        if not 1 <= args.command_timeout <= 600:
            raise TwinClientError("command timeout must be between 1 and 600 seconds")
        return "shell", {
            "command": args.command,
            "args": args.arguments,
            "timeout_s": args.command_timeout,
        }
    if command == "file-read":
        return "file", {"action": "read", "path": args.path}
    if command == "file-write":
        raw = args.data.encode("utf-8")
        if len(raw) > MAX_WRITE_BYTES:
            raise TwinClientError("file data exceeds 1 MiB")
        return "file", {"action": "write", "path": args.path, "data": args.data}
    if command == "browser":
        field = {
            "navigate": "url",
            "extract": "selector",
            "screenshot": "name",
        }[args.action]
        return "browser", {"action": args.action, field: args.target}
    if command == "audit":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            raise TwinClientError("--payload must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise TwinClientError("--payload must be a JSON object")
        return "audit", {
            "action": args.action,
            "result": args.result,
            "risk_level": args.risk,
            "payload": payload,
        }
    raise TwinClientError("unsupported operation")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Atlas through the signed twin channel")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--timeout", type=float, default=10.0)
    operations = parser.add_subparsers(dest="operation", required=True)
    operations.add_parser("health")

    intent = operations.add_parser("intent")
    intent.add_argument("intent")

    shell = operations.add_parser("shell")
    shell.add_argument("--command-timeout", type=int, default=30)
    shell.add_argument("command")
    shell.add_argument("arguments", nargs=argparse.REMAINDER)

    file_read = operations.add_parser("file-read")
    file_read.add_argument("path")
    file_write = operations.add_parser("file-write")
    file_write.add_argument("path")
    file_write.add_argument("--data", required=True)

    browser = operations.add_parser("browser")
    browser.add_argument("action", choices=["navigate", "extract", "screenshot"])
    browser.add_argument("target")

    audit = operations.add_parser("audit")
    audit.add_argument("action")
    audit.add_argument(
        "--result",
        default="success",
        choices=["success", "failure", "blocked", "pending", "refused"],
    )
    audit.add_argument(
        "--risk",
        default="safe",
        choices=["safe", "moderate", "high", "critical"],
    )
    audit.add_argument("--payload", default="{}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        endpoint, payload = _payload_from_args(args)
        client = AtlasTwinClient(
            base_url=args.base_url,
            timeout=args.timeout,
            env_file=args.env_file,
        )
        result = client.post(endpoint, payload)
    except TwinClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
