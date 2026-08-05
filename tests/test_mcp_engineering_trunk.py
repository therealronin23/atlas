"""Contract tests para `EngineeringTrunk`, la raíz `engineering` del trunk MCP.

Este módulo llegó al árbol SIN test y sin commitear, y su
`generate_hypotheses()` no podía ejecutarse ni una vez: llamaba a
`history_hypothesis(module, repo_root=...)` (la firma real es
`(repo_root, path)`) y a `memory_hypothesis(module, lesson_store=...)` (la
real es `(store, tag)`). Dos `TypeError` garantizados detrás de un tool MCP
que ningún test tocaba — el caller hueco que ADC-WO-108 nombra como su
propia trampa.

El contrato que fijan estos tests es el que ya usa el resto del plano de
ingeniería: la unidad de trabajo es una RUTA repo-relativa
(`FindingLocation.path`, lo mismo que consume `engineering_impacted_tests`),
no un nombre de módulo, y la composición se delega a `compose_hypotheses`
en vez de recablearla a mano.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.engineering.hypotheses import module_name_for_path
from atlas.mcp.engineering_trunk import EngineeringTrunk


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Un repo git mínimo con un fichero bajo `src/atlas/` que tiene historia."""
    source = tmp_path / "src" / "atlas" / "core"
    source.mkdir(parents=True)
    target = source / "widget.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, env=env, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, env=env, check=True
    )
    return tmp_path


def test_generate_hypotheses_devuelve_las_tres_fuentes(repo: Path) -> None:
    """El caso que hoy es `TypeError`: las tres hipótesis se componen y
    responden, cada una con su propio `available`."""
    trunk = EngineeringTrunk(repo, graph_db_path=repo / "sin_grafo.kuzu")

    result = trunk.generate_hypotheses("src/atlas/core/widget.py")

    assert set(result) == {"graph", "history", "memory"}
    # historia: git respondió de verdad, con el commit sembrado
    assert result["history"]["available"] is True
    assert result["history"]["commit_count"] == 1
    assert result["history"]["last_commit_at"]
    # memoria: LessonStore vacío es una respuesta válida, no un fallo
    assert result["memory"]["available"] is True
    assert result["memory"]["lesson_count"] == 0
    # grafo: sin Kuzu ingerido responde `available=False` CON motivo, no revienta
    assert result["graph"]["available"] is False
    assert result["graph"]["reason"]


def test_ruta_fuera_de_src_atlas_no_revienta(repo: Path) -> None:
    """`module_name_for_path` devuelve None fuera de `src/atlas/`; eso degrada
    la hipótesis de grafo, no aborta las otras dos."""
    (repo / "docs").mkdir()
    (repo / "docs" / "nota.md").write_text("x\n", encoding="utf-8")
    assert module_name_for_path("docs/nota.md") is None

    trunk = EngineeringTrunk(repo, graph_db_path=repo / "sin_grafo.kuzu")
    result = trunk.generate_hypotheses("docs/nota.md")

    assert result["graph"]["available"] is False
    assert result["history"]["available"] is True
    assert result["memory"]["available"] is True


def test_graph_db_no_se_hereda_de_la_maquina(repo: Path, tmp_path: Path) -> None:
    """El trunk se declara portable: el grafo que consulta debe ser el que se
    le inyecta, no el `$HOME/atlas` de la máquina donde corre."""
    from atlas.memory.project_graph import DEFAULT_GRAPH_DB

    injected = tmp_path / "otro_grafo.kuzu"
    trunk = EngineeringTrunk(repo, graph_db_path=injected)

    assert trunk._graph_db_path == injected
    assert trunk._graph_db_path != DEFAULT_GRAPH_DB


def test_impacted_tests_acepta_las_mismas_rutas(repo: Path) -> None:
    """Los dos tools del trunk hablan el mismo idioma: rutas repo-relativas."""
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_widget.py").write_text(
        "from atlas.core.widget import VALUE\n\n\ndef test_v():\n    assert VALUE == 1\n",
        encoding="utf-8",
    )

    impacted = EngineeringTrunk(repo).get_impacted_tests(["src/atlas/core/widget.py"])

    assert isinstance(impacted, list)


def test_read_findings_con_journal_vacio(repo: Path) -> None:
    """Un journal recién creado devuelve lista vacía, no excepción."""
    assert EngineeringTrunk(repo).read_findings() == []
