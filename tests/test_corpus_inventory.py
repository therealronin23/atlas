"""T0.5b — primer paso honesto: inventario determinista del corpus antes de
cualquier clasificación semántica (SPEC-ONLY hasta ahora, ver WORK_LEDGER
Cycle 4 2026-07-22). NO pretende resolver "alimenta-ítem/candidata/histórico/
GAP" completo (eso exige juicio semántico contra el master plan, fuera de
alcance de un ciclo atómico) — solo establece la línea base medible: cuántos
docs hay, dónde, y un bucket heurístico por convención de ruta. Todo lo que
la heurística no reconoce se etiqueta honestamente "sin_clasificar", nunca
se inventa un bucket."""

from __future__ import annotations

from pathlib import Path

from atlas.knowledge.corpus_inventory import inventory_corpus


def _mini_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "archive").mkdir(parents=True)
    (root / "docs" / "inbox").mkdir(parents=True)
    (root / "docs" / "decisions" / "adr").mkdir(parents=True)
    (root / "docs" / "design").mkdir(parents=True)
    (root / "docs" / "risks").mkdir(parents=True)

    (root / "AGENTS.md").write_text("uno dos tres\n", encoding="utf-8")
    (root / "docs" / "archive" / "old.md").write_text("cuatro cinco\n", encoding="utf-8")
    (root / "docs" / "inbox" / "new_export.md").write_text("seis\n", encoding="utf-8")
    (root / "docs" / "decisions" / "adr" / "adr-001.md").write_text(
        "siete ocho nueve diez\n", encoding="utf-8"
    )
    (root / "docs" / "design" / "atlas_master_plan.md").write_text(
        "el plan maestro\n", encoding="utf-8"
    )
    (root / "docs" / "risks" / "unclassified.md").write_text(
        "sin bucket heurístico conocido\n", encoding="utf-8"
    )
    return root


def test_inventory_counts_all_markdown_root_and_nested(tmp_path: Path) -> None:
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    assert report["total_docs"] == 6


def test_inventory_buckets_by_path_convention(tmp_path: Path) -> None:
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    by_path = {d["path"]: d["bucket"] for d in report["docs"]}
    assert by_path["docs/archive/old.md"] == "historico"
    assert by_path["docs/inbox/new_export.md"] == "candidata"
    assert by_path["docs/decisions/adr/adr-001.md"] == "alimenta_item"
    assert by_path["docs/design/atlas_master_plan.md"] == "alimenta_item"


def test_inventory_never_invents_a_bucket_it_cannot_justify(tmp_path: Path) -> None:
    """Honestidad de capacidades: sin regla de ruta que lo cubra, el bucket
    es 'sin_clasificar', nunca un bucket inventado con falsa confianza."""
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    by_path = {d["path"]: d["bucket"] for d in report["docs"]}
    assert by_path["docs/risks/unclassified.md"] == "sin_clasificar"
    assert by_path["AGENTS.md"] == "sin_clasificar"


def test_inventory_bucket_counts_sum_to_total(tmp_path: Path) -> None:
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    assert sum(report["buckets"].values()) == report["total_docs"]


def test_inventory_records_word_count_per_doc(tmp_path: Path) -> None:
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    by_path = {d["path"]: d["word_count"] for d in report["docs"]}
    assert by_path["docs/decisions/adr/adr-001.md"] == 4


def test_inventory_missing_docs_dir_counts_only_root_md(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    (root / "README.md").write_text("hola\n", encoding="utf-8")
    report = inventory_corpus(root)
    assert report["total_docs"] == 1
    assert report["docs"][0]["path"] == "README.md"


def test_inventory_is_sorted_deterministically(tmp_path: Path) -> None:
    root = _mini_corpus(tmp_path)
    report = inventory_corpus(root)
    paths = [d["path"] for d in report["docs"]]
    assert paths == sorted(paths)


def test_cli_corpus_inventory_json(tmp_path: Path, monkeypatch) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    root = _mini_corpus(tmp_path)
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(root))
    runner = CliRunner()
    result = runner.invoke(cli, ["corpus-inventory", "--json"])
    assert result.exit_code == 0, result.output
    import json as _json

    report = _json.loads(result.output)
    assert report["total_docs"] == 6


def test_cli_corpus_inventory_writes_file(tmp_path: Path, monkeypatch) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    root = _mini_corpus(tmp_path)
    out = tmp_path / "out" / "inventory.json"
    monkeypatch.setenv("ATLAS_CORE_ROOT", str(root))
    runner = CliRunner()
    result = runner.invoke(cli, ["corpus-inventory", "--write", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "sin_clasificar" in result.output
