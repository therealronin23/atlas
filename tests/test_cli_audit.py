"""`atlas audit` contra un ledger Merkle REAL (t8).

Corrige una conclusión mía del 2026-08-09. Dije que lo que quedaba sin cubrir
en `interfaces/cli.py` sólo se alcanzaba sustituyendo por dobles todo lo que
esos comandos hacen —el teatro de tests que la propia aceptación de t8
prohíbe— y por eso propuse cerrar el ítem sin tocarlo.

Cierto de `cycle` (44 sentencias: Cónclave, workers paralelos e inferencia).
**Falso de `audit`** (41 sentencias), que es el segundo bloque más grande:
lee un log Merkle y verifica la cadena. Eso se ejercita con un ledger de
verdad, sin doblar nada, y encima es el comando que responde "¿alguien tocó el
registro?".

Medido: la CLI estaba en 79% con la suite completa (5716 tests) y el objetivo
de t8 eran 80. Estos 41 statements son justo el punto que faltaba — pero el
motivo para escribirlos no es el porcentaje, es que la verificación de
integridad de la cadena no tenía ni una prueba desde la CLI.

Lo que se ejercita de verdad: `MerkleLogger` escribe, `verify_chain()` lee, y
el test **corrompe el fichero a mano** para comprobar que la detección no es
decorativa.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlas.interfaces.cli import cli
from atlas.logging.merkle_logger import MerkleLogger


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """`ATLAS_HOME` aislado: la suite no puede tocar el estado del operador."""
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("ATLAS_NESTED_TEST_RUN", "1")
    # Rich recorta las celdas al ancho del terminal y con 80 columnas
    # `test_cli_audit` se convierte en `test_cli_aud…`. Afirmar sobre el
    # recorte sería afirmar sobre el formateador, no sobre el comando.
    monkeypatch.setenv("COLUMNS", "220")
    from atlas.interfaces import cli as cli_mod

    cli_mod.reset_orchestrator()
    yield CliRunner()
    cli_mod.reset_orchestrator()


def _ledger(runner_home: Path) -> tuple[MerkleLogger, Path]:
    """El ledger en la MISMA ruta que compone el comando:
    `<workspace>/memory/audit`."""
    directorio = runner_home / "memory" / "audit"
    return MerkleLogger(directorio), directorio


def _escribir(logger: MerkleLogger, cuantos: int) -> None:
    for i in range(cuantos):
        logger.log(
            action=f"prueba.accion_{i}",
            agent="test_cli_audit",
            result="success" if i % 2 == 0 else "failure",
            risk_level="safe" if i % 2 == 0 else "high",
            payload={"i": i},
        )


# ---------------------------------------------------------------------------
# Verificación de la cadena — con un ledger real, y roto a mano
# ---------------------------------------------------------------------------


def test_verify_confirma_una_cadena_intacta(runner: CliRunner, tmp_path: Path) -> None:
    logger, _ = _ledger(tmp_path / "home")
    _escribir(logger, 5)

    resultado = runner.invoke(cli, ["audit", "--verify"])

    assert resultado.exit_code == 0, resultado.output
    assert "integra" in resultado.output


def test_una_cadena_MANIPULADA_impide_arrancar(runner: CliRunner, tmp_path: Path) -> None:
    """La prueba que hace que lo anterior signifique algo: sin ella, un
    `verify_chain()` que devolviera `True` siempre pasaría el test de arriba y
    el comando sería decorativo.

    Y midiendo salió una garantía MÁS FUERTE de la que se buscaba. La
    manipulación no la reporta el comando: la caza el arranque del orquestador,
    que se niega a levantar con

        RuntimeError: Merkle chain corrupta al arrancar:
          Record #2 (id=...): hash_self invalido.

    O sea, no es que `atlas audit --verify` avise si vas a mirar — es que
    NINGÚN comando de Atlas funciona con el registro tocado. Se fija esa, que
    es la que de verdad protege, y no la que yo había supuesto.
    """
    logger, directorio = _ledger(tmp_path / "home")
    _escribir(logger, 5)

    ficheros = sorted(p for p in directorio.rglob("*") if p.is_file())
    assert ficheros, "el ledger no escribió nada; el test no probaría nada"
    objetivo = next(p for p in ficheros if p.stat().st_size > 0)
    lineas = objetivo.read_text(encoding="utf-8").splitlines()
    assert len(lineas) >= 2, "hacen falta al menos dos entradas para romper el enlace"
    # Se altera el PAYLOAD de una entrada intermedia dejando su hash intacto:
    # es la manipulación que la cadena existe para detectar.
    registro = json.loads(lineas[1])
    registro["payload"] = {"i": 999, "manipulado": True}
    lineas[1] = json.dumps(registro)
    objetivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    resultado = runner.invoke(cli, ["audit", "--verify"])

    assert resultado.exception is not None, "arrancó con la cadena manipulada"
    assert "corrupta" in str(resultado.exception).lower()
    assert "hash_self" in str(resultado.exception)


def test_verify_sobre_un_ledger_vacio_no_revienta(runner: CliRunner) -> None:
    resultado = runner.invoke(cli, ["audit", "--verify"])

    assert resultado.exit_code == 0, resultado.output


# ---------------------------------------------------------------------------
# La tabla
# ---------------------------------------------------------------------------


def test_un_log_vacio_lo_dice_en_vez_de_pintar_una_tabla_hueca(
    runner: CliRunner,
) -> None:
    resultado = runner.invoke(cli, ["audit"])

    assert resultado.exit_code == 0, resultado.output
    assert "vacio" in resultado.output.lower()


def test_pinta_las_entradas_con_su_accion_y_agente(
    runner: CliRunner, tmp_path: Path
) -> None:
    logger, _ = _ledger(tmp_path / "home")
    _escribir(logger, 3)

    resultado = runner.invoke(cli, ["audit"])

    assert resultado.exit_code == 0, resultado.output
    assert "test_cli_audit" in resultado.output
    assert "Audit Log" in resultado.output


def test_tail_recorta_a_las_ultimas_n(runner: CliRunner, tmp_path: Path) -> None:
    logger, _ = _ledger(tmp_path / "home")
    _escribir(logger, 8)

    salida = runner.invoke(cli, ["audit", "--tail", "2"]).output

    assert "ultimas 2" in salida
    # La 7 es de las dos últimas; la 0 no puede estar.
    assert "accion_7" in salida
    assert "accion_0" not in salida


def test_los_resultados_y_riesgos_se_colorean_por_su_valor(
    runner: CliRunner, tmp_path: Path
) -> None:
    """`result` y `risk_level` eligen color por diccionario, con `white` de
    reserva. Se ejercitan las dos ramas: valores conocidos y el fallback."""
    logger, _ = _ledger(tmp_path / "home")
    _escribir(logger, 2)  # success/safe y failure/high
    logger.log(
        action="prueba.rara", agent="test_cli_audit",
        result="estado_desconocido", risk_level="riesgo_desconocido", payload={},
    )

    resultado = runner.invoke(cli, ["audit", "--tail", "5"])

    assert resultado.exit_code == 0, resultado.output
    # Las columnas Result y Risk se declaran con `width=10` FIJO en el comando,
    # así que recortan pase lo que pase con el terminal. Es comportamiento del
    # comando, no ruido del test: se afirma sobre el prefijo que de verdad se
    # ve. Lo que ejercita este caso es la rama de reserva `.get(res, "white")`,
    # que se recorre igual esté el texto recortado o no.
    assert "estado_de" in resultado.output
    assert "riesgo_de" in resultado.output
    assert "safe" in resultado.output and "high" in resultado.output
