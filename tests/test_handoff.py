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
    (repo / "docs" / "design" / "atlas_ecosystem_map.md").write_text(
        "# Atlas Ecosystem Map\n"
        "\n"
        "## Canonical Map\n"
        "\n"
        "| Item | Taxonomy | State |\n"
        "| --- | --- | --- |\n"
        "| Cosa A | Core | ACTIVO |\n"
        "| Cosa B | Governance | PENDIENTE |\n"
        "| Cosa C | Capability | PENDIENTE |\n"
        "\n"
        "## Otra sección\n"
        "no debe colarse en el conteo.\n",
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
    "05_ECOSISTEMA.md",
    "06_PRIMEROS_10_MINUTOS.md",
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


def test_generate_handoff_writes_all_files(tmp_path: Path) -> None:
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
    assert "FUENTE NO DISPONIBLE" in (out_dir / "05_ECOSISTEMA.md").read_text(encoding="utf-8")
    # 06_PRIMEROS_10_MINUTOS.md es estático (no lee fuentes) — nunca falla cerrado.
    assert "FUENTE NO DISPONIBLE" not in (out_dir / "06_PRIMEROS_10_MINUTOS.md").read_text(encoding="utf-8")


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


def test_cli_handoff_respects_explicit_out_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hallazgo Minor (cobertura de tests) de la revisión final T0: la opción
    --out-dir nunca se había ejercitado vía CliRunner (todos los tests pasaban
    out_dir directo a generate_handoff), así que el plumbing click.Path ->
    resolved_out_dir del comando real quedaba sin probar."""
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    monkeypatch.setenv("ATLAS_MEMORY_DB", str(tmp_path / "no-such-dir" / "memory.db"))
    explicit_out_dir = tmp_path / "custom_out"

    result = CliRunner().invoke(cli, ["handoff", "--out-dir", str(explicit_out_dir)])

    assert result.exit_code == 0, result.output
    assert (explicit_out_dir / "MANIFEST.json").is_file()
    for name in _MD_NAMES:
        assert (explicit_out_dir / name).is_file()
    # el default (docs/handoff/GENERATED) NO debe tocarse cuando se pasa --out-dir explícito
    assert not (repo / "docs" / "handoff" / "GENERATED" / "MANIFEST.json").exists()


# ---------------------------------------------------------------------------
# CLI: build_gated_index() falla -> degradar a index=None, NO reventar
# (hallazgo Important de la revisión final T0)
# ---------------------------------------------------------------------------


def test_cli_handoff_build_gated_index_failure_still_generates_file_based_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si build_gated_index() lanza (embedder no cacheado, BD bloqueada/corrupta),
    'atlas handoff' NO debe reventar: captura la excepción, degrada a index=None
    (03_MEMORIA_CLAVE.md lleva FUENTE NO DISPONIBLE: sustrato) y el resto del
    pack (los 4 ficheros basados en el repo) SE GENERA igual."""
    from click.testing import CliRunner

    import atlas.mcp.memory_server as memory_server
    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    db_path = tmp_path / "existe-pero-falla.db"
    db_path.write_bytes(b"")  # is_file() == True -> el CLI intenta abrir el índice
    monkeypatch.setenv("ATLAS_MEMORY_DB", str(db_path))

    def _boom(_db_path: Path) -> SqliteMemoryIndex:
        raise RuntimeError("embedder no cacheado (simulado)")

    monkeypatch.setattr(memory_server, "build_gated_index", _boom)

    result = CliRunner().invoke(cli, ["handoff"])

    assert result.exit_code == 0, result.output
    out_dir = repo / "docs" / "handoff" / "GENERATED"
    assert (out_dir / "MANIFEST.json").is_file()
    for name in _MD_NAMES:
        assert (out_dir / name).is_file()
    assert "FUENTE NO DISPONIBLE: sustrato" in (out_dir / "03_MEMORIA_CLAVE.md").read_text(encoding="utf-8")
    assert "embedder no cacheado" in result.output


# ---------------------------------------------------------------------------
# CLI --check: MANIFEST.json corrupto -> mensaje limpio + exit 1, jamás traceback
# (hallazgo Minor de la revisión final T0)
# ---------------------------------------------------------------------------


def test_cli_handoff_check_manifest_invalid_json_fails_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    out_dir = repo / "docs" / "handoff" / "GENERATED"
    out_dir.mkdir(parents=True)
    (out_dir / "MANIFEST.json").write_text('{"head_sha": "abc123", truncado', encoding="utf-8")

    result = CliRunner().invoke(cli, ["handoff", "--check"])

    assert result.exit_code == 1
    assert not isinstance(result.exception, json.JSONDecodeError)
    assert "MANIFEST.json" in result.output


def test_cli_handoff_check_manifest_not_a_dict_fails_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    repo = _make_repo(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(repo))
    out_dir = repo / "docs" / "handoff" / "GENERATED"
    out_dir.mkdir(parents=True)
    (out_dir / "MANIFEST.json").write_text("[1, 2, 3]", encoding="utf-8")

    result = CliRunner().invoke(cli, ["handoff", "--check"])

    assert result.exit_code == 1
    assert "MANIFEST.json" in result.output


# ---------------------------------------------------------------------------
# head_sha: saneado de entorno git heredado (hallazgo Minor de la revisión
# final T0) — mismo patrón que _clean_git_env, pero aquí probamos que la
# PROPIA función limpia el env del subproceso, no solo el test.
# ---------------------------------------------------------------------------


def test_head_sha_ignores_inherited_git_env_vars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atlas.core.handoff import head_sha

    repo = _make_repo(tmp_path, name="target_repo")
    expected = _git(repo, "rev-parse", "HEAD")

    # Simula un proceso padre (hook pre-commit, git anidado) que exporta estas
    # env vars apuntando a OTRO repo: head_sha(repo) no debe filtrarse a través
    # de ellas y devolver el HEAD del repo ajeno.
    other_repo = tmp_path / "other_repo"
    other_repo.mkdir()
    _git(other_repo, "init", "-q")
    (other_repo / "f.txt").write_text("x", encoding="utf-8")
    _git(other_repo, "add", "-A")
    _git(other_repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "other")

    monkeypatch.setenv("GIT_DIR", str(other_repo / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other_repo))

    assert head_sha(repo) == expected


# ---------------------------------------------------------------------------
# extract_where_block: <2 entradas "- **" (hallazgo Minor de calidad de tests
# de la revisión final T0) — la rama else (0 o 1 entrada) no tenía ningún
# test dedicado; corta en el siguiente '## ' o al final del texto.
# ---------------------------------------------------------------------------


def test_extract_where_block_zero_entries_cuts_at_next_header() -> None:
    from atlas.core.handoff import extract_where_block

    text = (
        "# Ledger\n"
        "\n"
        "## WHERE\n"
        "\n"
        "sin entradas todavía, solo texto libre.\n"
        "\n"
        "## OTRA SECCION\n"
        "contenido de otra sección que NO debe aparecer.\n"
    )

    block = extract_where_block(text)

    assert block is not None
    assert "sin entradas todavía" in block
    assert "OTRA SECCION" not in block
    assert "NO debe aparecer" not in block


def test_extract_where_block_zero_entries_cuts_at_end_of_text() -> None:
    from atlas.core.handoff import extract_where_block

    text = (
        "# Ledger\n"
        "\n"
        "## WHERE\n"
        "\n"
        "sin entradas, y sin más secciones después.\n"
    )

    block = extract_where_block(text)

    assert block is not None
    assert block.endswith("sin entradas, y sin más secciones después.")


def test_extract_where_block_one_entry_cuts_at_next_header() -> None:
    from atlas.core.handoff import extract_where_block

    text = (
        "## WHERE\n"
        "\n"
        "- **ÚNICA ENTRADA (2026-07-17)** — con una línea de\n"
        "  continuación indentada.\n"
        "\n"
        "## OTRA SECCION\n"
        "no debe aparecer.\n"
    )

    block = extract_where_block(text)

    assert block is not None
    assert "ÚNICA ENTRADA" in block
    assert "continuación indentada" in block
    assert "OTRA SECCION" not in block


def test_extract_where_block_one_entry_cuts_at_end_of_text() -> None:
    from atlas.core.handoff import extract_where_block

    text = "## WHERE\n\n- **ÚNICA ENTRADA (2026-07-17)** — sin sección posterior.\n"

    block = extract_where_block(text)

    assert block is not None
    assert block.rstrip("\n").endswith("sin sección posterior.")


def test_manifest_records_source_hashes_and_hook_uses_them(tmp_path: Path) -> None:
    """El MANIFEST registra el sha256 de cada fuente de repo (contrato de
    frescura por CONTENIDO: el pack se proyecta del árbol de trabajo, así que
    comparar shas de git marcaba desfasado un pack recién generado). El hook
    de sesión debe leer esas "sources" del manifest en vez de hardcodear la
    lista — si vuelve a duplicarla, este test lo caza."""
    from atlas.core.handoff import REPO_SOURCES, source_hashes

    repo = _make_repo(tmp_path)
    generate_handoff(repo, None, tmp_path / "out")
    manifest = json.loads((tmp_path / "out" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert set(manifest["sources"]) == set(REPO_SOURCES)
    assert manifest["sources"] == source_hashes(repo)

    hook = (
        Path(__file__).resolve().parent.parent / "scripts" / "handoff_freshness_hook.sh"
    ).read_text(encoding="utf-8")
    assert 'manifest["sources"]' in hook
    for source in REPO_SOURCES:
        assert f'"{source}"' not in hook, (
            f"el hook hardcodea {source}: debe leer las fuentes del MANIFEST"
        )


# ---------------------------------------------------------------------------
# 05_ECOSISTEMA.md / 06_PRIMEROS_10_MINUTOS.md — spec B+C §5/§4 (auditoría
# MAXIMUS Cycle 9: la spec listaba 6 deliverables para `atlas handoff`
# (a-f); solo (a)-(d) existían. Estos son (e) y (f).
# ---------------------------------------------------------------------------


_ECOSYSTEM_FIXTURE = (
    "# Atlas Ecosystem Map\n"
    "\n"
    "## Canonical Map\n"
    "\n"
    "| Item | Taxonomy | State |\n"
    "| --- | --- | --- |\n"
    "| Cosa A | Core | ACTIVO |\n"
    "| Cosa B | Governance | PENDIENTE |\n"
    "| Cosa C | Capability | PENDIENTE |\n"
    "| Cosa D | Core | SELLADO |\n"
    "\n"
    "## Otra sección\n"
    "| no | debe | colarse |\n"
    "| --- | --- | --- |\n"
    "| X | Y | Z |\n"
)


def test_parse_ecosystem_table_rows_skips_header_separator_and_other_sections() -> None:
    from atlas.core.handoff import _parse_ecosystem_table_rows

    rows = _parse_ecosystem_table_rows(_ECOSYSTEM_FIXTURE)

    assert rows == [
        ("Cosa A", "ACTIVO"),
        ("Cosa B", "PENDIENTE"),
        ("Cosa C", "PENDIENTE"),
        ("Cosa D", "SELLADO"),
    ]


def test_parse_ecosystem_table_rows_no_canonical_map_returns_empty() -> None:
    from atlas.core.handoff import _parse_ecosystem_table_rows

    assert _parse_ecosystem_table_rows("# Sin tabla aquí\n") == []


def test_ecosistema_body_counts_by_state_and_lists_pendiente(tmp_path: Path) -> None:
    from atlas.core.handoff import ecosistema_body

    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "atlas_ecosystem_map.md").write_text(
        _ECOSYSTEM_FIXTURE, encoding="utf-8"
    )

    body = ecosistema_body(tmp_path)

    assert "ACTIVO: 1" in body
    assert "PENDIENTE: 2" in body
    assert "SELLADO: 1" in body
    assert "Cosa B" in body
    assert "Cosa C" in body
    assert "Cosa A" not in body.split("PENDIENTE (más accionables")[1]  # solo PENDIENTE en esa lista


def test_ecosistema_body_missing_file_fails_closed(tmp_path: Path) -> None:
    from atlas.core.handoff import ecosistema_body

    assert "FUENTE NO DISPONIBLE" in ecosistema_body(tmp_path)


def test_ecosistema_body_no_table_fails_closed(tmp_path: Path) -> None:
    from atlas.core.handoff import ecosistema_body

    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "atlas_ecosystem_map.md").write_text(
        "# Sin la sección esperada\n", encoding="utf-8"
    )

    assert "FUENTE NO DISPONIBLE" in ecosistema_body(tmp_path)


def test_ecosistema_body_no_pendiente_items_says_so(tmp_path: Path) -> None:
    from atlas.core.handoff import ecosistema_body

    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "atlas_ecosystem_map.md").write_text(
        "## Canonical Map\n\n| Item | Taxonomy | State |\n| --- | --- | --- |\n"
        "| Cosa A | Core | ACTIVO |\n",
        encoding="utf-8",
    )

    body = ecosistema_body(tmp_path)

    assert "(ninguno)" in body


def test_primeros_10_minutos_body_has_concrete_bootstrap_commands() -> None:
    from atlas.core.handoff import primeros_10_minutos_body

    body = primeros_10_minutos_body()

    assert "atlas reality --json" in body
    assert "AGENTS.md" in body
    assert "golden-route request" in body
    assert "atlas update validate" in body
    assert "F2.6" in body


def test_generate_handoff_ecosistema_reflects_real_fixture_table(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    idx = _make_index(tmp_path)
    out_dir = tmp_path / "out"

    generate_handoff(repo, idx, out_dir)

    text = (out_dir / "05_ECOSISTEMA.md").read_text(encoding="utf-8")
    assert "PENDIENTE: 2" in text
    assert "Cosa B" in text
    assert "Cosa C" in text


def test_source_hashes_marks_absent_source_as_missing(tmp_path: Path) -> None:
    """Una fuente ausente se registra MISSING (no se omite): así el aviso de
    frescura ve el cambio cuando reaparece, y el pack ya la declara como
    FUENTE NO DISPONIBLE."""
    from atlas.core.handoff import source_hashes

    hashes = source_hashes(tmp_path)
    assert set(hashes.values()) == {"MISSING"}
