"""
Integridad HMAC para approvals persistidos (pending.json).

Formato v1 en disco:
  {"v": 1, "task": {...}, "mac": "<hmac-sha256-hex>"}

Secreto: ATLAS_PENDING_HMAC_KEY o fallback HERMES_API_KEY.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


PENDING_STORE_VERSION = 1


def pending_hmac_secret() -> bytes:
    key = os.environ.get("ATLAS_PENDING_HMAC_KEY", "").strip()
    if not key:
        key = os.environ.get("HERMES_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "Falta ATLAS_PENDING_HMAC_KEY o HERMES_API_KEY para firmar pending approvals"
        )
    return key.encode("utf-8")


def canonical_task_json(task_data: dict[str, Any]) -> bytes:
    return json.dumps(task_data, sort_keys=True, ensure_ascii=False).encode("utf-8")


def compute_pending_mac(task_data: dict[str, Any], *, secret: bytes | None = None) -> str:
    key = secret if secret is not None else pending_hmac_secret()
    return hmac.new(key, canonical_task_json(task_data), hashlib.sha256).hexdigest()


def wrap_task_payload(task_data: dict[str, Any], *, secret: bytes | None = None) -> dict[str, Any]:
    mac = compute_pending_mac(task_data, secret=secret)
    return {"v": PENDING_STORE_VERSION, "task": task_data, "mac": mac}


def unwrap_task_payload(
    data: dict[str, Any],
    *,
    secret: bytes | None = None,
) -> dict[str, Any] | None:
    """
    Devuelve task dict si MAC valido; None si legacy, tamper o formato invalido.
    """
    if "mac" in data and "task" in data:
        task_data = data.get("task")
        if not isinstance(task_data, dict):
            return None
        expected = str(data.get("mac", ""))
        try:
            actual = compute_pending_mac(task_data, secret=secret)
        except ValueError:
            return None
        if not hmac.compare_digest(actual, expected):
            return None
        return task_data

    # Legacy: JSON plano sin wrapper — rechazar (no ejecutar intents alterados)
    if "intent" in data and "id" in data:
        return None

    return None


def is_legacy_pending_file(data: dict[str, Any]) -> bool:
    return "mac" not in data and "intent" in data and "id" in data
