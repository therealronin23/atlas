"""F2.6 como gate automático recurrente (spec B+C §4, MAXIMUS Cycle 12).

F2.6 (rúbrica de sucesión, 6 ítems, sesión LLM real) es cara y necesita
juicio real — NUNCA se dispara sola. Mismo principio que ``PreflightGate``:
lo barato y determinista corre solo; lo caro con juicio real lo dispara un
humano cuando el hallazgo lo pide. Lo que este módulo automatiza es
exactamente eso — detectar cuándo F2.6 está DEBIDA, no ejecutarla.

"Cambio grande" (spec B+C §4: "se corre tras cambios grandes, nueva fase,
ADR nuevo") se traduce aquí, determinista, a: ¿hay ADRs nuevos en
``docs/decisions/adr/`` desde el último run REGISTRADO? Quien corre F2.6 de
verdad (sesión Sonnet fría, `claude -p`, o cualquier mecanismo — el spec no
fija cuál) registra el resultado con ``record_f26_run``; este módulo nunca
inventa que se corrió ni evalúa la rúbrica por su cuenta.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.git_env import clean_git_env

_DEFAULT_STATE_PATH = "workspace/self_build/f26_gate_state.json"
_ADR_PREFIX = "docs/decisions/adr/"


@dataclass
class F26GateStatus:
    status: str  # "never_run" | "current" | "due" | "unknown"
    last_run_sha: str | None
    last_run_at: str | None
    last_result: str | None
    new_adrs_since: list[str]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "last_run_sha": self.last_run_sha,
            "last_run_at": self.last_run_at,
            "last_result": self.last_result,
            "new_adrs_since": self.new_adrs_since,
            "reason": self.reason,
        }


def record_f26_run(
    repo_root: Path,
    *,
    result: str,
    notes: str = "",
    state_path: Path | None = None,
    at_sha: str | None = None,
) -> dict[str, Any]:
    """Registra que F2.6 se corrió DE VERDAD (fuera de este módulo). No
    ejecuta ni evalúa nada — solo persiste un SHA, el momento y el resultado
    que declara el caller. ``result`` en {"pass", "fail"}.

    ``at_sha`` es para backfill honesto: si la corrida real ocurrió en un
    commit pasado (p.ej. registrar HOY una F2.6 que se corrió hace días),
    pasar ese SHA en vez del HEAD actual — así ``f26_gate_status`` calcula
    ADRs nuevos desde el momento REAL de la corrida, no desde hoy."""
    if result not in ("pass", "fail"):
        raise ValueError(f"result debe ser 'pass' o 'fail', recibido {result!r}")
    path = state_path or (repo_root / _DEFAULT_STATE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "last_run_sha": at_sha or _head_sha(repo_root),
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "last_result": result,
        "notes": notes[:1000],
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def f26_gate_status(repo_root: Path, *, state_path: Path | None = None) -> F26GateStatus:
    """Determinista, sin red ni LLM: ¿hay ADRs nuevos desde el último run
    registrado? Fail-honesto: un estado ilegible nunca se reporta como
    'current' por defecto — 'unknown' explícito."""
    path = state_path or (repo_root / _DEFAULT_STATE_PATH)
    if not path.is_file():
        current = _list_adrs(repo_root)
        return F26GateStatus(
            status="never_run",
            last_run_sha=None,
            last_run_at=None,
            last_result=None,
            new_adrs_since=current,
            reason="F2.6 nunca se registró como corrido; usa 'atlas f26 record-run' tras correrlo",
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return F26GateStatus(
            status="unknown",
            last_run_sha=None,
            last_run_at=None,
            last_result=None,
            new_adrs_since=[],
            reason=f"estado ilegible: {type(exc).__name__}",
        )
    last_sha = record.get("last_run_sha")
    new_adrs = _adrs_added_since(repo_root, last_sha) if last_sha else _list_adrs(repo_root)
    if new_adrs:
        status = "due"
        reason = f"{len(new_adrs)} ADR(s) nuevo(s) desde el último run"
    else:
        status = "current"
        reason = "sin ADRs nuevos desde el último run"
    return F26GateStatus(
        status=status,
        last_run_sha=last_sha,
        last_run_at=record.get("last_run_at"),
        last_result=record.get("last_result"),
        new_adrs_since=new_adrs,
        reason=reason,
    )


def _head_sha(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=5, check=False, env=clean_git_env(),
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _list_adrs(repo_root: Path) -> list[str]:
    adr_dir = repo_root / "docs" / "decisions" / "adr"
    if not adr_dir.is_dir():
        return []
    return sorted(
        f"{_ADR_PREFIX}{p.name}" for p in adr_dir.glob("*.md")
    )


def _adrs_added_since(repo_root: Path, since_sha: str) -> list[str]:
    """ADRs presentes en HEAD que NO existían en ``since_sha`` — vía
    ``git diff --diff-filter=A`` (solo altas, no ediciones/renombres de ADRs
    ya conocidos). Fail-honesto: un git que falla (SHA podado, repo movido)
    devuelve lista vacía en vez de una excepción — 'current' por defecto
    ante duda, nunca un falso 'due' ruidoso en cada llamada."""
    proc = subprocess.run(
        [
            "git", "-C", str(repo_root), "diff", "--name-only",
            "--diff-filter=A", since_sha, "HEAD", "--", _ADR_PREFIX,
        ],
        capture_output=True, text=True, timeout=10, check=False, env=clean_git_env(),
    )
    if proc.returncode != 0:
        return []
    return sorted(line.strip() for line in proc.stdout.splitlines() if line.strip())
