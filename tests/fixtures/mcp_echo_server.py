#!/usr/bin/env python3
"""Toy MCP server para tests del cliente — ADR-035.

Stdlib pura. Implementa el subset mínimo del protocolo MCP que el cliente
usa: initialize, tools/list, tools/call. Tools: echo (read), append_file
(mutate). Sin red, sin secretos. Útil para E2E del transporte y el dispatch
del registry sin depender de servers reales.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


TOOLS = [
    {
        "name": "echo",
        "description": "Devuelve el texto recibido. No muta nada.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "append_file",
        "description": "Añade una línea a un archivo. MUTA el host.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "line": {"type": "string"},
            },
            "required": ["path", "line"],
        },
    },
]


def _send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _ok(msg_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _err(msg_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def _handle(req: dict) -> None:
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        _ok(msg_id, {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "echo-test", "version": "0"},
        })
        return
    if method == "notifications/initialized":
        return  # notification, no response
    if method == "tools/list":
        _ok(msg_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "echo":
            _ok(msg_id, {"content": [{"type": "text", "text": str(args.get("text", ""))}]})
            return
        if name == "append_file":
            try:
                path = Path(args["path"])
                line = str(args.get("line", ""))
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                _ok(msg_id, {"content": [{"type": "text", "text": "ok"}]})
            except Exception as exc:  # noqa: BLE001
                _ok(msg_id, {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                })
            return
        _err(msg_id, -32601, f"unknown tool: {name}")
        return
    if msg_id is not None:
        _err(msg_id, -32601, f"unknown method: {method}")


def main() -> None:
    # Permite emitir una notificación accidental al inicio para probar que el
    # cliente las descarta correctamente.
    if os.environ.get("ECHO_PREAMBLE"):
        sys.stdout.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/log",
            "params": {"level": "info", "data": "warming up"},
        }) + "\n")
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(req, dict):
            _handle(req)


if __name__ == "__main__":
    main()
