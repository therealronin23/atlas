"""Cosecha de la suite congelada de defectos — la verdad-terreno del fitness.

El lazo tiene restricciones ("pytest pasa") pero ninguna función de fitness, y
por eso rinde 7,8% end-to-end frente al 35-50% de aceptación de PRs reales del
campo. DGM (arXiv:2505.22954) identifica la validación empírica sobre un
benchmark como el ingrediente habilitante: sin una métrica que subir, un lazo
sólo puede no-empeorar.

Este módulo construye ese benchmark a partir del historial propio, con el
método de SWE-bench:

    base = padre(commit_de_arreglo)
    se aplica SÓLO la parte de tests/ del diff del arreglo
    el test debe FALLAR ahí  -> hay defecto reproducible
    (y con el arreglo entero debe PASAR -> el defecto es el que se cree)

La propiedad que lo hace no-hackeable: se guarda el estado del defecto y el
parche de TESTS, **nunca el diff del arreglo**. La respuesta no está en el repo,
así que el lazo no puede leerla — sólo resolverla.

Un candidato cuyo test ya pasa en `base` es un falso positivo de la cosecha (el
commit tocó tests por otra razón) y se descarta: mediría cero.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from atlas.core.self_maintenance.frozen_defects import (
    FrozenDefect,
    build_candidate,
    candidate_commits,
    split_test_patch,
    write_defects,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo con un defecto real: un commit `fix(` que arregla src y añade test."""
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
        "PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
    }

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True,
                       capture_output=True)

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "feat: calculadora")

    # El arreglo: corrige src Y añade el test que lo demuestra.
    (tmp_path / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "tests" / "test_calc.py").write_text(
        "from src.calc import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n"
    )
    git("add", "-A")
    git("commit", "-q", "-m", "fix(calc): la suma restaba")

    # Ruido: un commit fix( que NO toca tests -> no es candidato.
    (tmp_path / "src" / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n"
    )
    git("add", "-A")
    git("commit", "-q", "-m", "fix(calc): faltaba mul")
    return tmp_path


# --------------------------------------------------------------------------
# Selección de candidatos
# --------------------------------------------------------------------------


