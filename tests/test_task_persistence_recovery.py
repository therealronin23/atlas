"""Bench de recuperación de TaskPersistence — falsifier de EDR-ADC-WO-069
(`docs/canon/decision_dossiers/EDR-ADR-069-durable-work.md`), ejecutado por
primera vez el 2026-07-31.

El propio EDR lo declaró sin ejecutar: *"Falsifier: recovery tests show
that a selective journal cannot reconstruct an approved task without
hidden mutable state, or a smaller compatible boundary meets the same
recovery contract with less complexity."*

Este test cruza un límite de PROCESO REAL (subprocess, intérprete Python
nuevo) a propósito — es la única forma de descartar de verdad "estado
mutable oculto": un test en el mismo proceso podría pasar por accidente
gracias a algún caché en memoria sin que nadie lo note. Un subproceso nuevo
no comparte NADA salvo el fichero en disco.

Protocolo:
1. Subproceso A: construye una Task, la persiste (AWAITING_APPROVAL), la
   transiciona a EXECUTING (simula "aprobada, ahora en ejecución") y la
   persiste de nuevo -- sale y muere.
2. Subproceso B (intérprete nuevo, sin memoria compartida con A): abre una
   TaskPersistence NUEVA sobre el mismo directorio y hace `load(task_id)`.
3. El test compara campo a campo lo que B reconstruyó contra lo que A
   escribió -- sin fiarse de "no lanzó excepción", cada campo se verifica.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_WRITER_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from pathlib import Path
from atlas.core.contracts import Task, TaskSource, TaskStatus
from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
from atlas.logging.merkle_logger import MerkleLogger

pending_dir = Path({pending_dir!r})
merkle = MerkleLogger(Path({merkle_dir!r}))
store = TaskPersistence(pending_dir, merkle)

task = Task(
    intent={intent!r},
    source=TaskSource.CLI,
    id={task_id!r},
    priority=4,
    sensitivity="high",
    action="bench_recovery",
    status=TaskStatus.AWAITING_APPROVAL,
    tool_name="bash",
    metadata={{"bench": "adc-wo-102", "n": 7}},
)
store.persist(task)

# Simula la aprobación humana: la task avanza a EXECUTING y se persiste
# de nuevo -- esto es lo que ColdUpdateManager/approve_pending hacen antes
# de que este mismo proceso pueda morir (crash, reinicio, kill -9).
task.transition(TaskStatus.EXECUTING)
task.result = {{"approved_by": "bench", "note": "simulated approval"}}
store.persist(task)

print("WRITER_OK")
"""

_READER_SCRIPT = """
import json
import sys
sys.path.insert(0, {src!r})
from pathlib import Path
from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
from atlas.logging.merkle_logger import MerkleLogger

pending_dir = Path({pending_dir!r})
merkle = MerkleLogger(Path({merkle_dir!r}))
# TaskPersistence NUEVA, en un intérprete Python NUEVO -- cero memoria
# compartida con el subproceso escritor. Si esto reconstruye la task, es
# por lo que hay en disco, no por ningún estado oculto.
store = TaskPersistence(pending_dir, merkle)
task = store.load({task_id!r})
if task is None:
    print(json.dumps({{"loaded": False}}))
else:
    print(json.dumps({{
        "loaded": True,
        "id": task.id,
        "intent": task.intent,
        "status": task.status.value,
        "priority": task.priority,
        "sensitivity": task.sensitivity,
        "action": task.action,
        "tool_name": task.tool_name,
        "metadata": task.metadata,
        "result": task.result,
    }}))
"""


def _run(script: str, **fmt: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script.format(**fmt)],
        capture_output=True, text=True, timeout=30, check=False,
        cwd=REPO,
    )


def test_approved_task_survives_a_real_process_restart(tmp_path: Path) -> None:
    pending_dir = tmp_path / "pending_approvals"
    merkle_dir = tmp_path / "merkle"
    task_id = "bench-recovery-0001"
    intent = "aprobar un cambio de config sensible"
    src = str(REPO / "src")

    writer = _run(
        _WRITER_SCRIPT,
        src=src, pending_dir=str(pending_dir), merkle_dir=str(merkle_dir),
        task_id=task_id, intent=intent,
    )
    assert writer.returncode == 0, writer.stderr
    assert "WRITER_OK" in writer.stdout

    reader = _run(
        _READER_SCRIPT,
        src=src, pending_dir=str(pending_dir), merkle_dir=str(merkle_dir),
        task_id=task_id,
    )
    assert reader.returncode == 0, reader.stderr
    result = json.loads(reader.stdout.strip().splitlines()[-1])

    assert result["loaded"] is True, (
        "una task aprobada y persistida en un proceso NO se pudo reconstruir "
        "en otro -- esto falsificaría el EDR"
    )
    assert result["id"] == task_id
    assert result["intent"] == intent
    # El estado reconstruido debe ser EXECUTING (post-aprobación), no
    # AWAITING_APPROVAL (pre-aprobación) -- prueba que la SEGUNDA
    # persistencia (tras transition()) es la que sobrevive, no un snapshot
    # viejo cacheado en algún sitio.
    assert result["status"] == "executing"
    assert result["priority"] == 4
    assert result["sensitivity"] == "high"
    assert result["action"] == "bench_recovery"
    assert result["tool_name"] == "bash"
    assert result["metadata"] == {"bench": "adc-wo-102", "n": 7}
    assert result["result"] == {"approved_by": "bench", "note": "simulated approval"}


def test_merkle_receipt_exists_independent_of_the_json_file(tmp_path: Path) -> None:
    """El EDR pide recuperación auditable, no solo "el JSON existe": el
    receipt Merkle de la persistencia debe existir en su propia cadena,
    verificable sin confiar en el fichero pending_approvals/*.json."""
    pending_dir = tmp_path / "pending_approvals"
    merkle_dir = tmp_path / "merkle"
    task_id = "bench-recovery-0002"
    src = str(REPO / "src")

    writer = _run(
        _WRITER_SCRIPT,
        src=src, pending_dir=str(pending_dir), merkle_dir=str(merkle_dir),
        task_id=task_id, intent="segunda task del bench",
    )
    assert writer.returncode == 0, writer.stderr

    from atlas.logging.merkle_logger import MerkleLogger

    merkle = MerkleLogger(merkle_dir)
    records = [r for r in merkle.read_all() if r.task_id == task_id]
    actions = [r.action for r in records]
    assert "approval.persisted" in actions
    # Dos persist() reales (AWAITING_APPROVAL, luego EXECUTING) -> dos
    # receipts, no uno reusado.
    assert actions.count("approval.persisted") == 2


def test_load_of_unknown_task_id_is_none_not_a_crash(tmp_path: Path) -> None:
    """Contraparte honesta: recuperar un id que nunca se persistió no debe
    fingir éxito ni lanzar -- None es la respuesta fail-honesta."""
    from atlas.core.orchestrator_parts.task_persistence import TaskPersistence
    from atlas.logging.merkle_logger import MerkleLogger

    store = TaskPersistence(tmp_path / "pending_approvals", MerkleLogger(tmp_path / "merkle"))
    assert store.load("nunca-existio") is None
