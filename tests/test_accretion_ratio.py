"""El ratio de acreción deja de ser invisible.

Causa nº2 del postmortem de la auditoría 2026-08-06, y la única que nadie había
tocado. Medida sobre este repo:

    60 días  -> 14,7:1  (+149.753 / -10.192)
    30 días  -> 24,3:1  (+79.162 /  -3.259)

Acelerando, sobre una base de 81k loc en `src/`. Nada se retira nunca, así que
cada cambio cuesta más que el anterior y llega el punto en que ni una persona
ni un modelo caben en el proyecto.

Esta pieza sólo MIDE y AVISA. No bloquea nada, a propósito: el pre-commit ya
tuvo esta semana un fail-closed sobre un falso positivo (cancelaba cualquier
commit de sólo renombrados) y la lección es que una puerta nueva se gana el
derecho a bloquear con datos, no de nacimiento.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atlas.core.accretion import AccretionRatio, accretion_ratio


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
        "PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
    }

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, env=env, check=True,
                       capture_output=True)

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("\n".join(f"linea {i}" for i in range(10)) + "\n")
    git("init", "-q")
    git("add", "-A")
    # La semilla se fecha FUERA de la ventana: si cayera dentro, sus 10 líneas
    # se sumarían a cada medición y los tests medirían el fixture, no el cambio.
    env["GIT_COMMITTER_DATE"] = "2020-01-01T00:00:00+00:00"
    env["GIT_AUTHOR_DATE"] = "2020-01-01T00:00:00+00:00"
    git("commit", "-q", "-m", "seed")
    return tmp_path


def _commit(repo: Path, path: str, content: str, msg: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e.com",
        "PATH": "/usr/bin:/bin", "HOME": str(repo),
    }
    (repo / path).write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=repo, env=env, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, env=env, check=True,
                   capture_output=True)


# --------------------------------------------------------------------------
# La medida
# --------------------------------------------------------------------------


def test_solo_anadir_da_ratio_infinito_acotado(repo: Path) -> None:
    """Sin borrar nada no hay divisor. Se reporta como ratio None, no como
    división por cero ni como 0 (que parecería sano)."""
    _commit(repo, "src/b.py", "x\n" * 20, "feat: mas")

    r = accretion_ratio(repo, days=30)

    assert r.deleted == 0
    assert r.added > 0
    assert r.ratio is None
    assert r.status == "unbounded"


def test_borrar_mas_de_lo_que_se_anade_es_sano(repo: Path) -> None:
    _commit(repo, "src/a.py", "linea 0\n", "refactor: consolidar")

    r = accretion_ratio(repo, days=30)

    assert r.deleted > r.added
    assert r.ratio is not None and r.ratio < 1.0
    assert r.status == "ok"


def test_cuenta_lineas_reales(repo: Path) -> None:
    _commit(repo, "src/b.py", "y\n" * 7, "feat: siete")

    r = accretion_ratio(repo, days=30)

    assert r.added == 7


def test_umbral_marca_warn(repo: Path) -> None:
    # 10 líneas fuera, 40 dentro -> ratio 4
    _commit(repo, "src/a.py", "z\n" * 40, "feat: crecer")

    assert accretion_ratio(repo, days=30, threshold=2.0).status == "warn"
    assert accretion_ratio(repo, days=30, threshold=99.0).status == "ok"


def test_solo_mira_las_rutas_pedidas(repo: Path) -> None:
    """`docs/` crece por razones distintas que `src/`; mezclarlos haría el
    número inútil."""
    _commit(repo, "docs.md", "d\n" * 500, "docs: mucho texto")

    r = accretion_ratio(repo, days=30, paths=("src",))

    assert r.added == 0


# --------------------------------------------------------------------------
# Fail-honesto: la consumen `atlas reality` y el pre-commit
# --------------------------------------------------------------------------


def test_sin_git_no_lanza(tmp_path: Path) -> None:
    r = accretion_ratio(tmp_path, days=30)

    assert r.status == "unknown"
    assert r.reason
    assert r.ratio is None


def test_ventana_sin_commits_es_unknown(repo: Path) -> None:
    """Cero cambios en la ventana no es 'sano': es que no hay dato. Sin commits
    nuevos, sólo queda la semilla de 2020, fuera de cualquier ventana."""
    r = accretion_ratio(repo, days=30)

    assert r.added == 0 and r.deleted == 0
    assert r.status == "unknown"
    assert "sin cambios" in r.reason


def test_es_serializable(repo: Path) -> None:
    import json

    d = json.loads(json.dumps(accretion_ratio(repo, days=30).to_dict()))

    assert {"added", "deleted", "ratio", "status", "reason", "days"} <= set(d)


def test_dataclass_por_defecto() -> None:
    assert AccretionRatio().status == "unknown"


# --------------------------------------------------------------------------
# Cableado real
# --------------------------------------------------------------------------


def test_reality_trae_la_seccion() -> None:
    """Una métrica que existe y nadie consulta no mide nada — el fallo que esta
    auditoría lleva encontrando por todas partes."""
    from atlas.core.reality import collect_reality

    snapshot = collect_reality(repo_root=Path.cwd())

    assert "accretion" in snapshot
    section = snapshot["accretion"]
    assert "status" in section
    assert "ratio" in section


def test_la_seccion_declara_su_clase_de_evidencia() -> None:
    from atlas.core.reality import _EVIDENCE_CLASS

    assert "accretion" in _EVIDENCE_CLASS