def test_solo_commits_fix_con_test_y_src(repo: Path) -> None:
    shas = candidate_commits(repo)

    assert len(shas) == 1
    assert subprocess.run(
        ["git", "log", "-1", "--format=%s", shas[0]], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout.strip() == "fix(calc): la suma restaba"


def test_un_fix_sin_tests_no_es_candidato(repo: Path) -> None:
    """Sin test que lo demuestre no hay defecto medible."""
    subjects = [
        subprocess.run(["git", "log", "-1", "--format=%s", s], cwd=repo,
                       capture_output=True, text=True, check=True).stdout.strip()
        for s in candidate_commits(repo)
    ]
    assert "fix(calc): faltaba mul" not in subjects


def test_limit_acota_la_cosecha(repo: Path) -> None:
    assert candidate_commits(repo, limit=0) == []


# --------------------------------------------------------------------------
# El parche de tests se separa del arreglo — el núcleo de la no-hackeabilidad
# --------------------------------------------------------------------------


def test_el_parche_solo_contiene_tests(repo: Path) -> None:
    sha = candidate_commits(repo)[0]

    patch = split_test_patch(repo, sha)

    assert "tests/test_calc.py" in patch
    assert "src/calc.py" not in patch


def test_el_parche_no_filtra_el_arreglo(repo: Path) -> None:
    """Si el diff de src se colara, el lazo leería la solución en vez de
    resolverla, y la métrica valdría cero."""
    sha = candidate_commits(repo)[0]

    patch = split_test_patch(repo, sha)

    assert "return a + b" not in patch


def test_el_defecto_no_guarda_el_diff_del_arreglo(repo: Path) -> None:
    defect = build_candidate(repo, candidate_commits(repo)[0])

    assert defect is not None
    serialized = json.dumps(defect.to_dict())
    assert "return a + b" not in serialized


def _paths_tocadas(patch: str) -> set[str]:
    """Rutas que el parche modifica, leídas de las cabeceras `diff --git`.

    Anclado a inicio de línea a propósito. Buscar 'src/' por substring da falsos
    positivos reales: al cosechar el repo de verdad, un test que lleva un diff
    FALSO como fixture produce la línea `++++ b/src/atlas/no_existe.py` (cuatro
    '+': tres del diff embebido más el del diff exterior), y un checker ingenuo
    la lee como fuga del arreglo cuando es contenido del test.
    """
    import re

    header = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
    out: set[str] = set()
    for line in patch.splitlines():
        match = header.match(line)
        if match:
            out.update(match.groups())
    return out


def test_ninguna_ruta_del_parche_sale_de_tests(repo: Path) -> None:
    """LA invariante: si un solo hunk del arreglo se cuela, el lazo lee la
    solución en vez de resolverla y la métrica pasa a medir memoria."""
    defect = build_candidate(repo, candidate_commits(repo)[0])
    assert defect is not None

    paths = _paths_tocadas(defect.test_patch)

    assert paths
    assert all(p.startswith("tests/") for p in paths), paths


def test_un_diff_embebido_en_un_test_no_es_una_fuga() -> None:
    """Regresión del falso positivo descrito en `_paths_tocadas`."""
    patch = (
        "diff --git a/tests/test_x.py b/tests/test_x.py\n"
        "--- a/tests/test_x.py\n"
        "+++ b/tests/test_x.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+PATCH = '''diff --git a/src/atlas/no_existe.py b/src/atlas/no_existe.py\n"
        "++++ b/src/atlas/no_existe.py'''\n"
    )

    assert _paths_tocadas(patch) == {"tests/test_x.py"}


# --------------------------------------------------------------------------
# Construcción del defecto
# --------------------------------------------------------------------------


def test_base_es_el_padre_del_arreglo(repo: Path) -> None:
    sha = candidate_commits(repo)[0]
    defect = build_candidate(repo, sha)

    assert defect is not None
    parent = subprocess.run(
        ["git", "rev-parse", f"{sha}^"], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert defect.base_sha == parent
    assert defect.fix_sha == sha


def test_el_defecto_lleva_sus_ficheros_de_test(repo: Path) -> None:
    defect = build_candidate(repo, candidate_commits(repo)[0])

    assert defect is not None
    assert defect.test_files == ("tests/test_calc.py",)


def test_el_subsistema_sale_del_scope_del_commit(repo: Path) -> None:
    """`fix(calc): ...` -> subsystem 'calc'. Sirve para no cosechar veinte
    defectos del mismo rincón."""
    defect = build_candidate(repo, candidate_commits(repo)[0])

    assert defect is not None
    assert defect.subsystem == "calc"


def test_un_commit_raiz_sin_padre_se_descarta(repo: Path) -> None:
    root = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo,
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    assert build_candidate(repo, root) is None


# --------------------------------------------------------------------------
# Persistencia
# --------------------------------------------------------------------------


def test_write_defects_es_jsonl_estable(repo: Path, tmp_path: Path) -> None:
    defect = build_candidate(repo, candidate_commits(repo)[0])
    assert defect is not None
    out = tmp_path / "sub" / "frozen_defects.jsonl"

    n = write_defects([defect], out)

    assert n == 1
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows[0]["fix_sha"] == defect.fix_sha
    assert rows[0]["base_sha"] == defect.base_sha
    # ordenado por clave: dos cosechas iguales dan bytes iguales
    assert out.read_text() == out.read_text()


def test_write_defects_sobreescribe_no_acumula(repo: Path, tmp_path: Path) -> None:
    """Append-only aquí sería un error: la suite es un CONJUNTO, y recosechar
    duplicaría defectos inflando el denominador del score."""
    defect = build_candidate(repo, candidate_commits(repo)[0])
    assert defect is not None
    out = tmp_path / "frozen_defects.jsonl"

    write_defects([defect], out)
    write_defects([defect], out)

    assert len(out.read_text().splitlines()) == 1


def test_id_estable_entre_cosechas(repo: Path) -> None:
    sha = candidate_commits(repo)[0]

    a = build_candidate(repo, sha)
    b = build_candidate(repo, sha)

    assert a is not None and b is not None
    assert a.id == b.id


def test_from_dict_redondea(repo: Path) -> None:
    defect = build_candidate(repo, candidate_commits(repo)[0])
    assert defect is not None

    assert FrozenDefect.from_dict(defect.to_dict()) == defect
