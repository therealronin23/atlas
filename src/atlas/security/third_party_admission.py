"""ADC-WO-124 — receipts de admisión gobernada para MCP de terceros.

`SentinelGate` (ADR-038) veta por defecto cualquier ejecutable de terceros
sin artefacto materializado, hash, receipt e aislamiento. Este módulo es el
ÚNICO lugar que puede producir un receipt capaz de levantar ese veto —
`SentinelGate` solo lo LEE (``load_receipt``), nunca lo crea. Admitir o
revocar es una acción explícita, auditada en Merkle, disparada por un
humano (CLI ``atlas mcp admit-third-party`` / ``revoke-third-party``).

Invariante duro: el hash del ejecutable se recomputa SIEMPRE desde los
bytes reales del artefacto en el momento de admitir — nunca se confía un
hash declarado. Sin esto, "admitir por hash" sería teatro.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


class ReceiptIntegrityError(RuntimeError):
    """El receipt existe pero no es una autoridad válida (fail-closed)."""


@dataclass(frozen=True)
class ThirdPartyReceipt:
    server: str
    cmd: tuple[str, ...]
    cwd: str | None
    env_extra: dict[str, str]
    env_passthrough: tuple[str, ...]
    executable_sha256: str
    package: str
    version: str
    license: str
    dependency_inventory: tuple[str, ...]
    static_scan_verdict: str
    xvfb_only: bool
    admitted_by: str
    admitted_at: str
    merkle_receipt_id: str
    revoked: bool = False
    revoked_by: str | None = None
    revoked_at: str | None = None
    revoke_merkle_receipt_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["cmd"] = list(self.cmd)
        data["env_passthrough"] = list(self.env_passthrough)
        data["dependency_inventory"] = list(self.dependency_inventory)
        return data

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "ThirdPartyReceipt":
        return ThirdPartyReceipt(
            server=data["server"],
            cmd=tuple(data["cmd"]),
            cwd=data["cwd"],
            env_extra=dict(data["env_extra"]),
            env_passthrough=tuple(data["env_passthrough"]),
            executable_sha256=data["executable_sha256"],
            package=data["package"],
            version=data["version"],
            license=data["license"],
            dependency_inventory=tuple(data["dependency_inventory"]),
            static_scan_verdict=data["static_scan_verdict"],
            xvfb_only=bool(data["xvfb_only"]),
            admitted_by=data["admitted_by"],
            admitted_at=data["admitted_at"],
            merkle_receipt_id=data["merkle_receipt_id"],
            revoked=bool(data.get("revoked", False)),
            revoked_by=data.get("revoked_by"),
            revoked_at=data.get("revoked_at"),
            revoke_merkle_receipt_id=data.get("revoke_merkle_receipt_id"),
        )


def _receipt_path(receipts_dir: Path, server: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in server)
    return Path(receipts_dir) / f"{safe}.json"


def load_receipt(receipts_dir: Path, server: str) -> ThirdPartyReceipt | None:
    """``None`` = sin receipt (caso esperado: nunca admitido). Un fichero
    presente pero corrupto/ilegible es una integridad rota, no un "no
    receipt" — falla cerrado en vez de tratarlo como ausencia."""
    path = _receipt_path(receipts_dir, server)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptIntegrityError(
            f"receipt ilegible para {server!r} en {path}"
        ) from exc
    if not isinstance(data, dict):
        raise ReceiptIntegrityError(f"receipt para {server!r} no es un objeto JSON")
    try:
        return ThirdPartyReceipt.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReceiptIntegrityError(
            f"receipt para {server!r} le faltan campos o tiene tipos inválidos"
        ) from exc


def _write_receipt(receipts_dir: Path, receipt: ThirdPartyReceipt) -> None:
    receipts_dir = Path(receipts_dir)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = _receipt_path(receipts_dir, receipt.server)
    path.write_text(
        json.dumps(receipt.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )


def admit_third_party(
    receipts_dir: Path,
    merkle_log: Callable[..., Any],
    *,
    server: str,
    cmd: list[str],
    cwd: str | None,
    env_extra: dict[str, str],
    env_passthrough: list[str],
    executable_path: Path,
    package: str,
    version: str,
    license_name: str,
    dependency_inventory: list[str],
    static_scan_verdict: str,
    xvfb_only: bool,
    admitted_by: str,
) -> ThirdPartyReceipt:
    """Admite ``server`` pinando el hash REAL de ``executable_path`` ahora
    mismo. No hay atajo de "confía en este hash que te paso" — el único
    hash que cuenta es el que este código calcula leyendo el fichero."""
    executable_path = Path(executable_path)
    if executable_path.is_symlink() or not executable_path.is_file():
        raise FileNotFoundError(
            f"ejecutable a admitir no existe o es symlink: {executable_path}"
        )
    executable_sha256 = hashlib.sha256(executable_path.read_bytes()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    record = merkle_log(
        action="sentinel.receipt_admitted",
        agent=admitted_by,
        result="success",
        risk_level="high",
        payload={
            "server": server, "package": package, "version": version,
            "executable_sha256": executable_sha256, "xvfb_only": xvfb_only,
            "static_scan_verdict": static_scan_verdict,
        },
        task_id=server,
    )
    receipt = ThirdPartyReceipt(
        server=server,
        cmd=tuple(cmd),
        cwd=cwd,
        env_extra=dict(env_extra),
        env_passthrough=tuple(env_passthrough),
        executable_sha256=executable_sha256,
        package=package,
        version=version,
        license=license_name,
        dependency_inventory=tuple(dependency_inventory),
        static_scan_verdict=static_scan_verdict,
        xvfb_only=xvfb_only,
        admitted_by=admitted_by,
        admitted_at=now,
        merkle_receipt_id=str(record.id),
    )
    _write_receipt(receipts_dir, receipt)
    return receipt


def revoke_third_party(
    receipts_dir: Path,
    merkle_log: Callable[..., Any],
    *,
    server: str,
    revoked_by: str,
) -> ThirdPartyReceipt:
    """Revoca un receipt existente. La cuarentena se restaura de inmediato:
    la siguiente llamada a ``SentinelGate.vet_command`` relee este fichero
    desde disco y encuentra ``revoked=True``, sin caché que invalidar."""
    existing = load_receipt(receipts_dir, server)
    if existing is None:
        raise FileNotFoundError(f"no hay receipt admitido para {server!r} que revocar")
    now = datetime.now(timezone.utc).isoformat()
    record = merkle_log(
        action="sentinel.receipt_revoked",
        agent=revoked_by,
        result="success",
        risk_level="high",
        payload={"server": server, "previously_admitted_by": existing.admitted_by},
        task_id=server,
    )
    revoked = replace(
        existing,
        revoked=True, revoked_by=revoked_by, revoked_at=now,
        revoke_merkle_receipt_id=str(record.id),
    )
    _write_receipt(receipts_dir, revoked)
    return revoked
