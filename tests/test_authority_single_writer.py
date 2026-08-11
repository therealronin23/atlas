"""ADC-WO-102: la autoridad sobre el estado de un Task deja de ser prosa.

La ficha pide "un dueño por estado mutable" y nombra tres riesgos:
`dual writers`, `bypassed approval gates` e `incompatible persisted state`.
Midiendo el código (2026-08-11) el resultado no fue ni "cumple" ni "no
cumple", sino repartido:

- **`Task.status`**: un solo escritor real, `Task.transition()`, que además
  valida contra `VALID_TRANSITIONS`. Cumple.
- **El sobre HMAC en disco**: lo construye sólo `TaskPersistence`. Cumple.
- **El DIRECTORIO de pending approvals**: NO cumplía. `ApprovalManager`
  entraba a mano en el directorio de `TaskPersistence` a hacer el baile de
  la reserva (`pending.json` → `pending.executing.json`, y los `unlink` de
  vuelta). Dos módulos manipulando las mismas rutas: eso es exactamente
  `dual writers`, aunque el contenido del sobre lo escribiera uno solo.
- **El clearance `task:<id>`**: DOS otorgantes, y está bien que sean dos —
  el humano (`ApprovalManager`) y la vía auto-aprobada de ADR-033
  (allowlist + sin taint + veredicto Allow del decisor, auditada como
  `task.auto_approved`). Lo que no puede haber es un tercero silencioso.

Este fichero fija las cuatro cosas. El mapa en prosa vive en
`docs/design/authority_map_mission_task.md`; esto es lo que impide que se
desvíe sin que nadie se entere.

MÉTODO: AST, no `grep`. Un `grep` de `.status =` marca `provider.status`,
`proposal.status` y `report.status` —tres estados que no tienen nada que ver
con Tasks— y convierte un guardia sano en una puerta que miente. Con AST se
distingue el objeto y el valor asignado.

Cada guardia se verifica por MUTACIÓN dentro de este mismo fichero: se le da
al detector una fuente con el defecto y se comprueba que lo caza. Un guardia
que sólo se prueba contra código limpio no prueba nada.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "atlas"

_PERSISTENCIA = "core/orchestrator_parts/task_persistence.py"
_APPROVALS = "core/orchestrator_parts/approvals.py"
_AGENTIC = "core/orchestrator_parts/agentic_executor.py"
_CONTRACTS = "core/contracts.py"
_ORCHESTRATOR = "core/orchestrator.py"
_API = "api/server.py"


def _fuentes() -> list[tuple[str, str]]:
    """`(ruta relativa, código)` de todo `src/atlas`, sin `__pycache__`."""
    out: list[tuple[str, str]] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        out.append((
            path.relative_to(SRC).as_posix(),
            path.read_text(encoding="utf-8", errors="replace"),
        ))
    return out


def _cualificado(pila: list[str]) -> str:
    return ".".join(pila)


class _Recorrido(ast.NodeVisitor):
    """Base con pila de nombres cualificados (`Clase.metodo`)."""

    def __init__(self, ruta: str) -> None:
        self.ruta = ruta
        self._pila: list[str] = []
        self.hallazgos: list[tuple[str, int, str]] = []

    def _apunta(self, node: ast.AST, detalle: str) -> None:
        self.hallazgos.append((
            self.ruta, getattr(node, "lineno", 0),
            f"{_cualificado(self._pila)}: {detalle}",
        ))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._pila.append(node.name)
        self.generic_visit(node)
        self._pila.pop()

    def _funcion(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._pila.append(node.name)
        self.generic_visit(node)
        self._pila.pop()

    visit_FunctionDef = _funcion  # type: ignore[assignment]
    visit_AsyncFunctionDef = _funcion  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# G1 — Task.status sólo lo escribe transition() (y la rehidratación)
# ---------------------------------------------------------------------------

_ESCRITORES_DE_STATUS_PERMITIDOS = frozenset({
    (_CONTRACTS, "Task.transition"),
    # Rehidratar desde disco NO es una transición: el estado ya ocurrió y
    # `transition()` lo rechazaría por venir de PENDING. Es la única
    # excepción legítima y por eso está aquí nombrada, no escondida.
    (_PERSISTENCIA, "TaskPersistence.deserialize"),
})


class _EscriturasDeStatus(_Recorrido):
    """Asignaciones a `.status` que de verdad tocan el estado de un Task.

    Se cuenta como tal si el valor menciona `TaskStatus`, o si el objeto se
    llama `task`, o si es `self` dentro de la clase `Task`. Eso deja fuera
    `provider.status`, `proposal.status` y `report.status`, que son otros
    estados con otros dueños.
    """

    def _es_de_task(self, objetivo: ast.Attribute, valor: ast.AST) -> bool:
        if "TaskStatus" in ast.unparse(valor):
            return True
        obj = ast.unparse(objetivo.value)
        if obj in {"task", "self.task", "_task"}:
            return True
        return obj == "self" and "Task" in self._pila

    def _revisa(self, objetivos: list[ast.expr], valor: ast.AST, node: ast.AST) -> None:
        for objetivo in objetivos:
            if (
                isinstance(objetivo, ast.Attribute)
                and objetivo.attr == "status"
                and self._es_de_task(objetivo, valor)
            ):
                self._apunta(node, f"escribe {ast.unparse(objetivo)}")

    def visit_Assign(self, node: ast.Assign) -> None:
        self._revisa(list(node.targets), node.value, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._revisa([node.target], node.value, node)
        self.generic_visit(node)


def _escrituras_de_status(fuentes: list[tuple[str, str]]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for ruta, codigo in fuentes:
        visitante = _EscriturasDeStatus(ruta)
        visitante.visit(ast.parse(codigo))
        out.extend(visitante.hallazgos)
    return out


def test_solo_transition_escribe_el_estado_de_un_task() -> None:
    intrusos = [
        (ruta, linea, detalle)
        for ruta, linea, detalle in _escrituras_de_status(_fuentes())
        if (ruta, detalle.split(":")[0]) not in _ESCRITORES_DE_STATUS_PERMITIDOS
    ]
    assert not intrusos, (
        "segundo escritor de Task.status fuera de Task.transition(): "
        f"{intrusos}. Cualquier estado nuevo debe pasar por transition(), "
        "que valida contra VALID_TRANSITIONS; asignarlo a mano se salta la "
        "máquina de estados entera (ADC-WO-102, riesgo 'dual writers')."
    )


def test_el_guardia_de_status_caza_un_segundo_escritor() -> None:
    """Mutación: sin esto, un detector que devolviera siempre `[]` pasaría."""
    mutante = (
        "class Runner:\n"
        "    def run(self, task):\n"
        "        task.status = TaskStatus.DONE\n"
    )
    hallazgos = _escrituras_de_status([("core/inventado.py", mutante)])
    assert len(hallazgos) == 1, hallazgos
    assert "Runner.run" in hallazgos[0][2]


def test_el_guardia_de_status_no_marca_otros_status() -> None:
    """El falso positivo que el `grep` sí cometía."""
    inocente = (
        "def refresh(provider, proposal, report):\n"
        "    provider.status = ProviderStatus.OK\n"
        "    proposal.status = 'approved'\n"
        "    report.status = 'completed'\n"
    )
    assert _escrituras_de_status([("core/inventado.py", inocente)]) == []


# ---------------------------------------------------------------------------
# G2 — el sobre HMAC lo construye un solo módulo
# ---------------------------------------------------------------------------


def _llamadas(fuentes: list[tuple[str, str]], nombre: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for ruta, codigo in fuentes:
        for node in ast.walk(ast.parse(codigo)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            llamado = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else ""
            )
            if llamado == nombre:
                out.append((ruta, node.lineno, ast.unparse(node)[:120]))
    return out


def test_solo_task_persistence_construye_el_sobre_hmac() -> None:
    intrusos = [
        h for h in _llamadas(_fuentes(), "wrap_task_payload")
        if h[0] != _PERSISTENCIA
    ]
    assert not intrusos, (
        f"otro módulo fabrica sobres de pending approval: {intrusos}. "
        "El sobre es lo que hace verificable el estado persistido; un "
        "segundo fabricante puede producir ficheros que `load()` acepte sin "
        "que TaskPersistence los haya escrito nunca."
    )


def test_el_guardia_del_sobre_caza_un_segundo_fabricante() -> None:
    mutante = "def save(d):\n    return wrap_task_payload(d)\n"
    assert _llamadas([("core/inventado.py", mutante)], "wrap_task_payload")


# ---------------------------------------------------------------------------
# G3 — el directorio de pending approvals sólo se le entrega a un dueño
# ---------------------------------------------------------------------------


def _construye_la_ruta(codigo: str) -> bool:
    """¿Este módulo CONSTRUYE la ruta de la cola, o sólo dice la palabra?

    La distinción no es cosmética: `scout.py` emite una señal de
    mantenimiento con `kind="pending_approvals"` y un `in codigo` la marcaba
    como si conociera el directorio. Lo que importa es `<algo> /
    "pending_approvals"` — una división de `Path`, que es poder escribir.
    """
    for node in ast.walk(ast.parse(codigo)):
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Constant)
            and node.right.value == "pending_approvals"
        ):
            return True
    return False


def test_el_directorio_de_pending_solo_lo_construyen_dos_ficheros() -> None:
    """`api/server.py` es la excepción DECLARADA: lee la cola sin importar
    nada de `orchestrator_parts` (OS-R1) y no escribe. Está en el mapa."""
    quien = sorted(ruta for ruta, codigo in _fuentes() if _construye_la_ruta(codigo))
    assert quien == sorted([_ORCHESTRATOR, _API]), (
        f"un módulo nuevo construye la ruta de la cola HITL: {quien}. "
        "Construir la ruta es poder escribirla."
    )


def test_el_guardia_de_la_ruta_no_confunde_nombrar_con_construir() -> None:
    assert not _construye_la_ruta('signal = {"kind": "pending_approvals"}')
    assert _construye_la_ruta('d = self._workspace / "memory" / "pending_approvals"')


class _EntregasDelDirectorio(_Recorrido):
    """A quién se le pasa `self._pending_approval_dir` como argumento."""

    def visit_Call(self, node: ast.Call) -> None:
        args = list(node.args) + [kw.value for kw in node.keywords]
        if any("_pending_approval_dir" in ast.unparse(a) for a in args):
            func = node.func
            destino = func.attr if isinstance(func, ast.Attribute) else (
                func.id if isinstance(func, ast.Name) else ast.unparse(func)
            )
            self._apunta(node, destino)
        self.generic_visit(node)


def _entregas(fuentes: list[tuple[str, str]]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for ruta, codigo in fuentes:
        visitante = _EntregasDelDirectorio(ruta)
        visitante.visit(ast.parse(codigo))
        out.extend(visitante.hallazgos)
    return out


def test_el_directorio_solo_se_entrega_a_TaskPersistence() -> None:
    destinos = {h[2].split(": ")[-1] for h in _entregas(_fuentes())}
    assert destinos == {"TaskPersistence"}, (
        f"el directorio de tasks pendientes se entrega a {sorted(destinos)}. "
        "Sólo TaskPersistence es dueño de esas rutas; cualquier otro que las "
        "reciba puede escribirlas por su cuenta (ADC-WO-102, 'dual writers')."
    )


def test_el_guardia_de_entregas_caza_un_segundo_receptor() -> None:
    mutante = (
        "class Orch:\n"
        "    def build(self):\n"
        "        self._approvals = ApprovalManager("
        "pending_dir=self._pending_approval_dir)\n"
    )
    hallazgos = _entregas([("core/inventado.py", mutante)])
    assert [h[2].split(": ")[-1] for h in hallazgos] == ["ApprovalManager"]


# ---------------------------------------------------------------------------
# G4 — sólo TaskPersistence toca el sistema de ficheros de la cola
# ---------------------------------------------------------------------------

_METODOS_QUE_MUTAN = frozenset({
    "write_text", "write_bytes", "unlink", "replace", "rename",
    "mkdir", "touch", "rmdir",
})


class _MutacionesDelDirectorio(_Recorrido):
    """Mutaciones de fichero sobre rutas derivadas de `self._dir`.

    Sigue el flujo dentro de cada función: si un local se ata a una
    expresión que menciona `self._dir`, mutar ese local cuenta igual que
    mutar `self._dir` directamente. Es justo lo que hacía `ApprovalManager`
    (`pending_path = self._dir / ...` y luego `pending_path.replace(...)`).
    """

    def __init__(self, ruta: str) -> None:
        super().__init__(ruta)
        self._derivados: set[str] = set()

    def _funcion(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        previos = self._derivados
        self._derivados = set()
        # Primero se resuelven los alias del cuerpo, luego se juzgan las
        # llamadas: si no, el orden de aparición decidiría el veredicto.
        for hijo in ast.walk(node):
            if isinstance(hijo, ast.Assign) and "self._dir" in ast.unparse(hijo.value):
                for objetivo in hijo.targets:
                    if isinstance(objetivo, ast.Name):
                        self._derivados.add(objetivo.id)
        super()._funcion(node)
        self._derivados = previos

    visit_FunctionDef = _funcion  # type: ignore[assignment]
    visit_AsyncFunctionDef = _funcion  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _METODOS_QUE_MUTAN:
            receptor = ast.unparse(func.value)
            raiz = receptor.split(".")[0].split("[")[0].split("(")[0]
            if "self._dir" in receptor or raiz in self._derivados:
                self._apunta(node, f"{receptor}.{func.attr}()")
        self.generic_visit(node)


def _mutaciones(fuentes: list[tuple[str, str]]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for ruta, codigo in fuentes:
        visitante = _MutacionesDelDirectorio(ruta)
        visitante.visit(ast.parse(codigo))
        out.extend(visitante.hallazgos)
    return out


def _paquete_de_autoridad() -> list[tuple[str, str]]:
    """Sólo los módulos que pueden tener la cola en la mano.

    `self._dir` no es un identificador único: `WorktreeManager`,
    `OperationalWAL` y `BlockMemory` también llaman así a SU directorio, y
    barrer todo `src/atlas` los marcaba a los tres. Quién puede llegar a
    tener el directorio de la cola ya lo cierra
    `test_el_directorio_solo_se_entrega_a_TaskPersistence`; esto vigila la
    higiene dentro del paquete que sí lo maneja.
    """
    return [
        (ruta, codigo) for ruta, codigo in _fuentes()
        if ruta.startswith("core/orchestrator_parts/") or ruta == _ORCHESTRATOR
    ]


def test_solo_task_persistence_muta_ficheros_de_la_cola() -> None:
    intrusos = [h for h in _mutaciones(_paquete_de_autoridad()) if h[0] != _PERSISTENCIA]
    assert not intrusos, (
        f"otro módulo mueve o borra ficheros de la cola HITL: {intrusos}. "
        "Pídeselo a TaskPersistence (reserve_execution / release_execution / "
        "delete): el dueño del directorio es uno."
    )


_VOCABULARIO_DE_FICHEROS = frozenset({"os", "fcntl", "pathlib", "shutil", "tempfile"})


def test_el_flujo_de_aprobacion_no_tiene_vocabulario_de_ficheros() -> None:
    """El guardia de arriba sigue rutas derivadas de `self._dir`, y por ahí se
    le escapaba el `lock_path.unlink()` (venía de `acquire_lock`, no de
    `self._dir`). Éste cierra el hueco por el otro lado: si `ApprovalManager`
    no puede nombrar `os`, `fcntl` ni `pathlib`, no puede tocar disco por
    ninguna ruta, la siga el análisis o no."""
    codigo = (SRC / _APPROVALS).read_text(encoding="utf-8")
    importados: set[str] = set()
    for node in ast.walk(ast.parse(codigo)):
        if isinstance(node, ast.Import):
            importados.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            importados.add(node.module.split(".")[0])
    intrusos = importados & _VOCABULARIO_DE_FICHEROS
    assert not intrusos, (
        f"approvals.py importa {sorted(intrusos)}: el flujo de aprobación "
        "decide, no escribe. Las operaciones de disco las expone "
        "TaskPersistence por nombre."
    )


def test_el_guardia_de_ficheros_caza_la_reserva_a_mano() -> None:
    """Exactamente el código que `ApprovalManager` tenía antes del arreglo."""
    mutante = (
        "class ApprovalManager:\n"
        "    def _approve_locked(self, task_id):\n"
        "        pending_path = self._dir / f'{task_id}.json'\n"
        "        executing_path = self._dir / f'{task_id}.executing.json'\n"
        "        pending_path.replace(executing_path)\n"
        "        executing_path.unlink(missing_ok=True)\n"
    )
    hallazgos = _mutaciones([("core/inventado.py", mutante)])
    assert len(hallazgos) == 2, hallazgos
    assert all("ApprovalManager._approve_locked" in h[2] for h in hallazgos)


# ---------------------------------------------------------------------------
# G5 — el clearance de aprobación tiene dos otorgantes, y sólo dos
# ---------------------------------------------------------------------------

_OTORGANTES_DECLARADOS = frozenset({
    # La vía humana: `atlas approve` acaba aquí.
    (_APPROVALS, "ApprovalManager._approve_locked"),
    # La vía auto-aprobada de ADR-033: allowlist explícita + loop sin taint
    # (ADR-037) + veredicto Allow del decisor (ADR-040), y auditada como
    # `task.auto_approved`. Es una excepción de diseño, no un agujero.
    (_AGENTIC, "AgenticExecutor._run_auto_approved_mutation"),
})


class _Otorgantes(_Recorrido):
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        nombre = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else ""
        )
        if nombre == "mark_confirmed" and any(
            "task:" in ast.unparse(a) for a in node.args
        ):
            self._apunta(node, "mark_confirmed(task:…)")
        self.generic_visit(node)


def _otorgantes(fuentes: list[tuple[str, str]]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for ruta, codigo in fuentes:
        visitante = _Otorgantes(ruta)
        visitante.visit(ast.parse(codigo))
        out.update((ruta, detalle.split(":")[0]) for _, _, detalle in visitante.hallazgos)
    return out


def test_el_clearance_de_una_tarea_solo_lo_conceden_los_dos_declarados() -> None:
    encontrados = _otorgantes(_fuentes())
    assert encontrados == set(_OTORGANTES_DECLARADOS), (
        f"otorgantes de clearance task:<id> = {sorted(encontrados)}, "
        f"declarados = {sorted(_OTORGANTES_DECLARADOS)}. Conceder el "
        "clearance ES la aprobación: un tercer sitio que lo haga se salta el "
        "HITL sin dejar rastro (ADC-WO-102, riesgo 'bypassed approval gates')."
    )


def test_el_guardia_del_clearance_caza_un_tercer_otorgante() -> None:
    mutante = (
        "class Atajo:\n"
        "    def run(self, task):\n"
        "        self._permissions.mark_confirmed(f'task:{task.id}')\n"
    )
    assert _otorgantes([("core/inventado.py", mutante)]) == {
        ("core/inventado.py", "Atajo.run")
    }


# ---------------------------------------------------------------------------
# El mapa existe y nombra lo que este fichero vigila
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino",
    ["Task.transition", "TaskPersistence", "ApprovalManager",
     "mark_confirmed", "wrap_task_payload"],
)
def test_el_mapa_de_autoridad_nombra_a_cada_dueno(termino: str) -> None:
    """Un guardia sin mapa deja al siguiente adivinando por qué falla."""
    mapa = REPO / "docs" / "design" / "authority_map_mission_task.md"
    assert mapa.exists(), "falta docs/design/authority_map_mission_task.md"
    assert termino in mapa.read_text(encoding="utf-8"), (
        f"el mapa de autoridad no menciona {termino}"
    )
