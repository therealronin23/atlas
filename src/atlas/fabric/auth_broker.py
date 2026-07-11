"""AuthBroker — Atlas NUNCA persiste secretos en claro. v1 ni siquiera acepta
el valor del secreto: el flujo guiado le dice al usuario DÓNDE ponerlo
(variable de entorno / gestor del SO) y guarda solo la referencia opaca.

Vault propio = BLOCKED_BY_DESIGN hasta ADR dedicado (no se finge keyring).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Prefijos/formas conocidas de material secreto. Si algo así llega a un campo
# de texto del fabric, se rechaza: el usuario debe usar el flujo de referencia.
_SECRET_PATTERNS = [
    re.compile(r"^sk-[A-Za-z0-9_-]{16,}"),          # OpenAI/Anthropic style
    re.compile(r"^(ghp|gho|ghu|ghs)_[A-Za-z0-9]{20,}"),  # GitHub
    re.compile(r"^AKIA[0-9A-Z]{16}"),                # AWS access key
    re.compile(r"^xox[baprs]-"),                     # Slack
    re.compile(r"^AIza[0-9A-Za-z_-]{30,}"),          # Google API key
    re.compile(r"^-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."),  # JWT
]


def looks_like_secret(value: str) -> bool:
    candidate = value.strip()
    if any(p.match(candidate) for p in _SECRET_PATTERNS):
        return True
    # Cadena larga sin espacios con alta mezcla alfanumérica: sospechosa.
    return len(candidate) >= 40 and " " not in candidate and any(
        c.isdigit() for c in candidate
    ) and any(c.isalpha() for c in candidate)


class SecretRejected(ValueError):
    """Se intentó pasar material secreto en claro por un campo no seguro."""


def _default_refs_path() -> Path:
    home = Path(os.environ.get("ATLAS_HOME", "~/atlas")).expanduser()
    return home / "connections" / "credential_refs.json"


class AuthBroker:
    """Emite y valida referencias `env:<VAR>` sin tocar el secreto."""

    def __init__(self, refs_path: Path | None = None) -> None:
        self._path = refs_path or _default_refs_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        data: list[dict[str, Any]] = json.loads(self._path.read_text(encoding="utf-8"))
        return data

    def _save(self, refs: list[dict[str, Any]]) -> None:
        self._path.write_text(
            json.dumps(refs, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def create_env_reference(
        self, provider: str, env_var: str, scopes: list[str]
    ) -> dict[str, Any]:
        """Registra que el secreto de `provider` vivirá en $<env_var>.

        Rechaza cualquier cosa que parezca el secreto en sí.
        """
        for field_name, value in (("provider", provider), ("env_var", env_var)):
            if looks_like_secret(value):
                raise SecretRejected(
                    f"{field_name} parece material secreto; usa el nombre de la "
                    "variable, jamás el valor"
                )
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", env_var):
            raise SecretRejected(
                "env_var debe ser un nombre de variable (MAYUSCULAS_CON_GUION_BAJO)"
            )
        ref = {
            "credential_ref_id": f"credref_{uuid.uuid4().hex[:10]}",
            "provider": provider,
            "reference": f"env:{env_var}",
            "scopes": scopes,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_backend": "env",
            "plaintext_stored": False,
        }
        refs = self._load()
        refs.append(ref)
        self._save(refs)
        return ref

    def list_references(self) -> list[dict[str, Any]]:
        return self._load()

    def reference_available(self, credential_ref_id: str) -> bool:
        """True si la variable referenciada existe en el entorno actual.
        NUNCA devuelve el valor."""
        for ref in self._load():
            if ref["credential_ref_id"] == credential_ref_id:
                var = str(ref["reference"]).removeprefix("env:")
                return bool(os.environ.get(var))
        return False

    def manual_secret_capture_flow(self, provider: str, env_var: str) -> dict[str, Any]:
        """Flujo guiado declarativo: pasos que el USUARIO ejecuta fuera de
        Atlas. Atlas no ve el secreto en ningún paso."""
        return {
            "provider": provider,
            "kind": "manual_secret_capture",
            "atlas_sees_secret": False,
            "steps": [
                {"step": 1, "who": "user",
                 "action": f"Crea/copia la API key en el panel de {provider}"},
                {"step": 2, "who": "user",
                 "action": f"Exporta la clave: añade {env_var}=<tu_clave> a tu "
                           "entorno local (p.ej. ~/.config/atlas/env)"},
                {"step": 3, "who": "atlas",
                 "action": f"Atlas registra la referencia env:{env_var} y "
                           "comprueba que existe SIN leer su valor"},
            ],
        }
