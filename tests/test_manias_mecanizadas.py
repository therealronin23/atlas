"""Las manías que SÍ pueden ser código dejan de vivir sólo en prosa.

De las 35 declaradas en `AGENTS.md`, 29 no tenían rastro alguno en `src/` ni
`tests/`. La mayoría son de conducta y no pueden ser código
(`honesty-over-sycophancy`, `plan-then-execute`, `decide-with-facts`): fingir lo
contrario sería peor que reconocerlo.

Pero la evidencia de que las mecanizables importan es esta misma semana: se
rompieron DOS reglas que sólo vivían en prosa —`graph-rebuild-single-writer`,
que corrompió el grafo, e `internal-prior-art-first`, que reintrodujo un bug de
tokens ya pagado y documentado— habiendo leído el documento las dos veces.

Una regla que sólo vive en un documento se rompe. Ésta es la parte que puede no
depender de la buena memoria de quien pase por aquí.

NOTA DE MÉTODO, que es el hallazgo más útil de este fichero: `no-gui-in-tests`
parecía violada por tres ficheros y NO lo estaba. Un `grep` de `pyautogui` y
`DISPLAY` los marcaba, pero eran DATOS —el manifiesto de `computer-control-mcp`
declara `DISPLAY=:99` y `pyautogui` como dependencia— y los tests sólo afirman
sobre el recibo de admisión. El instrumento equivocado convierte una regla sana
en una puerta que miente. Con AST, importar != mencionar, y los tres falsos
positivos desaparecen.
"""

from __future__ import annotations

import ast
import os
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# no-gui-in-tests
# ---------------------------------------------------------------------------

_LIBS_GUI = frozenset(
    {"pyautogui", "tkinter", "Xlib", "PyQt5", "PyQt6", "PySide6", "pygame", "cv2"}
)


def _modulos_importados(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_ningun_test_importa_una_libreria_gui() -> None:
    """La suite no puede depender de un escritorio: en CI o en bwrap no lo hay.

    Se comprueba el IMPORT, no la mención. Mencionar `pyautogui` como dato del
    manifiesto de un servidor MCP es legítimo y frecuente aquí.
    """
    culpables = [
        f"{p.relative_to(REPO)}: {sorted(_modulos_importados(p) & _LIBS_GUI)}"
        for p in sorted((REPO / "tests").rglob("*.py"))
        if _modulos_importados(p) & _LIBS_GUI
    ]

    assert not culpables, (
        "tests que importan GUI sin marcar `computer_use`: " + "; ".join(culpables)
    )


def test_el_marcador_computer_use_sigue_existiendo() -> None:
    """El escape para los que SÍ necesitan display. Sin él, la regla de arriba
    no tendría válvula y alguien la borraría en vez de usarla."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")

    assert "computer_use" in pyproject
    assert "not computer_use" in pyproject


# ---------------------------------------------------------------------------
# local-agent-config-is-secret-by-default
# ---------------------------------------------------------------------------

#: Configs de agente LOCALES (no trackeadas). Las trackeadas viven en git y son
#: legibles por diseño: exigirles 600 sería un falso positivo garantizado.
_CONFIGS_LOCALES = (
    ".env",
    ".claude/settings.local.json",
    ".codex/config.toml",
)


def _trackeado(rel: str) -> bool:
    import subprocess

    return (
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=REPO, capture_output=True,
        ).returncode
        == 0
    )


@pytest.mark.parametrize("rel", _CONFIGS_LOCALES)
def test_config_local_de_agente_no_es_legible_por_terceros(rel: str) -> None:
    """Medido el 2026-08-10: `.claude/settings.local.json` estaba en 664
    mientras `.env` y `.codex/config.toml` estaban en 600. No contenía
    secretos —sólo una allow-list— pero la manía dice *by default*, y el
    fichero local sin trackear es justo el que puede crecer un token mañana.
    """
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} no existe en este checkout")
    if _trackeado(rel):
        pytest.skip(f"{rel} está trackeado: es público por diseño")

    modo = stat.S_IMODE(path.stat().st_mode)

    assert not modo & (stat.S_IRGRP | stat.S_IROTH), (
        f"{rel} en {oct(modo)}: config local de agente legible por grupo/otros"
    )


# ---------------------------------------------------------------------------
# filesystem-limits-are-runtime-facts
# ---------------------------------------------------------------------------


def test_los_limites_del_fs_se_consultan_no_se_asumen() -> None:
    """`NAME_MAX` es 255 en ext4 y 143 en eCryptfs. Hardcodearlo rompió antes
    la exportación a Obsidian; se lee con `os.pathconf`, no se supone."""
    sospechosos = []
    for p in sorted((REPO / "src" / "atlas").rglob("*.py")):
        texto = p.read_text(encoding="utf-8", errors="replace")
        for i, linea in enumerate(texto.splitlines(), 1):
            if "255" not in linea:
                continue
            bajo = linea.lower()
            if any(k in bajo for k in ("name_max", "filename", "max_name", "basename")):
                if "pathconf" not in bajo:
                    sospechosos.append(f"{p.relative_to(REPO)}:{i}")

    assert not sospechosos, (
        "límite de nombre de fichero hardcodeado en vez de consultado: "
        + ", ".join(sospechosos)
    )


def test_pathconf_esta_disponible_como_via_correcta() -> None:
    assert hasattr(os, "pathconf")


# ---------------------------------------------------------------------------
# no-cli-against-live-workspace
# ---------------------------------------------------------------------------


def test_la_suite_no_escribe_en_el_workspace_vivo() -> None:
    """Un test que escriba en `~/atlas` corrompe la cadena Merkle del operador
    — dos escritores sobre el mismo ledger, el incidente del 2026-05-29.

    Se buscan ESCRITURAS con un `~/atlas` literal, no lecturas ni asserts sobre
    rutas: `assert adopted_servers_path() == Path.home()/"atlas"/...` es
    legítimo y no toca nada.
    """
    culpables = []
    for p in sorted((REPO / "tests").rglob("*.py")):
        for i, linea in enumerate(
            p.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if 'Path.home()' not in linea and "~/atlas" not in linea:
                continue
            if any(k in linea for k in ("write_text", "mkdir", "unlink", "rmtree", "touch")):
                culpables.append(f"{p.relative_to(REPO)}:{i}")

    assert not culpables, (
        "tests que escriben en el workspace vivo: " + ", ".join(culpables)
    )


# ---------------------------------------------------------------------------
# Honestidad sobre el alcance
# ---------------------------------------------------------------------------


def test_agents_md_declara_cuales_no_son_mecanizables() -> None:
    """Sin esta nota, `AGENTS.md` aparenta 35 reglas igual de vinculantes
    cuando sólo un puñado tiene quien las haga cumplir. Decir cuáles dependen
    de la conducta es parte de no fingir cobertura."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    assert "no todas son mecanizables" in agents.lower()
