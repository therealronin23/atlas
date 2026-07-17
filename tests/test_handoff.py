"""
Tests de `atlas handoff` (T0 sucesión, Task 2): el pack de sucesión se
GENERA desde el sustrato (WORK_LEDGER.md, AGENTS.md, docs/design/actor_roles.md,
docs/design/atlas_master_plan.md, memorias `harness:*` del índice) en vez de
mantenerse a mano.

También cubre `SqliteMemoryIndex.ids_by_prefix` (decisión N1 del controlador):
`record_type` no se persiste en el schema SQL, así que `atlas handoff`
enumera las memorias migradas del harness por prefijo de id.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from atlas.core.handoff import generate_handoff
from atlas.mcp.memory_trunk import MemoryTrunk
from atlas.memory.embeddings import StubEmbedder
from atlas.memory.memory_index import SqliteMemoryIndex


# ---------------------------------------------------------------------------
# Fixtures compartidas
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # El hook pre-commit del repo real exporta GIT_INDEX_FILE/GIT_DIR; los
    # subprocesos git del test (init/commit sobre el repo fixture) los
    # heredarían y operarían contra el repo padre si no se limpian aquí
    # (mismo patrón que tests/test_cold_update_decider.py).
    for key in list(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def _make_repo(tmp_path: Path, name: str = "repo") -> Path:
    """Repo fixture mínimo con las 4 fuentes que consume `atlas handoff` y
    un WORK_LEDGER con 2 entradas WHERE (para verificar que el corte del
    bloque se queda en la primera)."""
    repo = tmp_path / name
    (repo / "docs" / "design").mkdir(parents=True)
    (repo / "WORK_LEDGER.md").write_text(
        "# WORK LEDGER — estado vivo\n"
        "\n"
        "## WHERE\n"
        "\n"
        "- **ENTRADA UNO (2026-07-17)** — primera entrada, con una línea de\n"
        "  continuación indentada que NO debe cortar el bloque.\n"
        "- **ENTRADA DOS (2026-07-16)** — segunda entrada, NO debe aparecer\n"
        "  en 00_ESTADO.md.\n",
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "# ATLAS CORE — Operating Context\n\ncontenido invariantes de prueba.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "design" / "actor_roles.md").write_text(
        "# Actor Roles\n\ncontenido quien-es-quien de prueba.\n",
        encoding="utf-8",
    )
    (repo / "docs" / "design" / "atlas_master_plan.md").write_text(
        "# Plan Maestro\n\ncontenido del plan de prueba.\n",
        encoding="utf-8",
    )
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return repo


def _make_index(tmp_path: Path, db_name: str = "g.db") -> SqliteMemoryIndex:
    idx = SqliteMemoryIndex(tmp_path / db_name, embedder=StubEmbedder(dim=64))
    MemoryTrunk(idx).add(
        "[migrado de memoria-harness 2026-07-16] Primera memoria de prueba.\n\ncuerpo",
        record_id="harness:mania-de-prueba",
        record_type="harness-memory",
    )
    return idx


_MD_NAMES = (
    "00_ESTADO.md",
    "01_QUIEN_ES_QUIEN.md",
    "02_INVARIANTES.md",
    "03_MEMORIA_CLAVE.md",
    "04_PLAN.md",
)


# ---------------------------------------------------------------------------
# SqliteMemoryIndex.ids_by_prefix — decisión N1
# ---------------------------------------------------------------------------


def test_ids_by_prefix_returns_matching_ids_sorted_alphabetically(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64))
    trunk = MemoryTrunk(idx)
    trunk.add("texto b", record_id="harness:b-mania")
    trunk.add("texto a", record_id="harness:a-mania")
    trunk.add("otro prefijo", record_id="doctrine:algo")
    assert idx.ids_by_prefix("harness:") == ["harness:a-mania", "harness:b-mania"]


def test_ids_by_prefix_no_match_returns_empty_list(tmp_path: Path) -> None:
    idx = SqliteMemoryIndex(tmp_path / "g.db", embedder=StubEmbedder(dim=64))
    assert idx.ids_by_prefix("harness:") == []


# ---------------------------------------------------------------------------
# generate_handoff — Step 1 (rojo) / Step 3 (verde)
# ---------------------------------------------------------------------------


def test_generate_handoff_writes_six_files(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    files = generate_handoff(repo, idx, out_dir)

    produced = sorted(p.name for p in out_dir.iterdir())
    assert produced == sorted((*_MD_NAMES, "MANIFEST.json"))
    assert set(files) == set(_MD_NAMES)


def test_generate_handoff_headers_present_in_all_markdown_files(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    for name in _MD_NAMES:
        text = (out_dir / name).read_text(encoding="utf-8")
        assert text.startswith("<!-- GENERADO por atlas handoff ")
        assert "NO EDITAR A MANO; regenerar con: atlas handoff -->" in text


def test_generate_handoff_estado_has_first_entry_not_second(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    text = (out_dir / "00_ESTADO.md").read_text(encoding="utf-8")
    assert "ENTRADA UNO" in text
    assert "ENTRADA DOS" not in text


def test_generate_handoff_memoria_clave_lists_harness_record(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    text = (out_dir / "03_MEMORIA_CLAVE.md").read_text(encoding="utf-8")
    assert "mania-de-prueba" in text
    assert "Primera memoria de prueba." in text


def test_generate_handoff_quien_invariantes_plan_are_verbatim(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    assert "quien-es-quien de prueba" in (out_dir / "01_QUIEN_ES_QUIEN.md").read_text(encoding="utf-8")
    assert "invariantes de prueba" in (out_dir / "02_INVARIANTES.md").read_text(encoding="utf-8")
    assert "del plan de prueba" in (out_dir / "04_PLAN.md").read_text(encoding="utf-8")


def test_generate_handoff_manifest_has_real_head_sha(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    manifest = json.loads((out_dir / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["head_sha"] == _git(repo, "rev-parse", "HEAD")
    assert "generated_at" in manifest
    assert set(manifest["files"]) == set(_MD_NAMES)


def test_generate_handoff_is_deterministic_same_shas_on_second_call(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    first = generate_handoff(repo, idx, out_dir)
    second = generate_handoff(repo, idx, out_dir)

    assert first == second


# ---------------------------------------------------------------------------
# Fail-CERRADO: fuente ausente -> marcador literal, nunca omisión silenciosa
# ---------------------------------------------------------------------------


def test_generate_handoff_missing_sources_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(
        repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "--allow-empty", "-qm", "init",
    )
    out_dir = tmp_path / "out_empty"

    generate_handoff(repo, None, out_dir)

    assert "FUENTE NO DISPONIBLE" in (out_dir / "00_ESTADO.md").read_text(encoding="utf-8")
    assert "FUENTE NO DISPONIBLE" in (out_dir / "01_QUIEN_ES_QUIEN.md").read_text(encoding="utf-8")
    assert "FUENTE NO DISPONIBLE" in (out_dir / "02_INVARIANTES.md").read_text(encoding="utf-8")
    assert "FUENTE NO DISPONIBLE: sustrato" in (out_dir / "03_MEMORIA_CLAVE.md").read_text(encoding="utf-8")
    assert "FUENTE NO DISPONIBLE" in (out_dir / "04_PLAN.md").read_text(encoding="utf-8")


def test_generate_handoff_ledger_without_where_section_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "no_where_repo"
    repo.mkdir()
    (repo / "WORK_LEDGER.md").write_text("# sin sección WHERE\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(
        repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "--allow-empty", "-qm", "init",
    )
    out_dir = tmp_path / "out_no_where"

    generate_handoff(repo, None, out_dir)

    assert "FUENTE NO DISPONIBLE" in (out_dir / "00_ESTADO.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI: `atlas handoff` / `atlas handoff --check` — Step 4
# ---------------------------------------------------------------------------


def test_cli_handoff_generates_pack_in_default_out_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    # BD inexistente -> el comando debe seguir con index=None (fail-cerrado en
    # 03_MEMORIA_CLAVE.md), nunca tocar la BD de producción real del operador.
    monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "no-such-dir" / "memory.db"))

    result = CliRunner().invoke(cli, ["handoff"])

    assert result.exit_code == 0, result.output
    out_dir = repo / "docs" / "handoff" / "GENERATED"
    assert (out_dir / "MANIFEST.json").is_file()
    assert "FUENTE NO DISPONIBLE: sustrato" in (out_dir / "03_MEMORIA_CLAVE.md").read_text(encoding="utf-8")


def test_cli_handoff_check_reports_never_generated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))

    result = CliRunner().invoke(cli, ["handoff", "--check"])

    assert result.exit_code == 0, result.output
    assert "nunca generado" in result.output


def test_cli_handoff_check_ok_right_after_generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "no-such-dir" / "memory.db"))
    runner = CliRunner()

    gen = runner.invoke(cli, ["handoff"])
    assert gen.exit_code == 0, gen.output

    check = runner.invoke(cli, ["handoff", "--check"])
    assert check.exit_code == 0, check.output


def test_cli_handoff_check_exits_1_stale_after_new_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "no-such-dir" / "memory.db"))
    runner = CliRunner()

    gen = runner.invoke(cli, ["handoff"])
    assert gen.exit_code == 0, gen.output

    _git(
        repo, "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "--allow-empty", "-qm", "segundo commit",
    )

    check = runner.invoke(cli, ["handoff", "--check"])
    assert check.exit_code == 1
    assert "STALE" in check.output
