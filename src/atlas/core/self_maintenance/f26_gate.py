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
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from atlas.core.git_env import clean_git_env
from atlas.core.self_maintenance.f26_grading import grade_f26_transcript

_DEFAULT_STATE_PATH = "workspace/self_build/f26_gate_state.json"
_ADR_PREFIX = "docs/decisions/adr/"

# item 1 del diseño (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md):
# `atlas f26 run` dispara la rúbrica. El prompt NUNCA se copia a mano aquí —
# se parsea del doc en tiempo de ejecución, fuente única.
_DEFAULT_DOC_PATH = "docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md"
_DEFAULT_RUNS_DIR = "workspace/self_build/f26_runs"
_PROMPT_SECTION_HEADING = "## Cómo ejecutarlo"


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
        "2. Corre `atlas f26 run --json`. Esto dispara una sesión Sonnet "
        "fría real que ejecuta la rúbrica de sucesión (hasta ~30 min) — "
        "gradea el transcript y se AUTO-REGISTRA vía record_f26_run al "
        "terminar; no hace falta ningún paso manual adicional después.\n"
        "3. Si el dispatch falla (p.ej. credencial de `claude -p` "
        "revocada, 401 — bloqueador conocido), reporta el error tal cual "
        "salga; no se registra nada porque no hay transcript válido.\n"
        "4. Si el veredicto (`overall_result`) es 'fail', el propio "
        "output lista qué ítems (item_1..item_6) fallaron y por qué — "
        "la regla del diseño es 'cada fallo = gap → arreglar → repetir "
        "la rúbrica ENTERA', no hay aprobado parcial.\n"
        "5. Si es 'pass' (6/6), no hace falta nada más: ya quedó "
        "registrado y el gate volverá a 'current'."
    )
    return {"title": title, "tldr": tldr, "prompt": prompt}


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
    if not failed_items:
        return f"F2.6 {score} — los 6 ítems pasaron"
    lines = [f"F2.6 {score} — ítems fallidos:"]
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
    dispatch: Callable[[str, Path], subprocess.CompletedProcess[str]] | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """Dispara F2.6: construye el prompt desde el doc (fuente única, fail
    closed si no se puede), lanza una sesión fría vía ``dispatch`` (por
    defecto ``claude -p --model sonnet --output-format stream-json
    --verbose``) y guarda el transcript crudo en disco bajo
    ``workspace/self_build/f26_runs/``. Si el dispatch tuvo éxito, además
    (T3, este mismo paso, sin intervención manual): gradea el transcript
    recién guardado con ``grade_f26_transcript`` (T2), decide el veredicto
    global — ``"pass"`` solo si ``score == "6/6"``, ``"fail"`` en cualquier
    otro caso (regla dura del doc: "cada fallo = gap → arreglar → repetir
    ENTERO", no hay aprobado parcial) — y llama a ``record_f26_run`` él
    mismo con ese resultado y unas notes legibles derivadas de ``details``.

    Si el dispatch FALLÓ (``success=False``, p.ej. el 401 conocido) no hay
    transcript válido que gradear: NO se gradea y NO se llama a
    ``record_f26_run`` — registrar algo aquí falsearía un resultado que
    nunca ocurrió. El dict devuelto refleja esto con ``grading=None``,
    ``overall_result=None``, ``recorded=False``.

    Un fallo del dispatcher (returncode != 0, o una excepción como binario
    ausente) NUNCA se silencia: se devuelve estructurado en el dict
    (``success=False``, ``error``, ``returncode``, ``stderr``)."""
    doc = doc_path or (repo_root / _DEFAULT_DOC_PATH)
    prompt = extract_f26_prompt(doc)  # fail closed: propaga sin disparar nada

    dispatch_fn = dispatch or _default_claude_dispatch
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        proc = dispatch_fn(prompt, repo_root)
        returncode: int | None = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        success = returncode == 0
        error = None if success else f"dispatch salió con returncode={returncode}"
    except (OSError, subprocess.SubprocessError) as exc:
        returncode = None
        stdout = ""
        stderr = ""
        success = False
        error = f"{type(exc).__name__}: {exc}"
    finished_at = datetime.now(timezone.utc).isoformat()

    runs_dir = out_dir or (repo_root / _DEFAULT_RUNS_DIR)
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = started_at.replace(":", "").replace("-", "").replace(".", "")
    transcript_path = runs_dir / f"f26_run_{stamp}.txt"
    transcript_path.write_text(stdout, encoding="utf-8")

    record: dict[str, Any] = {
        "success": success,
        "returncode": returncode,
        "error": error,
        "stderr": stderr[:5000],
        "prompt": prompt,
        "doc_path": str(doc),
        "started_at": started_at,
        "finished_at": finished_at,
        "transcript_path": str(transcript_path),
    }
    meta_path = runs_dir / f"f26_run_{stamp}.json"
    meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    record["meta_path"] = str(meta_path)

    if not success:
        # sin transcript válido: gradear o registrar aquí falsearía un
        # resultado que nunca ocurrió (regla explícita del diseño T3).
        record["grading"] = None
        record["overall_result"] = None
        record["recorded"] = False
        record["f26_record"] = None
        return record

    grading = grade_f26_transcript(transcript_path)
    overall_result = "pass" if grading["score"] == "6/6" else "fail"
    notes = _summarize_grading(grading)
    f26_record = record_f26_run(repo_root, result=overall_result, notes=notes)

    record["grading"] = grading
    record["overall_result"] = overall_result
    record["recorded"] = True
    record["f26_record"] = f26_record
    return record
