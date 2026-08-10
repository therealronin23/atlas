"""Los 81 comandos de la CLI se ejecutan, no sólo se declaran.

`interfaces/cli.py` es el fichero peor cubierto del proyecto: 1.279 sentencias
al 58-64%, con 542 sin ejecutar nunca. En esta auditoría la cobertura fue el
mejor predictor de defectos que se probó —los tres módulos peor cubiertos se
llevaron los tres P0— así que el hueco no es cosmético.

Lo que faltaba no era "más tests de la CLI" sino la pregunta barata: **¿arranca
cada comando?** El defecto de `mcp/engineering_trunk.py` de esta semana era un
`TypeError` garantizado en la primera línea útil, invisible para una suite que
nunca lo llamaba. Un `--help` no lo habría visto: `--help` sólo prueba el
decorador.

Este fichero cubre las dos capas:

  1. Los 81 comandos hoja resuelven su `--help` (cableado de opciones y tipos).
  2. Los de sólo lectura se INVOCAN de verdad contra un `ATLAS_HOME` aislado, y
     ninguno puede reventar con una excepción no controlada.

Un código de salida distinto de 0 es legítimo —`doctor` informa de problemas—
así que lo que se fija es la ausencia de traceback, no el éxito. Sólo para los
comandos que se limitan a listar se exige además el 0.

FUERA a propósito: `serve` y `dashboard` levantan servidores (el segundo dio
`address already in use` con el daemon vivo, que es la respuesta correcta y no
un defecto), y todo lo que escribe, aprueba, instala o revoca. Un smoke test no
puede tener efectos secundarios sobre el sistema del operador.
"""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from atlas.interfaces.cli import cli


