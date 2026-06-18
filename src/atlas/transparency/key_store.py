"""Capa 1 de gestión de claves — clave local persistente en disco.

Carga o genera un par Ed25519 y lo persiste en ~/.atlas/.
El usuario no interactúa con esto; ocurre en background al primer arranque.

Capa 2 (TPM/Secure Enclave via OSM-025) sustituirá load_or_create()
sin cambiar nada del path de firma — misma interfaz, distinto origen.
"""
from __future__ import annotations

import os
from pathlib import Path

from atlas.security.authorization import Ed25519Signer, Ed25519Verifier


_DEFAULT_DIR = Path.home() / ".atlas"
_SUBJECT_KEY_FILE = "cosign_subject_key.bin"   # 64 bytes: 32 priv + 32 pub
_OPERATOR_KEY_FILE = "cosign_operator_key.bin"


def _key_path(filename: str, directory: Path | None) -> Path:
    d = directory or _DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


def load_or_create(
    filename: str,
    *,
    directory: Path | None = None,
) -> tuple[Ed25519Signer, Ed25519Verifier, bytes]:
    """Carga un par Ed25519 desde disco o genera uno nuevo y lo persiste.

    Devuelve (signer, verifier, public_key_bytes).
    El archivo almacena 64 bytes: primeros 32 = clave privada raw,
    últimos 32 = clave pública raw.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError("cryptography no instalado") from exc

    path = _key_path(filename, directory)

    if path.exists():
        raw = path.read_bytes()
        if len(raw) != 64:
            raise ValueError(f"Archivo de clave corrupto ({len(raw)} bytes): {path}")
        priv_bytes = raw[:32]
        pub_bytes = raw[32:]
    else:
        key = Ed25519PrivateKey.generate()
        priv_bytes = key.private_bytes_raw()
        pub_bytes = key.public_key().public_bytes_raw()
        path.write_bytes(priv_bytes + pub_bytes)
        # Solo el propietario puede leer
        path.chmod(0o600)

    return Ed25519Signer(priv_bytes), Ed25519Verifier(pub_bytes), pub_bytes


def load_or_create_subject(
    directory: Path | None = None,
) -> tuple[Ed25519Signer, Ed25519Verifier, bytes]:
    """Par de claves del sujeto (cliente). Firma cada request."""
    return load_or_create(_SUBJECT_KEY_FILE, directory=directory)


def load_or_create_operator(
    directory: Path | None = None,
) -> tuple[Ed25519Signer, Ed25519Verifier, bytes]:
    """Par de claves del operador (gateway). Firma Receipts y STHs."""
    return load_or_create(_OPERATOR_KEY_FILE, directory=directory)
