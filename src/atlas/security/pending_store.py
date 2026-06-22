"""
Integridad HMAC para approvals persistidos (pending.json).

Formato v1 en disco:
  {"v": 1, "task": {...}, "mac": "<hmac-sha256-hex>"}

Secreto (prioridad): ATLAS_PENDING_HMAC_KEY > clave local autogenerada.
La clave autogenerada se persiste en <ATLAS_HOME>/.pending_hmac_key (permisos 0600).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any


PENDING_STORE_VERSION = 1
_LOCAL_KEY_FILENAME = ".pending_hmac_key"


def _local_key_path() -> Path:
    atlas_home = os.environ.get("ATLAS_HOME", "").strip()
    if atlas_home:
        base = Path(atlas_home)
    else:
        base = Path.home() / "atlas"
    return base / _LOCAL_KEY_FILENAME


def _load_or_create_local_key() -> bytes:
    """Lee la clave local persistente; la crea (secrets.token_hex) si no existe.

    Creación atómica: usa os.open con O_CREAT|O_EXCL para evitar ventana
    TOCTOU entre escritura y chmod.  Si el fichero ya existe, verifica que
    sus permisos sean exactamente 0600 y los corrige si son más permisivos.
    """
    path = _local_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        # Verificar permisos: rechazar (y reajustar) si son más permisivos que 0600.
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & ~0o600:
            # Otros bits activos (group/other read/write/exec) → re-chmod defensivo.
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        return path.read_bytes().strip()

    # Creación atómica: O_EXCL garantiza que si dos procesos concurrentes llegan
    # aquí solo uno crea el fichero; el otro recibirá FileExistsError y releerá.
    key = secrets.token_hex(32).encode("utf-8")
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        # Carrera: otro proceso creó el fichero entre el exists() y el open().
        return path.read_bytes().strip()
    try:
        os.write(fd, key)
    finally:
        os.close(fd)
    return key


def pending_hmac_secret() -> bytes:
    """Devuelve el secreto HMAC.

    Prioridad:
    1. Env var ATLAS_PENDING_HMAC_KEY (configuración explícita del operador).
    2. Clave local autogenerada y persistida bajo ATLAS_HOME (nunca lanza).
    """
    key = os.environ.get("ATLAS_PENDING_HMAC_KEY", "").strip()
    if key:
        return key.encode("utf-8")
    return _load_or_create_local_key()


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