def _hojas(cmd: click.Command, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if isinstance(cmd, click.Group):
        out: list[tuple[str, ...]] = []
        for nombre, hijo in sorted(cmd.commands.items()):
            out += _hojas(hijo, (*prefix, nombre))
        return out
    return [prefix]


TODOS = _hojas(cli)

#: Sólo lectura: informan y salen. Lista explícita, nunca derivada por nombre —
#: un `update apply` que entrase aquí por parecerse a `update status` ejecutaría
#: una actualización real durante la suite.
SOLO_LECTURA: tuple[tuple[str, ...], ...] = (
    ("status",), ("tools",), ("capabilities",), ("health",), ("doctor",),
    ("insights",), ("pending",), ("memory",), ("corpus-inventory",),
    ("completeness-demo",), ("gates", "list"), ("blocks", "list"),
    ("connections", "catalog"), ("self-audit", "status"),
    ("self-audit", "proposals"), ("self-audit", "report"),
    ("selfbuild", "status"), ("f26", "status"), ("gate-h", "status"),
    ("gate-h", "receipts"), ("update", "status"), ("update", "batch-review"),
    ("plugin", "activation", "list"), ("plugin", "receipt", "list"),
)

#: Comandos de lectura que exigen un argumento posicional. Van aparte porque
#: `test_la_lista_de_lectura_existe_de_verdad` comprueba contra el árbol de
#: comandos, y `("search", "watchdog")` no es una hoja: es `search` con un
#: término. Ese test cazó justo esta confusión al escribir el fichero.
CON_ARGUMENTO: tuple[tuple[str, ...], ...] = (
    ("search", "watchdog"),
)

#: De éstos sí se exige el 0: se limitan a enumerar lo que hay. Los demás
#: pueden salir distinto de cero informando de un problema real del sistema.
DEBEN_SALIR_CERO: frozenset[tuple[str, ...]] = frozenset({
    ("tools",), ("capabilities",), ("gates", "list"), ("blocks", "list"),
    ("connections", "catalog"), ("selfbuild", "status"), ("update", "status"),
    ("self-audit", "status"), ("f26", "status"), ("gate-h", "status"),
    ("plugin", "activation", "list"), ("plugin", "receipt", "list"),
})


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """`ATLAS_HOME` aislado: la suite no puede tocar el estado del operador."""
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    return CliRunner()


def test_el_arbol_de_comandos_no_se_encoge() -> None:
    """Si un refactor pierde un subcomando por el camino, este test lo dice.
    81 medidos el 2026-08-10; el umbral es a la baja, añadir no molesta."""
    assert len(TODOS) >= 81, f"la CLI expone {len(TODOS)} comandos, había 81"


@pytest.mark.parametrize("cmd", TODOS, ids=lambda c: " ".join(c))
def test_cada_comando_resuelve_su_help(cmd: tuple[str, ...], runner: CliRunner) -> None:
    """Cablear mal un `type=` o un `default=` sólo se ve al construir el
    comando, y sin esto no lo construía nadie."""
    resultado = runner.invoke(cli, [*cmd, "--help"])

    assert resultado.exit_code == 0, resultado.output[-500:]


@pytest.mark.parametrize(
    "cmd", (*SOLO_LECTURA, *CON_ARGUMENTO), ids=lambda c: " ".join(c)
)
def test_los_comandos_de_lectura_no_revientan(
    cmd: tuple[str, ...], runner: CliRunner
) -> None:
    """El caso `engineering_trunk`: un `TypeError` en la primera línea útil que
    ninguna suite veía porque ninguna suite lo llamaba."""
    resultado = runner.invoke(cli, list(cmd))

    excepcion = resultado.exception
    assert excepcion is None or isinstance(excepcion, SystemExit), (
        f"{' '.join(cmd)} lanzó {type(excepcion).__name__}: {excepcion}\n"
        f"{resultado.output[-800:]}"
    )


@pytest.mark.parametrize("cmd", sorted(DEBEN_SALIR_CERO), ids=lambda c: " ".join(c))
def test_los_comandos_que_solo_enumeran_salen_cero(
    cmd: tuple[str, ...], runner: CliRunner
) -> None:
    resultado = runner.invoke(cli, list(cmd))

    assert resultado.exit_code == 0, resultado.output[-800:]


def test_la_lista_de_lectura_existe_de_verdad() -> None:
    """Un comando renombrado dejaría su entrada apuntando al vacío, y el test
    de arriba pasaría en verde sin ejecutar nada — un test dormido."""
    conocidos = set(TODOS)
    huerfanos = [" ".join(c) for c in (*SOLO_LECTURA, *DEBEN_SALIR_CERO)
                 if c not in conocidos]

    assert not huerfanos, f"entradas que ya no existen en la CLI: {huerfanos}"


def test_ningun_comando_con_efectos_se_cuela_en_la_lista() -> None:
    """Barrera de lectura sobre la propia lista: si alguien añade aquí un
    `apply`, `install`, `approve`, `revoke`… la suite ejecutaría la acción real
    sobre la máquina del operador."""
    prohibidos = ("apply", "install", "approve", "revoke", "reject", "activate",
                  "materialize", "admit-third-party", "unblock", "pause",
                  "resume", "run", "serve", "dashboard", "cycle", "sweep",
                  "record-run", "stop", "decline", "test")
    coladas = [" ".join(c) for c in (*SOLO_LECTURA, *CON_ARGUMENTO)
               if c[0] in prohibidos or c[-1] in prohibidos]

    assert not coladas, f"comandos con efectos en la lista de lectura: {coladas}"


# ---------------------------------------------------------------------------
# Las ramas CON DATOS, que son las que nunca se ejecutan
# ---------------------------------------------------------------------------
#
# Varios comandos de lectura sí se invocan arriba, y aun así su parte
# interesante seguía a oscuras: se ejecutaban con el sistema VACÍO y salían por
# el `if not items: return`. Toda la construcción de tablas —donde vive el
# formateo, los colores condicionales y los `to_dict()`— no la había corrido
# nadie. Medido el 2026-08-10: `blocks_list` 11 de 18 sentencias sin ejecutar,
# `search` 10 de 20, con ambos comandos "cubiertos".


def test_blocks_list_pinta_la_tabla_cuando_hay_bloques(runner: CliRunner) -> None:
    """La rama vacía ya se ejercitaba; la de la tabla, con su color condicional
    por bloque lleno, no la había ejecutado nunca nadie."""
    from atlas.interfaces.cli import get_orchestrator

    mem = get_orchestrator().block_memory
    mem.create("persona", value="x" * 30, limit=40, description="quién soy")
    mem.create("lleno", value="y" * 20, limit=20, description="al límite")

    resultado = runner.invoke(cli, ["blocks", "list"])

    assert resultado.exit_code == 0, resultado.output
    assert "persona" in resultado.output
    assert "lleno" in resultado.output


def test_blocks_list_en_json_serializa_los_bloques(runner: CliRunner) -> None:
    import json as _json

    from atlas.interfaces.cli import get_orchestrator

    get_orchestrator().block_memory.create("persona", value="hola", description="d")

    resultado = runner.invoke(cli, ["blocks", "list", "--json"])

    assert resultado.exit_code == 0, resultado.output
    etiquetas = [b["label"] for b in _json.loads(resultado.output)]
    assert "persona" in etiquetas


def test_search_pinta_los_resultados_encontrados(runner: CliRunner) -> None:
    """`search` sobre un ledger vacío salía por "sin resultados". La tabla y el
    recorte de campos no se ejecutaban."""
    from atlas.interfaces.cli import get_orchestrator

    orch = get_orchestrator()
    orch._merkle.log(
        action="prueba.marcador", agent="test", result="success",
        payload={"detalle": "buscable"}, task_id="t-cli",
    )

    resultado = runner.invoke(cli, ["search", "marcador"])

    assert resultado.exit_code == 0, resultado.output
    assert "prueba.marcador" in resultado.output.replace("\n", "")


def test_search_sin_resultados_lo_dice(runner: CliRunner) -> None:
    resultado = runner.invoke(cli, ["search", "cadenaquenoexisteenningunsitio"])

    assert resultado.exit_code == 0
    assert "Sin resultados" in resultado.output


def test_connections_plan_con_una_receta_real(runner: CliRunner) -> None:
    """Se invocaba sin argumento (rc=2, error de uso) y el cuerpo no corría."""
    resultado = runner.invoke(cli, ["connections", "plan", "gmail"])

    assert resultado.exception is None or isinstance(resultado.exception, SystemExit)
    assert resultado.exit_code == 0, resultado.output


def test_connections_plan_con_receta_desconocida_sale_1(runner: CliRunner) -> None:
    """Rama de error: un id inventado tiene que salir 1, no reventar."""
    resultado = runner.invoke(cli, ["connections", "plan", "no-existe-esta-receta"])

    assert resultado.exit_code == 1
    assert "desconocida" in resultado.output


def test_gate_h_validate_con_patron_inexistente(runner: CliRunner) -> None:
    """Rama de "no encontrado", que es la única alcanzable sin fabricar un
    patrón aprobado con su fingerprint de entorno."""
    resultado = runner.invoke(cli, ["gate-h", "validate", "patron-que-no-existe"])

    assert resultado.exit_code == 0, resultado.output
    assert "no encontrado" in resultado.output.lower()


def test_security_audit_pinta_los_hallazgos(runner: CliRunner, tmp_path: Path) -> None:
    """La rama "sin hallazgos" es la única que se ejercitaba. La tabla con
    severidad, CWE y localización —12 de 19 sentencias— no la corría nadie."""
    objetivo = tmp_path / "vulnerable.py"
    objetivo.write_text(
        "import subprocess\n"
        "def run(cmd):\n"
        "    return subprocess.run(cmd, shell=True)\n",
        encoding="utf-8",
    )

    resultado = runner.invoke(cli, ["security-audit", str(objetivo)])

    assert resultado.exception is None or isinstance(resultado.exception, SystemExit), (
        resultado.output
    )
    assert resultado.exit_code == 0, resultado.output


def test_security_audit_en_json_serializa(runner: CliRunner, tmp_path: Path) -> None:
    import json as _json

    objetivo = tmp_path / "limpio.py"
    objetivo.write_text("VALOR = 1\n", encoding="utf-8")

    resultado = runner.invoke(cli, ["security-audit", str(objetivo), "--json"])

    assert resultado.exit_code == 0, resultado.output
    assert isinstance(_json.loads(resultado.output), list)


def test_reality_pinta_el_informe(runner: CliRunner) -> None:
    """`atlas reality` es la fuente factual del proyecto y su renderizado —no el
    `--json`, el de la tabla— nunca se había ejecutado en la suite. Hace sondas
    en vivo (~3 s), así que no se le exige código de salida: lo que se fija es
    que no reviente."""
    resultado = runner.invoke(cli, ["reality"])

    assert resultado.exception is None or isinstance(resultado.exception, SystemExit), (
        f"{type(resultado.exception).__name__}: {resultado.exception}\n"
        f"{resultado.output[-600:]}"
    )
    assert resultado.output.strip(), "reality no imprimió nada"
