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

import hashlib
import inspect
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from atlas.core.git_env import clean_git_env
from atlas.core.self_maintenance.f26_grading import grade_f26_transcript
from atlas.logging.merkle_logger import AuditRecord, MerkleLogger
from atlas.security.writer_lock import ExclusiveWriterLock, WriterLockHeld

_DEFAULT_STATE_PATH = "workspace/self_build/f26_gate_state.json"
_ADR_PREFIX = "docs/decisions/adr/"

# item 1 del diseño (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md):
# `atlas f26 run` dispara la rúbrica. El prompt NUNCA se copia a mano aquí —
# se parsea del doc en tiempo de ejecución, fuente única.
_DEFAULT_DOC_PATH = "docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md"
_DEFAULT_RUNS_DIR = "workspace/self_build/f26_runs"
_PROMPT_SECTION_HEADING = "## Cómo ejecutarlo"
_F26_GOLDEN_ROUTE_TARGET = "docs/continuation/CONTINUATION_STATE.md"


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
            "notification": f26_gate_notification(self),
        }


class F26AuditError(RuntimeError):
    """F2.6 no puede arrancar o cerrar con evidencia auditada fiable."""


def f26_gate_notification(status: F26GateStatus) -> dict[str, str] | None:
    """Punto 4 del diseño (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md):
    "notificación accionable cuando está due... encaja con el patrón
    `spawn_task` ya disponible en este entorno". `spawn_task` es una tool MCP
    (`mcp__ccd_session__spawn_task`) que SOLO existe dentro de una sesión
    agente con esa tool cableada — ni este módulo ni un proceso headless
    (`atlas f26 status`, cron, `self_build_runner.py`) pueden invocarla
    directamente. Por eso esta función no dispara nada: prepara el dict con
    los MISMOS nombres de campo que espera `spawn_task` (title/tldr/prompt),
    listo para que CUALQUIER sesión agente que vea `status=='due'` (p.ej. al
    correr `atlas reality --json` al arrancar, ya rutinario por el Operating
    Loop de AGENTS.md) lo pase tal cual a esa tool ella misma.

    Devuelve ``None`` si el gate no está debido — nunca se sugiere disparar
    F2.6 (sesión LLM real, cara) sin necesidad."""
    if status.status != "due":
        return None
    n = len(status.new_adrs_since)
    if status.last_result == "pending_review" and n > 0:
        return {
            "title": f"Repetir F2.6: {n} ADR(s) tras el 6/6 pendiente",
            "tldr": (
                "El transcript pendiente precede ADRs nuevos y no los cubre; "
                "confirmarlo no vuelve current el gate."
            ),
            "prompt": (
                "El gate F2.6 está 'due': existe un pending_review, pero hay "
                f"{n} ADR(s) nuevos desde su SHA. No confirmes ese transcript "
                "como evidencia de los ADRs posteriores. Corre de nuevo la "
                "rúbrica completa en el SHA actual con proveedor capaz fijado."
            ),
        }
    if status.last_result == "pending_review":
        return {
            "title": "Revisar F2.6: 6/6 automático pendiente",
            "tldr": (
                "El harness obtuvo 6/6, pero esa puntuación automática no "
                "equivale a una verificación semántica del operador."
            ),
            "prompt": (
                "El gate F2.6 sigue 'due' con resultado 'pending_review'. "
                "Revisa el transcript enlazado y sus receipts. Sólo registra "
                "'pass' con semantic_verification='operator_confirmed', actor "
                "no vacío y source_state_sha256 igual al estado automático "
                "6/6 pendiente más reciente."
            ),
        }
    if status.last_result == "fail" and n == 0:
        return {
            "title": "Repetir F2.6: el último run falló",
            "tldr": (
                "El último F2.6 registrado falló. La regla es arreglar los "
                "gaps y repetir la rúbrica completa; no hay aprobado parcial."
            ),
            "prompt": (
                "El gate F2.6 está 'due' porque el último run registrado "
                "terminó en 'fail', aunque no haya ADRs nuevos. Revisa sus "
                "notas/evidencia y corre `atlas f26 run --provider "
                "groq_gpt_oss_120b --approval-actor ACTOR --json`. Si vuelve a "
                "fallar, reporta cada ítem y conserva el gate "
                "en due; un 6/6 automático sólo crea pending_review. Únicamente "
                "una revisión semántica enlazada puede dejarlo current."
            ),
        }
    plural = "ADR nuevo" if n == 1 else "ADRs nuevos"
    adr_list = "\n".join(f"  - {adr}" for adr in status.new_adrs_since)
    title = f"Correr F2.6: {n} {plural} desde el último run"
    tldr = (
        f"F2.6 es la rúbrica de sucesión (6 ítems, sesión LLM real vía "
        f"`atlas f26 run`) — hay {n} {plural} desde el último run "
        "registrado, así que el gate está due. Es deliberadamente cara y "
        "manual: nunca se dispara sola, hace falta un gesto humano (o de "
        "agente) explícito para lanzarla."
    )
    prompt = (
        "El gate F2.6 (test de sucesión, spec B+C §4) está 'due': "
        f"{n} {plural} nuevo(s) desde el último run registrado en "
        "atlas-core:\n"
        f"{adr_list}\n\n"
        "Pasos:\n"
        "1. cd al repo atlas-core (working dir real del proyecto).\n"
        "2. Corre `atlas f26 run --provider groq_gpt_oss_120b "
        "--approval-actor ACTOR --json`. Esto "
        "dispara el driver agentic frío con proveedor fijado (hasta ~30 min), "
        "gradea el transcript y auto-registra FAIL o pending_review.\n"
        "3. Si el dispatch falla, reporta el error tal cual "
        "salga; no se registra nada porque no hay transcript válido.\n"
        "4. Si el veredicto (`overall_result`) es 'fail', el propio "
        "output lista qué ítems (item_1..item_6) fallaron y por qué — "
        "la regla del diseño es 'cada fallo = gap → arreglar → repetir "
        "la rúbrica ENTERA', no hay aprobado parcial.\n"
        "5. Si el score automático es 6/6, queda 'pending_review': el operador "
        "debe revisar semánticamente el transcript y usar `atlas f26 record-run "
        "--result pass --transcript-sha256 SHA --automatic-score 6/6 "
        "--semantic-review-actor ACTOR` para enlazar la confirmación."
    )
    return {"title": title, "tldr": tldr, "prompt": prompt}


def _state_sha256(record_without_hash: dict[str, Any]) -> str:
    canonical = json.dumps(
        record_without_hash,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _runtime_home() -> Path:
    configured_home = os.environ.get("ATLAS_HOME", "").strip()
    return (
        Path(configured_home).expanduser().resolve()
        if configured_home else Path.home() / "atlas"
    )


def _f26_writer_lock() -> ExclusiveWriterLock:
    """Serializa sesiones F2.6 aunque usen worktrees o state paths distintos."""
    return ExclusiveWriterLock(
        _runtime_home() / "memory" / "audit" / ".f26_gate.writer.lock"
    )


def _acquire_f26_writer_lock() -> ExclusiveWriterLock:
    lock = _f26_writer_lock()
    try:
        lock.acquire()
    except WriterLockHeld as exc:
        raise F26AuditError(f"F2.6 already has an active writer: {exc}") from exc
    return lock


def _effective_state_path(repo_root: Path, state_path: Path | None) -> Path:
    if state_path is not None:
        return state_path.expanduser().resolve()
    configured = os.environ.get("ATLAS_F26_STATE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return repo_root / _DEFAULT_STATE_PATH


def _pending_state_path(path: Path, state_sha256: str) -> Path:
    return path.with_name(f".{path.name}.{state_sha256}.pending")


def _pending_state_paths(path: Path) -> list[Path]:
    if not path.parent.is_dir():
        return []
    return sorted(path.parent.glob(f".{path.name}.*.pending"))


def _stage_f26_state(path: Path, record: dict[str, Any]) -> Path:
    """Fsync a un path único; todavía no publica el estado canónico."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _pending_state_paths(path)
    if existing:
        raise F26AuditError(
            "F2.6 has an unresolved staged state: "
            + ", ".join(str(item) for item in existing)
        )
    state_hash = record.get("state_sha256")
    if not isinstance(state_hash, str):
        raise F26AuditError("F2.6 staged state has no state_sha256")
    pending = _pending_state_path(path, state_hash)
    payload = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        with pending.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise F26AuditError(
            f"F2.6 state could not be staged: {type(exc).__name__}: {exc}"
        ) from exc
    return pending


def _publish_f26_state(pending: Path, path: Path) -> None:
    """Publica tras el terminal, manteniendo un marcador hasta durabilidad.

    ``os.replace`` consume el nombre staged antes del ``fsync`` del directorio.
    Un fallo entre ambos no puede fingir que ese nombre sigue ahí: un hardlink
    de recuperación permanece visible para que el gate devuelva UNKNOWN.
    """
    recovery = pending.with_name(f"{pending.name}.publication.pending")
    directory_fd: int | None = None
    replaced = False
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        os.link(pending, recovery)
        os.fsync(directory_fd)
        os.replace(pending, path)
        replaced = True
        os.fsync(directory_fd)
        try:
            recovery.unlink()
            os.fsync(directory_fd)
        except OSError as cleanup_exc:
            try:
                if not recovery.exists():
                    os.link(path, recovery)
            except OSError as marker_exc:
                raise F26AuditError(
                    "F2.6 state is durable but recovery-marker cleanup failed "
                    "and UNKNOWN marker recreation also failed: "
                    f"{type(cleanup_exc).__name__}: {cleanup_exc}; "
                    f"marker={type(marker_exc).__name__}: {marker_exc}"
                ) from cleanup_exc
            raise F26AuditError(
                "F2.6 state is durable but recovery-marker cleanup failed; "
                f"gate held UNKNOWN at {recovery}: "
                f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            ) from cleanup_exc
    except OSError as exc:
        if not replaced:
            try:
                recovery.unlink(missing_ok=True)
            except OSError:
                pass
        location = recovery if replaced else pending
        detail = (
            "canonical may already contain the new state; recovery marker retained"
            if replaced
            else "canonical was not replaced; staged state retained"
        )
        raise F26AuditError(
            "F2.6 terminal receipt exists but state publication failed; "
            f"{detail} at {location}: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _persist_run_meta(path: Path, record: dict[str, Any]) -> None:
    """Reemplaza el meta completo; nunca expone al lector JSON parcial."""
    pending = path.with_name(f"{path.name}.pending")
    pending.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    os.replace(pending, path)


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read_state_record(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise F26AuditError(
            f"source pending-review state is unreadable: {type(exc).__name__}"
        ) from exc
    if not isinstance(value, dict):
        raise F26AuditError("source pending-review state is not a JSON object")
    return value


def record_f26_run(
    repo_root: Path,
    *,
    result: str,
    notes: str = "",
    state_path: Path | None = None,
    at_sha: str | None = None,
    transcript_sha256: str | None = None,
    task_id: str | None = None,
    automatic_score: str | None = None,
    semantic_verification: str | None = None,
    semantic_review_actor: str | None = None,
    source_state_sha256: str | None = None,
    _state_source: str = "manual_record",
    _defer_state_publish: bool = False,
    _writer_lock_held: bool = False,
) -> dict[str, Any]:
    """Serializa la preparación, receipt y publicación de un estado F2.6."""
    kwargs: dict[str, Any] = {
        "result": result,
        "notes": notes,
        "state_path": state_path,
        "at_sha": at_sha,
        "transcript_sha256": transcript_sha256,
        "task_id": task_id,
        "automatic_score": automatic_score,
        "semantic_verification": semantic_verification,
        "semantic_review_actor": semantic_review_actor,
        "source_state_sha256": source_state_sha256,
        "_state_source": _state_source,
        "_defer_state_publish": _defer_state_publish,
    }
    if _writer_lock_held:
        return _record_f26_run_locked(repo_root, **kwargs)
    writer_lock = _acquire_f26_writer_lock()
    try:
        return _record_f26_run_locked(repo_root, **kwargs)
    finally:
        writer_lock.release()


def _record_f26_run_locked(
    repo_root: Path,
    *,
    result: str,
    notes: str,
    state_path: Path | None,
    at_sha: str | None,
    transcript_sha256: str | None,
    task_id: str | None,
    automatic_score: str | None,
    semantic_verification: str | None,
    semantic_review_actor: str | None,
    source_state_sha256: str | None,
    _state_source: str,
    _defer_state_publish: bool,
) -> dict[str, Any]:
    """Persiste un resultado F2.6 y lo enlaza a un terminal Merkle.

    ``pending_review`` sólo representa un 6/6 automático sin verificación
    semántica. ``pass`` exige una confirmación de operador enlazada al estado
    automático pendiente inmediatamente anterior. ``fail`` puede registrarse
    manualmente para conservar evidencia negativa sin elevarla a PASS.

    ``at_sha`` es para backfill honesto: si la corrida real ocurrió en un
    commit pasado (p.ej. registrar HOY una F2.6 que se corrió hace días),
    pasar ese SHA en vez del HEAD actual — así ``f26_gate_status`` calcula
    ADRs nuevos desde el momento REAL de la corrida, no desde hoy."""
    if result not in ("pass", "fail", "pending_review"):
        raise ValueError(
            "result debe ser 'pass', 'fail' o 'pending_review', "
            f"recibido {result!r}"
        )
    if _state_source not in {"manual_record", "automatic_run", "semantic_review"}:
        raise ValueError(f"state_source F2.6 inválido: {_state_source!r}")
    if result == "pending_review":
        if _state_source != "automatic_run":
            raise F26AuditError("pending_review sólo puede proceder de automatic_run")
        if (
            not _is_sha256(transcript_sha256)
            or automatic_score != "6/6"
            or semantic_verification != "not_performed"
        ):
            raise F26AuditError(
                "pending_review exige transcript SHA-256, automatic_score=6/6 "
                "y semantic_verification=not_performed"
            )
    if result == "pass":
        if (
            not _is_sha256(transcript_sha256)
            or automatic_score != "6/6"
            or semantic_verification != "operator_confirmed"
            or not isinstance(semantic_review_actor, str)
            or not semantic_review_actor.strip()
            or not _is_sha256(source_state_sha256)
        ):
            raise F26AuditError(
                "pass exige transcript SHA-256, automatic_score=6/6, "
                "semantic_verification=operator_confirmed, actor no vacío y "
                "source_state_sha256"
            )
        _state_source = "semantic_review"
    path = _effective_state_path(repo_root, state_path)
    source: dict[str, Any] | None = None
    if result == "pass":
        source = _read_state_record(path)
        source_run_sha = source.get("last_run_sha")
        run_sha = at_sha or (
            source_run_sha if isinstance(source_run_sha, str) else "unknown"
        )
    else:
        run_sha = at_sha or _head_sha(repo_root)
    if run_sha == "unknown" or not _commit_exists(repo_root, run_sha):
        raise F26AuditError(f"F2.6 state requires an existing commit SHA: {run_sha!r}")
    recorded_at = datetime.now(timezone.utc).isoformat()
    effective_task_id = task_id or f"f26:manual:{recorded_at}"
    merkle: MerkleLogger | None = None
    if result == "pass":
        assert source is not None
        source_hash = source.get("state_sha256")
        if source_hash != source_state_sha256:
            raise F26AuditError("source_state_sha256 no enlaza el estado pending_review actual")
        source_unhashed = dict(source)
        source_unhashed.pop("state_sha256", None)
        if _state_sha256(source_unhashed) != source_hash:
            raise F26AuditError("source pending_review state hash is invalid")
        source_task_id = source.get("task_id")
        source_run_sha = source.get("last_run_sha")
        source_transcript = source.get("transcript_sha256")
        if (
            source.get("last_result") != "pending_review"
            or source.get("state_source") != "automatic_run"
            or source.get("automatic_score") != "6/6"
            or source.get("semantic_verification") != "not_performed"
            or source_run_sha != run_sha
            or source_transcript != transcript_sha256
            or not isinstance(source_task_id, str)
        ):
            raise F26AuditError(
                "pass no coincide con el automatic_run pending_review 6/6 más reciente"
            )
        merkle = _verified_runtime_merkle()
        source_valid, source_reason = _state_receipt_matches(
            merkle,
            state_sha256=str(source_hash),
            run_sha=run_sha,
            result="pending_review",
            transcript_sha256=transcript_sha256,
            task_id=source_task_id,
            state_source="automatic_run",
            automatic_score="6/6",
            semantic_verification="not_performed",
            semantic_review_actor=None,
            source_state_sha256=None,
        )
        if not source_valid:
            raise F26AuditError(
                "source pending_review no es el terminal automático más reciente: "
                f"{source_reason}"
            )
    base_record: dict[str, Any] = {
        "last_run_sha": run_sha,
        "last_run_at": recorded_at,
        "last_result": result,
        "notes": notes[:1000],
        "task_id": effective_task_id,
        "transcript_sha256": transcript_sha256,
        "automatic_score": automatic_score,
        "semantic_verification": semantic_verification,
        "semantic_review_actor": (
            semantic_review_actor.strip()
            if isinstance(semantic_review_actor, str) else None
        ),
        "state_source": _state_source,
        "source_state_sha256": source_state_sha256,
    }
    record = {**base_record, "state_sha256": _state_sha256(base_record)}
    merkle = merkle or _verified_runtime_merkle()
    pending = _stage_f26_state(path, record)
    if _defer_state_publish:
        return record

    try:
        _finish_audit_record(
            merkle,
            task_id=effective_task_id,
            result="failure" if result == "fail" else "success",
            payload={
                "run_sha": run_sha,
                "overall_result": result,
                "transcript_sha256": transcript_sha256,
                "state_sha256": record["state_sha256"],
                "state_source": _state_source,
                "automatic_score": automatic_score,
                "semantic_verification": semantic_verification,
                "semantic_review_actor": (
                    semantic_review_actor.strip()
                    if isinstance(semantic_review_actor, str) else None
                ),
                "source_state_sha256": source_state_sha256,
            },
        )
    except Exception:
        pending.unlink(missing_ok=True)
        raise
    _publish_f26_state(pending, path)
    return record


def f26_gate_status(repo_root: Path, *, state_path: Path | None = None) -> F26GateStatus:
    """Determinista, sin red ni LLM: ¿hay ADRs nuevos desde el último run
    registrado? Fail-honesto: un estado ilegible nunca se reporta como
    'current' por defecto — 'unknown' explícito."""
    path = _effective_state_path(repo_root, state_path)
    pending_paths = _pending_state_paths(path)
    if pending_paths:
        return F26GateStatus(
            status="unknown", last_run_sha=None, last_run_at=None,
            last_result=None, new_adrs_since=[],
            reason=(
                "hay estado F2.6 staged sin publicación resuelta: "
                + ", ".join(str(item) for item in pending_paths)
            ),
        )
    if not path.is_file():
        try:
            merkle = _verified_runtime_merkle()
            f26_records = [
                record for record in merkle.read_all()
                if record.agent == "atlas.f26_gate"
            ]
        except (F26AuditError, OSError, RuntimeError, ValueError) as exc:
            return F26GateStatus(
                status="unknown", last_run_sha=None, last_run_at=None,
                last_result=None, new_adrs_since=[], reason=str(exc),
            )
        if f26_records:
            return F26GateStatus(
                status="unknown", last_run_sha=None, last_run_at=None,
                last_result=None, new_adrs_since=[],
                reason="hay receipts F2.6 en Merkle pero falta el state enlazado",
            )
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
    if not isinstance(record, dict):
        return F26GateStatus(
            status="unknown", last_run_sha=None, last_run_at=None,
            last_result=None, new_adrs_since=[],
            reason="estado ilegible: el JSON raíz no es un objeto",
        )
    last_sha = record.get("last_run_sha")
    last_run_at = record.get("last_run_at")
    last_result = record.get("last_result")
    if (
        not isinstance(last_sha, str) or not last_sha.strip()
        or not isinstance(last_run_at, str) or not last_run_at.strip()
        or last_result not in {"pass", "fail", "pending_review"}
    ):
        return F26GateStatus(
            status="unknown",
            last_run_sha=last_sha if isinstance(last_sha, str) else None,
            last_run_at=last_run_at if isinstance(last_run_at, str) else None,
            last_result=last_result if isinstance(last_result, str) else None,
            new_adrs_since=[], reason="estado ilegible: campos F2.6 inválidos",
        )

    task_id = record.get("task_id")
    transcript_sha256 = record.get("transcript_sha256")
    state_sha256 = record.get("state_sha256")
    automatic_score = record.get("automatic_score")
    semantic_verification = record.get("semantic_verification")
    semantic_review_actor = record.get("semantic_review_actor")
    state_source = record.get("state_source")
    source_state_sha256 = record.get("source_state_sha256")
    if last_result == "pending_review" and not (
        _is_sha256(transcript_sha256)
        and automatic_score == "6/6"
        and semantic_verification == "not_performed"
        and semantic_review_actor is None
        and state_source == "automatic_run"
        and source_state_sha256 is None
    ):
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason="estado pending_review no satisface el contrato automático 6/6",
        )
    if last_result == "pass" and not (
        _is_sha256(transcript_sha256)
        and automatic_score == "6/6"
        and semantic_verification == "operator_confirmed"
        and isinstance(semantic_review_actor, str)
        and bool(semantic_review_actor.strip())
        and state_source == "semantic_review"
        and _is_sha256(source_state_sha256)
    ):
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason="estado PASS carece de una revisión semántica enlazada válida",
        )
    if not isinstance(task_id, str) or not isinstance(state_sha256, str):
        if last_result == "fail":
            try:
                _verified_runtime_merkle()
            except (F26AuditError, OSError, RuntimeError, ValueError) as exc:
                return F26GateStatus(
                    status="unknown", last_run_sha=last_sha,
                    last_run_at=last_run_at, last_result=last_result,
                    new_adrs_since=[], reason=str(exc),
                )
            new_adrs, diff_error = _adrs_added_since(repo_root, last_sha)
            if diff_error is not None:
                return F26GateStatus(
                    status="unknown", last_run_sha=last_sha,
                    last_run_at=last_run_at, last_result=last_result,
                    new_adrs_since=[],
                    reason=(
                        "estado FAIL legado sin receipt enlazable y no se pudo "
                        f"comparar su SHA: {diff_error}"
                    ),
                )
            return F26GateStatus(
                status="due", last_run_sha=last_sha, last_run_at=last_run_at,
                last_result=last_result, new_adrs_since=new_adrs,
                reason=(
                    "el último run F2.6 legado falló y carece del receipt "
                    "enlazable actual; hay que repetir la rúbrica completa"
                ),
            )
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason="estado sin task_id/state_sha256 enlazables",
        )
    if transcript_sha256 is not None and not isinstance(transcript_sha256, str):
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason="estado ilegible: transcript_sha256 inválido",
        )
    unhashed_state = dict(record)
    unhashed_state.pop("state_sha256", None)
    if _state_sha256(unhashed_state) != state_sha256:
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason="state_sha256 no coincide con el contenido del estado",
        )
    try:
        merkle = _verified_runtime_merkle()
    except (F26AuditError, OSError, RuntimeError, ValueError) as exc:
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[], reason=str(exc),
        )
    valid_receipt, receipt_reason = _state_receipt_matches(
        merkle, state_sha256=state_sha256, run_sha=last_sha,
        result=last_result, transcript_sha256=transcript_sha256, task_id=task_id,
        state_source=state_source,
        automatic_score=automatic_score,
        semantic_verification=semantic_verification,
        semantic_review_actor=semantic_review_actor,
        source_state_sha256=source_state_sha256,
    )
    if not valid_receipt:
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason=f"estado no enlaza con su receipt Merkle: {receipt_reason}",
        )

    new_adrs, diff_error = _adrs_added_since(repo_root, last_sha)
    if diff_error is not None:
        return F26GateStatus(
            status="unknown", last_run_sha=last_sha, last_run_at=last_run_at,
            last_result=last_result, new_adrs_since=[],
            reason=f"no se pudo comparar ADRs desde el SHA registrado: {diff_error}",
        )
    if last_result == "fail":
        status = "due"
        reason = "el último run F2.6 falló; hay que repetir la rúbrica completa"
    elif last_result == "pending_review":
        status = "due"
        reason = (
            "6/6 automático pendiente de verificación semántica del operador"
        )
    elif new_adrs:
        status = "due"
        reason = f"{len(new_adrs)} ADR(s) nuevo(s) desde el último run"
    else:
        status = "current"
        reason = "sin ADRs nuevos desde el último run"
    return F26GateStatus(
        status=status,
        last_run_sha=last_sha,
        last_run_at=last_run_at,
        last_result=last_result,
        new_adrs_since=new_adrs,
        reason=reason,
    )


def _head_sha(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=5, check=False, env=clean_git_env(),
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def _commit_exists(repo_root: Path, sha: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True, text=True, timeout=5, check=False,
            env=clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _tracked_checkout_status(repo_root: Path) -> tuple[bool, str]:
    """Devuelve el estado tracked exacto; un fallo Git nunca equivale a limpio."""
    try:
        proc = subprocess.run(
            [
                "git", "-C", str(repo_root), "status", "--porcelain=v1",
                "--untracked-files=all",
            ],
            capture_output=True, text=True, timeout=10, check=False,
            env=clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, proc.stderr.strip() or f"git status exit {proc.returncode}"
    return not bool(proc.stdout), proc.stdout.strip()


def _verified_runtime_merkle() -> MerkleLogger:
    merkle = MerkleLogger(_runtime_home() / "memory" / "audit")
    intact, detail = merkle.verify_chain()
    if not intact:
        raise F26AuditError(f"Merkle chain is not intact: {detail}")
    return merkle


def _state_receipt_matches(
    merkle: MerkleLogger,
    *,
    state_sha256: str,
    run_sha: str,
    result: str,
    transcript_sha256: str | None,
    task_id: str,
    state_source: object,
    automatic_score: object,
    semantic_verification: object,
    semantic_review_actor: object,
    source_state_sha256: object,
) -> tuple[bool, str]:
    records = merkle.read_all()
    matches = [
        record for record in records
        if record.action == "session.ended" and record.task_id == task_id
    ]
    if len(matches) != 1:
        return False, f"task_id matched {len(matches)} session.ended records"
    record = matches[0]
    if record.agent != "atlas.f26_gate":
        return False, "receipt is not an atlas.f26_gate session.ended record"
    try:
        linked_index = next(
            index for index, candidate in enumerate(records)
            if candidate.hash_self == record.hash_self
        )
    except StopIteration:
        return False, "linked receipt is absent from the verified Merkle sequence"
    later_records = records[linked_index + 1:]
    for candidate in later_records:
        if candidate.action != "session.started" or candidate.agent != "atlas.f26_gate":
            continue
        matching_ends = [
            later for later in later_records
            if later.action == "session.ended"
            and later.agent == "atlas.f26_gate"
            and later.task_id == candidate.task_id
        ]
        if len(matching_ends) != 1:
            return False, (
                "a later F2.6 session is incomplete or ambiguous: "
                f"task_id={candidate.task_id!r}, terminal_count={len(matching_ends)}"
            )
    completed = [
        candidate for candidate in records
        if candidate.action == "session.ended"
        and candidate.agent == "atlas.f26_gate"
        and candidate.payload.get("overall_result") in {
            "pass", "fail", "pending_review",
        }
    ]
    if not completed or completed[-1].hash_self != record.hash_self:
        return False, "state is not linked to the latest completed F2.6 end"
    if result == "pass":
        if len(completed) < 2:
            return False, "semantic review has no prior automatic pending_review end"
        source = completed[-2]
        expected_source = {
            "run_sha": run_sha,
            "overall_result": "pending_review",
            "transcript_sha256": transcript_sha256,
            "state_sha256": source_state_sha256,
            "state_source": "automatic_run",
            "automatic_score": "6/6",
            "semantic_verification": "not_performed",
        }
        for key, value in expected_source.items():
            if source.payload.get(key) != value:
                return False, f"source pending_review receipt payload {key} differs"
    if record.task_id != task_id:
        return False, "task_id differs from the receipt"
    expected = {
        "run_sha": run_sha,
        "overall_result": result,
        "transcript_sha256": transcript_sha256,
        "state_sha256": state_sha256,
        "state_source": state_source,
        "automatic_score": automatic_score,
        "semantic_verification": semantic_verification,
        "semantic_review_actor": semantic_review_actor,
        "source_state_sha256": source_state_sha256,
    }
    for key, value in expected.items():
        if record.payload.get(key) != value:
            return False, f"receipt payload {key} differs"
    expected_receipt_result = "failure" if result == "fail" else "success"
    if record.result != expected_receipt_result:
        return False, "receipt result differs from overall_result"
    return True, "matched"


def _audit_ref(record: AuditRecord) -> dict[str, str | None]:
    return {
        "id": record.id,
        "action": record.action,
        "hash_self": record.hash_self,
        "hash_prev": record.hash_prev,
        "task_id": record.task_id,
    }


def _model_call_refs(merkle: MerkleLogger, *, task_id: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for record in merkle.read_all():
        if record.action != "model.called" or record.task_id != task_id:
            continue
        refs.append({
            "hash_self": record.hash_self,
            "provider": record.payload.get("provider"),
            "model": record.payload.get("model"),
            "tokens_used": record.payload.get("tokens_used"),
            "success": record.payload.get("success"),
        })
    return refs


def _finish_audit_record(
    merkle: MerkleLogger, *, task_id: str, result: str, payload: dict[str, Any],
) -> AuditRecord:
    try:
        record = merkle.log(
            action="session.ended",
            agent="atlas.f26_gate",
            result=result,
            risk_level="moderate",
            payload=payload,
            task_id=task_id,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise F26AuditError(f"F2.6 end receipt could not be written: {exc}") from exc
    intact, detail = merkle.verify_chain()
    if not intact:
        raise F26AuditError(f"Merkle chain failed after F2.6: {detail}")
    return record


_APPLIED_RESULT_RE = re.compile(
    r"\AProposal (?P<proposal>[A-Za-z0-9._:-]+) "
    r"path='docs/continuation/CONTINUATION_STATE\.md' "
    r"status=applied approval_ref=(?P<approval>[0-9a-f]{64}) "
    r"receipt_id=(?P<receipt>[A-Za-z0-9._:-]+)\Z",
)


def _golden_route_evidence(
    transcript: str,
    *,
    merkle: MerkleLogger,
    task_id: str,
    started_receipt_hash: str,
) -> tuple[list[dict[str, str]], str | None]:
    """Vincula tool_use -> tool_result -> apply receipt -> approval receipt.

    El transcript es input no confiable. Cualquier línea/shape/ID ambiguo
    invalida la atribución completa; nunca se busca un substring suelto.
    """
    uses: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    try:
        lines = [line for line in transcript.splitlines() if line.strip()]
        messages = [json.loads(line) for line in lines]
    except (json.JSONDecodeError, ValueError) as exc:
        return [], f"invalid transcript JSONL: {exc}"
    for message in messages:
        if not isinstance(message, dict):
            return [], "transcript message is not an object"
        message_type = message.get("type")
        body = message.get("message")
        if message_type not in {"assistant", "user"}:
            continue
        if not isinstance(body, dict) or not isinstance(body.get("content"), list):
            return [], "transcript message has invalid content"
        for block in body["content"]:
            if not isinstance(block, dict):
                return [], "transcript content block is not an object"
            if message_type == "assistant" and block.get("type") == "tool_use":
                tool_id = block.get("id")
                if not isinstance(tool_id, str) or not tool_id or tool_id in uses:
                    return [], "tool_use IDs are missing or duplicate"
                uses[tool_id] = block
            elif message_type == "user" and block.get("type") == "tool_result":
                tool_id = block.get("tool_use_id")
                if not isinstance(tool_id, str) or not tool_id or tool_id in results:
                    return [], "tool_result IDs are missing or duplicate"
                if tool_id not in uses:
                    return [], "tool_result has no preceding tool_use"
                results[tool_id] = block

    all_records = merkle.read_all()
    start_indexes = [
        index for index, record in enumerate(all_records)
        if record.hash_self == started_receipt_hash
    ]
    if len(start_indexes) != 1:
        return [], f"start receipt matched {len(start_indexes)} Merkle records"
    records = {
        record.hash_self: record
        for record in all_records[start_indexes[0] + 1:]
    }
    evidence: list[dict[str, str]] = []
    golden_route_uses = [
        use for use in uses.values() if use.get("name") == "GoldenRoute"
    ]
    if len(golden_route_uses) != 1:
        return [], (
            "expected exactly one GoldenRoute tool_use in the transcript, "
            f"got {len(golden_route_uses)}"
        )
    for tool_id, use in uses.items():
        if use.get("name") != "GoldenRoute":
            continue
        input_ = use.get("input")
        result = results.get(tool_id)
        if not isinstance(input_, dict) or set(input_) != {"text"} or result is None:
            continue
        request = " ".join(str(input_.get("text", "")).split())
        if not re.fullmatch(
            r"añade la línea ['\"]F2\.6 ejecutado['\"] al final de "
            r"docs/continuation/CONTINUATION_STATE\.md\.?",
            request,
            flags=re.IGNORECASE,
        ):
            continue
        if result.get("is_error") is not False or not isinstance(result.get("content"), str):
            continue
        match = _APPLIED_RESULT_RE.fullmatch(result["content"])
        if match is None:
            continue
        applied = records.get(match.group("approval"))
        if applied is None or (
            applied.action != "golden_route.applied"
            or applied.agent != "golden_route"
            or applied.result != "success"
            or applied.task_id != task_id
        ):
            continue
        payload = applied.payload
        approved_by = payload.get("approved_by")
        if (
            payload.get("proposal_id") != match.group("proposal")
            or payload.get("receipt_id") != match.group("receipt")
            or payload.get("path") != _F26_GOLDEN_ROUTE_TARGET
            or not isinstance(payload.get("approval_ref"), str)
            or not isinstance(approved_by, str)
            or not approved_by.strip()
        ):
            continue
        decision = records.get(payload["approval_ref"])
        decision_actor = decision.payload.get("actor") if decision is not None else None
        if decision is None or (
            decision.action != "golden_route.decision.approve"
            or decision.agent != "golden_route"
            or decision.result != "success"
            or decision.task_id != task_id
            or decision.payload.get("proposal_id") != match.group("proposal")
            or decision.payload.get("decision") != "approve"
            or not isinstance(decision_actor, str)
            or not decision_actor.strip()
            or decision_actor != approved_by
        ):
            continue
        evidence.append({
            "proposal_id": match.group("proposal"),
            "receipt_id": match.group("receipt"),
            "applied_hash": applied.hash_self,
            "decision_hash": decision.hash_self,
        })
    if len(evidence) != 1:
        return evidence, f"expected exactly one verified GoldenRoute apply, got {len(evidence)}"
    return evidence, None


def _git_text(repo_root: Path, *args: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, timeout=10, check=False,
            env=clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""
    return proc.returncode == 0, proc.stdout


def _git_bytes(repo_root: Path, *args: str) -> tuple[bool, bytes]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=False, timeout=10, check=False,
            env=clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False, b""
    return proc.returncode == 0, proc.stdout


def _tree_mode_type(repo_root: Path, sha: str) -> tuple[bool, tuple[str, str]]:
    ok, output = _git_text(repo_root, "ls-tree", sha, "--", _F26_GOLDEN_ROUTE_TARGET)
    if not ok:
        return False, ("", "")
    match = re.fullmatch(
        r"(?P<mode>\d{6}) (?P<type>\w+) [0-9a-f]+\t" +
        re.escape(_F26_GOLDEN_ROUTE_TARGET) + r"\n?",
        output,
    )
    if match is None:
        return False, ("", "")
    return True, (match.group("mode"), match.group("type"))


def _classify_head_transition(
    repo_root: Path, *, start_sha: str, finish_sha: str, transcript: str,
    merkle: MerkleLogger,
    task_id: str,
    started_receipt_hash: str,
) -> dict[str, Any]:
    """Distingue el commit exacto de GoldenRoute de deriva concurrente.

    Un F2.6 válido puede mover HEAD por diseño: el ítem 3 aplica un ColdUpdate,
    cuya ruta commitea el fichero objetivo. Sólo se acepta una transición de
    un commit, con padre exacto en el SHA inicial, ``proposal_id`` presente en
    el tool-result aplicado y el único diff igual al append literal exigido.
    """
    if "unknown" in {start_sha, finish_sha}:
        return {
            "changed": start_sha != finish_sha,
            "authorized": False,
            "kind": "unverifiable",
            "reason": "start or finish SHA is unknown",
        }
    if start_sha == finish_sha:
        return {
            "changed": False,
            "authorized": True,
            "kind": "unchanged",
            "reason": "HEAD remained at the captured start SHA",
        }

    evidence, evidence_error = _golden_route_evidence(
        transcript,
        merkle=merkle,
        task_id=task_id,
        started_receipt_hash=started_receipt_hash,
    )
    if evidence_error is not None:
        return {
            "changed": True, "authorized": False,
            "kind": "unattributed_commit", "reason": evidence_error,
        }
    proposal_ids = {item["proposal_id"] for item in evidence}
    ok, commit_text = _git_text(repo_root, "show", "-s", "--format=%P%x00%B", finish_sha)
    if not ok or not commit_text:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unverifiable",
            "reason": "finish commit metadata is unavailable",
        }
    parent_text, separator, commit_message = commit_text.partition("\x00")
    parents = parent_text.split()
    if not separator:
        parents = []
    if parents != [start_sha]:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unexpected_lineage",
            "reason": f"finish commit parents are {parents!r}, expected [{start_sha!r}]",
        }

    proposal_match = re.search(
        r"(?m)^proposal_id:\s*([A-Za-z0-9._:-]+)\s*$", commit_message,
    )
    committed_proposal = proposal_match.group(1) if proposal_match is not None else None
    if committed_proposal is None or committed_proposal not in proposal_ids:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unattributed_commit",
            "reason": (
                f"commit proposal_id={committed_proposal!r} is not tied to an "
                f"applied GoldenRoute result {sorted(proposal_ids)!r}"
            ),
        }

    ok, names_text = _git_text(
        repo_root, "diff", "--name-only", start_sha, finish_sha, "--",
    )
    changed_paths = [line for line in names_text.splitlines() if line]
    if not ok or changed_paths != [_F26_GOLDEN_ROUTE_TARGET]:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unexpected_diff",
            "reason": f"changed paths are {changed_paths!r}",
        }

    before_mode_ok, before_mode = _tree_mode_type(repo_root, start_sha)
    after_mode_ok, after_mode = _tree_mode_type(repo_root, finish_sha)
    if not before_mode_ok or not after_mode_ok or before_mode != after_mode:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unexpected_mode",
            "reason": f"tree mode/type changed from {before_mode!r} to {after_mode!r}",
        }

    before_ok, before = _git_bytes(
        repo_root, "show", f"{start_sha}:{_F26_GOLDEN_ROUTE_TARGET}",
    )
    after_ok, after = _git_bytes(
        repo_root, "show", f"{finish_sha}:{_F26_GOLDEN_ROUTE_TARGET}",
    )
    separator_bytes = b"" if not before or before.endswith(b"\n") else b"\n"
    expected = before + separator_bytes + b"F2.6 ejecutado\n"
    if not before_ok or not after_ok or after != expected:
        return {
            "changed": True,
            "authorized": False,
            "kind": "unexpected_content",
            "reason": "commit is not the exact F2.6 append",
        }

    return {
        "changed": True,
        "authorized": True,
        "kind": "golden_route_commit",
        "reason": "single exact GoldenRoute append commit",
        "proposal_id": committed_proposal,
    }


def _list_adrs(repo_root: Path) -> list[str]:
    adr_dir = repo_root / "docs" / "decisions" / "adr"
    if not adr_dir.is_dir():
        return []
    return sorted(
        f"{_ADR_PREFIX}{p.name}" for p in adr_dir.glob("*.md")
    )


def _adrs_added_since(repo_root: Path, since_sha: str) -> tuple[list[str], str | None]:
    """ADRs presentes en HEAD que NO existían en ``since_sha`` — vía
    ``git diff --diff-filter=A`` (solo altas, no ediciones/renombres de ADRs
    ya conocidos). Fail-honesto: un Git que falla (SHA podado, repo movido)
    devuelve una señal de error; el caller debe reportar ``unknown``, nunca
    convertir ausencia de evidencia en ``current``."""
    try:
        proc = subprocess.run(
            [
                "git", "-C", str(repo_root), "diff", "--name-only",
                "--diff-filter=A", since_sha, "HEAD", "--", _ADR_PREFIX,
            ],
            capture_output=True, text=True, timeout=10, check=False,
            env=clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return [], proc.stderr.strip() or f"git diff exit {proc.returncode}"
    return (
        sorted(line.strip() for line in proc.stdout.splitlines() if line.strip()),
        None,
    )


class F26PromptExtractionError(RuntimeError):
    """El doc fuente de F2.6 no tiene el bloque de rúbrica esperado. Fail
    closed a propósito: nunca se improvisa un prompt sustituto — si el doc
    cambió de forma, quien lo lea debe arreglarlo, no adivinarlo."""


def extract_f26_prompt(doc_path: Path) -> str:
    """Extrae el prompt de la rúbrica F2.6 leyendo EL DOC (fuente única),
    nunca copiado a mano en Python. Parsea el bloque ```bash bajo la sección
    "## Cómo ejecutarlo" y el string entre comillas pasado a
    ``claude -p --model sonnet "..."``, reconstruyendo las líneas que bash
    uniría vía continuación ``\\<salto de línea>``."""
    if not doc_path.is_file():
        raise F26PromptExtractionError(f"doc F2.6 no encontrado: {doc_path}")
    text = doc_path.read_text(encoding="utf-8")
    section_start = text.find(_PROMPT_SECTION_HEADING)
    if section_start == -1:
        raise F26PromptExtractionError(
            f"sección {_PROMPT_SECTION_HEADING!r} no encontrada en {doc_path}"
        )
    fence_match = re.search(r"```bash\n(.*?)```", text[section_start:], re.DOTALL)
    if fence_match is None:
        raise F26PromptExtractionError(
            f"bloque ```bash no encontrado bajo {_PROMPT_SECTION_HEADING!r} en {doc_path}"
        )
    # bash: dentro de comillas dobles, barra invertida + salto de línea se
    # elimina entero (continuación de línea) — así se reconstruye el prompt
    # tal y como lo vería `claude -p` al ejecutarse de verdad.
    joined = fence_match.group(1).replace("\\\n", "")
    prompt_match = re.search(r'claude -p --model sonnet "(.*)"', joined, re.DOTALL)
    if prompt_match is None:
        raise F26PromptExtractionError(
            f"prompt entre comillas no encontrado en el bloque bash de {doc_path}"
        )
    return prompt_match.group(1)


def _default_claude_dispatch(prompt: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Mecanismo de disparo por defecto: `claude -p --model sonnet <prompt>`
    en modo no interactivo. Sustituible vía el parámetro ``dispatch`` de
    ``run_f26`` — hoy este binario da 401 (credencial revocada, bloqueador
    documentado en el doc F2.6, ajeno a esta pieza); mañana, o en tests, se
    puede pasar cualquier otro callable con la misma firma.

    ``--output-format stream-json --verbose`` (con `--input-format
    stream-json` implícito en el binario real vía ps aux, T2 MAXIMUS Cycle
    14): el stdout final de `claude -p` sin estas flags es solo texto plano,
    invisible a qué tool_use hizo la sesión — 3 de los 6 ítems de la rúbrica
    (2/3/5) necesitan ver la secuencia de tool calls, no solo la respuesta
    final. Con estas flags stdout es JSONL (una línea = un mensaje), y
    ``run_f26`` lo guarda tal cual para que el grading (T2) lo parsee."""
    return subprocess.run(
        ["claude", "-p", "--model", "sonnet", "--output-format", "stream-json", "--verbose", prompt],
        capture_output=True, text=True, cwd=cwd, timeout=1800, check=False,
    )


def _summarize_grading(grading: dict[str, Any]) -> str:
    """Notas legibles para ``record_f26_run`` a partir del veredicto de
    ``grade_f26_transcript``: el score siempre, y si algo falló, qué ítem y
    por qué (usando el propio ``details`` del grading — nunca un "6/6"
    mudo). Recortado a 1000 chars por ``record_f26_run`` igualmente, pero se
    mantiene compacto aquí para que lo importante no se corte primero."""
    score = grading["score"]
    failed_items = [
        item for item in
        ("item_1", "item_2", "item_3", "item_4", "item_5", "item_6")
        if grading[item] == "fail"
    ]
    method_note = (
        "score automático mixto; ítems 1/4/6 son heurística textual, "
        "sin verificación semántica"
    )
    if not failed_items:
        return f"F2.6 {score} — los 6 ítems pasaron ({method_note})"
    lines = [f"F2.6 {score} — {method_note}; ítems fallidos:"]
    for item in failed_items:
        detail = grading["details"].get(item, {})
        reason = detail.get("reason")
        if reason is None:
            reason = ", ".join(f"{k}={v}" for k, v in detail.items())
        lines.append(f"  {item}: {reason}")
    return "\n".join(lines)


def run_f26(
    repo_root: Path,
    *,
    doc_path: Path | None = None,
    dispatch: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    out_dir: Path | None = None,
    state_path: Path | None = None,
    allow_unsafe_legacy_dispatch: bool = False,
) -> dict[str, Any]:
    """Dispara F2.6: construye el prompt desde el doc (fuente única, fail
    closed si no se puede), lanza una sesión fría mediante un dispatcher
    explícito y guarda el transcript crudo en disco bajo
    ``workspace/self_build/f26_runs/``. Si el dispatch tuvo éxito, además
    (T3): gradea el transcript recién guardado con
    ``grade_f26_transcript`` (T2). Un score 6/6 elegible queda
    ``pending_review`` hasta revisión semántica del operador; cualquier score
    menor o transición no elegible queda ``fail``. En ambos casos llama a
    ``record_f26_run`` con notes derivadas de ``details``.

    Si el dispatch FALLÓ (``success=False``, p.ej. el 401 conocido) no hay
    transcript válido que gradear: NO se gradea y NO se llama a
    ``record_f26_run`` — registrar algo aquí falsearía un resultado que
    nunca ocurrió. El dict devuelto refleja esto con ``grading=None``,
    ``overall_result=None``, ``recorded=False``.

    El legacy Claude interno sólo existe tras ``allow_unsafe_legacy_dispatch``;
    la CLI productiva usa el driver agentic. Un ``returncode != 0`` se devuelve
    estructurado en el dict
    (``success=False``, ``error``, ``returncode``, ``stderr``). Una excepción
    del dispatcher o de cualquier paso posterior al ``session.started`` cierra
    la sesión una sola vez como fallo y se eleva como ``F26AuditError``.
    """
    doc = doc_path or (repo_root / _DEFAULT_DOC_PATH)
    prompt = extract_f26_prompt(doc)  # fail closed barato: propaga sin dispatch
    if dispatch is None and not allow_unsafe_legacy_dispatch:
        raise F26AuditError(
            "implicit legacy Claude dispatch is disabled; explicit opt-in required"
        )
    run_sha = _head_sha(repo_root)
    if run_sha == "unknown" or not _commit_exists(repo_root, run_sha):
        raise F26AuditError("F2.6 requires a verifiable initial Git SHA")
    checkout_clean, checkout_detail = _tracked_checkout_status(repo_root)
    if not checkout_clean:
        raise F26AuditError(
            "F2.6 requires a clean checkout (tracked and untracked); "
            f"git status reported: {checkout_detail or 'unverifiable'}"
        )
    merkle = _verified_runtime_merkle()
    writer_lock = _acquire_f26_writer_lock()
    staged_state: Path | None = None

    dispatch_fn: Callable[..., subprocess.CompletedProcess[str]] = (
        dispatch or _default_claude_dispatch
    )
    started_at = datetime.now(timezone.utc).isoformat()
    stamp = started_at.replace(":", "").replace("-", "").replace(".", "")
    task_id = f"f26:{stamp}"
    try:
        started_record = merkle.log(
            action="session.started",
            agent="atlas.f26_gate",
            result="success",
            risk_level="moderate",
            payload={
                "run_sha": run_sha,
                "doc_path": str(doc),
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            },
            task_id=task_id,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        writer_lock.release()
        raise F26AuditError(f"F2.6 start receipt could not be written: {exc}") from exc
    end_attempted = False
    phase = "dispatch"
    dispatch_success: bool | None = None
    finished_sha: str | None = None
    transcript_sha256: str | None = None
    model_calls: list[dict[str, Any]] = []
    f26_record: dict[str, Any] | None = None
    try:
        if dispatch is None:
            proc = dispatch_fn(prompt, repo_root)
        else:
            try:
                signature = inspect.signature(dispatch_fn)
                signature.bind(prompt, repo_root, task_id=task_id)
                accepts_task_id = True
            except TypeError:
                # Se decide ANTES de invocar. Inferir soporte desde un TypeError
                # posterior al efecto podía ejecutar el dispatcher dos veces.
                signature.bind(prompt, repo_root)
                accepts_task_id = False
            except (ValueError, AttributeError) as exc:
                raise F26AuditError(
                    f"dispatcher signature is not inspectable: {exc}"
                ) from exc
            if accepts_task_id:
                proc = dispatch_fn(prompt, repo_root, task_id=task_id)
            else:
                proc = dispatch_fn(prompt, repo_root)
        returncode: int | None = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        success = returncode == 0
        dispatch_success = success
        error = None if success else f"dispatch salió con returncode={returncode}"

        finished_at = datetime.now(timezone.utc).isoformat()
        finished_sha = _head_sha(repo_root)
        head_changed_during_run = run_sha != finished_sha
        checkout_clean_after, checkout_after_detail = _tracked_checkout_status(repo_root)

        phase = "runs_dir"
        runs_dir = out_dir or (repo_root / _DEFAULT_RUNS_DIR)
        runs_dir.mkdir(parents=True, exist_ok=True)
        phase = "transcript"
        transcript_path = runs_dir / f"f26_run_{stamp}.txt"
        transcript_path.write_text(stdout, encoding="utf-8")
        transcript_sha256 = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        phase = "head_transition"
        head_transition = _classify_head_transition(
            repo_root, start_sha=run_sha, finish_sha=finished_sha, transcript=stdout,
            merkle=merkle, task_id=task_id,
            started_receipt_hash=started_record.hash_self,
        )
        if not checkout_clean_after:
            head_transition = {
                "changed": head_changed_during_run,
                "authorized": False,
                "kind": "dirty_checkout",
                "reason": (
                    "tracked or untracked checkout differs from the finish commit: "
                    f"{checkout_after_detail or 'unverifiable'}"
                ),
            }

        model_calls = _model_call_refs(merkle, task_id=task_id)
        record: dict[str, Any] = {
            "success": success,
            "returncode": returncode,
            "error": error,
            "stderr": stderr[:5000],
            "prompt": prompt,
            "doc_path": str(doc),
            "started_at": started_at,
            "finished_at": finished_at,
            "run_sha": run_sha,
            "finished_sha": finished_sha,
            "head_changed_during_run": head_changed_during_run,
            "head_transition": head_transition,
            "transcript_path": str(transcript_path),
            "transcript_sha256": transcript_sha256,
            "task_id": task_id,
            "model_calls": model_calls,
        }
        meta_path = runs_dir / f"f26_run_{stamp}.json"
        record["meta_path"] = str(meta_path)

        if not success:
            # sin transcript válido: gradear o registrar aquí falsearía un
            # resultado que nunca ocurrió (regla explícita del diseño T3).
            record["grading"] = None
            record["automatic_result"] = None
            record["overall_result"] = None
            record["recorded"] = False
            record["f26_record"] = None
            record["audit_receipt"] = {
                "started": _audit_ref(started_record), "finished": None,
            }
            phase = "meta_initial"
            meta_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            phase = "session_end"
            end_attempted = True
            finished_record = _finish_audit_record(
                merkle,
                task_id=task_id,
                result="failure",
                payload={
                    "run_sha": run_sha,
                    "finished_sha": finished_sha,
                    "dispatch_success": False,
                    "error": error,
                    "transcript_sha256": transcript_sha256,
                    "overall_result": None,
                    "state_sha256": None,
                    "state_source": None,
                    "automatic_score": None,
                    "semantic_verification": None,
                    "semantic_review_actor": None,
                    "source_state_sha256": None,
                    "model_calls": model_calls,
                },
            )
            record["audit_receipt"]["finished"] = _audit_ref(finished_record)
            phase = "meta_final"
            _persist_run_meta(meta_path, record)
            return record

        phase = "grading"
        grading = grade_f26_transcript(transcript_path)
        automatic_result = "pass" if grading["score"] == "6/6" else "fail"
        overall_result = (
            "pending_review" if automatic_result == "pass" else "fail"
        )
        notes = _summarize_grading(grading)
        required_transition = (
            "golden_route_commit" if grading["item_3"] == "pass" else None
        )
        transition_eligible = (
            required_transition is None
            or head_transition["kind"] == required_transition
        )
        if not transition_eligible:
            overall_result = "fail"
            notes += (
                f"\nitem_3 exige una transición GoldenRoute verificable: "
                f"{run_sha} -> {finished_sha}; observado={head_transition['kind']}; "
                f"{head_transition['reason']}; "
                "resultado no elegible para PASS"
            )
        elif head_changed_during_run and not bool(head_transition["authorized"]):
            overall_result = "fail"
            notes += (
                f"\nHEAD cambió sin transición verificable: {run_sha} -> {finished_sha}; "
                f"{head_transition['reason']}; resultado no elegible para PASS"
            )
        semantic_verification = grading["grading_method"]["semantic_verification"]
        phase = "state"
        f26_record = record_f26_run(
            repo_root,
            result=overall_result,
            notes=notes,
            state_path=state_path,
            at_sha=run_sha,
            transcript_sha256=transcript_sha256,
            task_id=task_id,
            automatic_score=grading["score"],
            semantic_verification=semantic_verification,
            _state_source="automatic_run",
            _defer_state_publish=True,
            _writer_lock_held=True,
        )
        effective_state_path = _effective_state_path(repo_root, state_path)
        staged_state = _pending_state_path(
            effective_state_path, str(f26_record["state_sha256"]),
        )
        record["grading"] = grading
        record["automatic_result"] = automatic_result
        record["overall_result"] = overall_result
        record["recorded"] = False
        record["f26_record"] = f26_record
        record["audit_receipt"] = {
            "started": _audit_ref(started_record), "finished": None,
        }
        phase = "meta_initial"
        meta_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        phase = "session_end"
        end_attempted = True
        finished_record = _finish_audit_record(
            merkle,
            task_id=task_id,
            result="failure" if overall_result == "fail" else "success",
            payload={
                "run_sha": run_sha,
                "finished_sha": finished_sha,
                "head_transition": head_transition,
                "dispatch_success": True,
                "automatic_score": grading["score"],
                "semantic_verification": semantic_verification,
                "overall_result": overall_result,
                "transcript_sha256": transcript_sha256,
                "state_sha256": f26_record["state_sha256"],
                "state_source": "automatic_run",
                "semantic_review_actor": None,
                "source_state_sha256": None,
                "model_calls": model_calls,
            },
        )
        phase = "state_publish"
        assert staged_state is not None
        _publish_f26_state(staged_state, effective_state_path)
        staged_state = None
        record["audit_receipt"]["finished"] = _audit_ref(finished_record)
        record["recorded"] = True
        phase = "meta_final"
        _persist_run_meta(meta_path, record)
        return record
    except Exception as exc:
        close_error: F26AuditError | None = None
        try:
            model_calls = _model_call_refs(merkle, task_id=task_id)
        except (OSError, RuntimeError, ValueError):
            pass
        if not end_attempted:
            end_attempted = True
            try:
                _finish_audit_record(
                    merkle,
                    task_id=task_id,
                    result="failure",
                    payload={
                        "run_sha": run_sha,
                        "finished_sha": finished_sha,
                        "dispatch_success": dispatch_success,
                        "overall_result": None,
                        "transcript_sha256": transcript_sha256,
                        "state_sha256": (
                            f26_record.get("state_sha256")
                            if f26_record is not None else None
                        ),
                        "model_calls": model_calls,
                        "phase": phase,
                        "failure_type": type(exc).__name__,
                        "failure": str(exc)[:1000],
                    },
                )
            except F26AuditError as audit_exc:
                close_error = audit_exc
        if phase in {"meta_initial", "session_end"} and staged_state is not None:
            staged_state.unlink(missing_ok=True)
        close_detail = (
            f"; end receipt also failed: {close_error}" if close_error else ""
        )
        raise F26AuditError(
            f"F2.6 failed after session.started during {phase}: "
            f"{type(exc).__name__}: {exc}{close_detail}"
        ) from exc
    finally:
        writer_lock.release()
