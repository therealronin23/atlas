"""Contrato A3.1: materializador explícito de fuente LOCAL a staging inmutable.

ADR-073 (consecuencias A3, condiciones 1-2 del design doc plugin_manifest_v1):
materializar a un directorio NUEVO bajo staging, sin hooks ni red, fijar
contenido/procedencia y re-escanear DESPUÉS de materializar. Fuentes remotas
quedan fuera de esta loncha por diseño.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from atlas.mcp.plugin_materializer import (
    MaterializationResult,
    PluginMaterializer,
)
from atlas.security.supply_chain import ScanLimits


def _manifest(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": "1.0",
        "plugin_id": "demo-plugin",
        "display_name": "Demo plugin",
        "version": "1.0.0",
        "source": {
            "origin": "local://test/demo-plugin",
            "revision": "fixture-1",
            "license": "Apache-2.0",
        },
        "activation": "declarative",
        "permissions": [],
        "contributions": [
            {
                "contribution_id": "demo-skill",
                "kind": "skill",
                "path": "skills/demo.md",
            }
        ],
    }
    document.update(overrides)
    return document


def _source(root: Path, manifest: dict[str, object] | None = None) -> Path:
    root.mkdir(parents=True)
    (root / "atlas-plugin.json").write_text(
        json.dumps(manifest or _manifest()), encoding="utf-8"
    )
    (root / "skills").mkdir()
    (root / "skills" / "demo.md").write_text(
        "# Demo skill\n\nUna skill declarativa de demostración para el "
        "contrato A3.1 del materializador de staging.\n",
        encoding="utf-8",
    )
    return root


def _tree_sha256(root: Path) -> str:
    entries = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append(f"{path.relative_to(root).as_posix()}\0{digest}")
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def test_materialize_local_happy_path_admits(tmp_path: Path) -> None:
    source = _source(tmp_path / "src" / "demo-plugin")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(staging_root=staging)

    result = materializer.materialize_local(source, expected_plugin_id="demo-plugin")

    assert isinstance(result, MaterializationResult)
    assert result.status == "materialized"
    assert result.reason_codes == []
    staged = Path(result.staged_root or "")
    assert staged.is_dir()
    assert staged.parent == staging
    # Contenido copiado byte-a-byte y procedencia MEDIDA, no asertada.
    assert result.provenance is not None
    assert result.provenance.source_kind == "local"
    assert result.provenance.tree_sha256 == _tree_sha256(source)
    assert result.provenance.tree_sha256 == _tree_sha256(staged)
    assert result.provenance.revision == f"sha256:{result.provenance.tree_sha256}"
    assert result.provenance.file_count == 2
    # Re-escaneo tras materializar: la admisión está ligada al árbol STAGED.
    assert result.admission is not None
    assert result.admission.status == "admit"
    assert result.admission.scan is not None
    assert result.admission.scan.root == str(staged)


def test_provenance_sidecar_lives_outside_staged_tree(tmp_path: Path) -> None:
    source = _source(tmp_path / "src" / "demo-plugin")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(staging_root=staging)

    result = materializer.materialize_local(source)

    staged = Path(result.staged_root or "")
    sidecar = staged.with_name(staged.name + ".provenance.json")
    assert sidecar.is_file()
    # Los bytes escaneados son EXACTAMENTE los bytes admitidos: nada se añade
    # dentro del árbol después del escaneo.
    assert not any(p.name.endswith(".provenance.json") for p in staged.rglob("*"))
    persisted = json.loads(sidecar.read_text(encoding="utf-8"))
    assert persisted["tree_sha256"] == (result.provenance.tree_sha256 if result.provenance else None)


def test_source_symlink_fails_closed_without_partial_staging(tmp_path: Path) -> None:
    source = _source(tmp_path / "src" / "demo-plugin")
    (source / "skills" / "evil.md").symlink_to(tmp_path / "outside.md")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(staging_root=staging)

    result = materializer.materialize_local(source)

    assert result.status == "failed"
    assert "source_symlink" in result.reason_codes
    assert result.staged_root is None
    assert not staging.exists() or list(staging.iterdir()) == []


def test_destination_collision_fails_and_preserves_existing(tmp_path: Path) -> None:
    source = _source(tmp_path / "src" / "demo-plugin")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(staging_root=staging)

    first = materializer.materialize_local(source)
    assert first.status == "materialized"
    staged = Path(first.staged_root or "")
    before = _tree_sha256(staged)

    second = materializer.materialize_local(source)

    assert second.status == "failed"
    assert "destination_exists" in second.reason_codes
    assert _tree_sha256(staged) == before


def test_source_inside_staging_rejected(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    source = _source(staging / "already-here")
    materializer = PluginMaterializer(staging_root=staging)

    result = materializer.materialize_local(source)

    assert result.status == "failed"
    assert "source_overlaps_staging" in result.reason_codes


def test_limits_are_enforced_fail_closed(tmp_path: Path) -> None:
    source = _source(tmp_path / "src" / "demo-plugin")
    (source / "extra.md").write_text("x", encoding="utf-8")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(
        staging_root=staging, limits=ScanLimits(max_files=2)
    )

    result = materializer.materialize_local(source)

    assert result.status == "failed"
    assert "source_too_many_files" in result.reason_codes
    assert result.staged_root is None


def test_admission_verdict_propagates_honestly(tmp_path: Path) -> None:
    # Árbol sin manifest: la materialización mecánica funciona, pero la
    # admisión A2 dice block — y el resultado lo reporta tal cual.
    source = tmp_path / "src" / "no-manifest"
    source.mkdir(parents=True)
    (source / "readme.md").write_text("hola", encoding="utf-8")
    staging = tmp_path / "staging"
    materializer = PluginMaterializer(staging_root=staging)

    result = materializer.materialize_local(source)

    assert result.status == "materialized"
    assert result.admission is not None
    assert result.admission.status == "block"
    assert "manifest_missing" in result.admission.reason_codes


def test_cli_plugin_materialize_end_to_end(tmp_path: Path) -> None:
    # wire-before-claim: el materializador tiene un caller de producción real.
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    source = _source(tmp_path / "src" / "demo-plugin")
    staging = tmp_path / "staging"
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "plugin", "materialize", str(source),
            "--staging-root", str(staging),
            "--plugin-id", "demo-plugin",
        ],
    )

    assert result.exit_code == 0, result.output
    # A3.2: materialize ahora también emite un recibo vía el broker.
    assert "issued" in result.output
    assert "recibo=" in result.output
    assert list(staging.glob("demo-plugin-*")) != []


def test_cli_plugin_materialize_block_exits_nonzero(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from atlas.interfaces.cli import cli

    source = tmp_path / "src" / "no-manifest"
    source.mkdir(parents=True)
    (source / "readme.md").write_text("hola", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["plugin", "materialize", str(source), "--staging-root", str(tmp_path / "staging")],
    )

    assert result.exit_code != 0
    assert "block" in result.output


def test_compute_tree_sha256_matches_provenance_no_drift(tmp_path: Path) -> None:
    # Guardia anti-deriva: plugin_activator re-verifica con compute_tree_sha256
    # de forma INDEPENDIENTE del algoritmo interno del materializador. Si
    # algún día divergen, este test lo detecta antes que un falso-positivo
    # "staged_tree_mutated_since_receipt" en producción.
    from atlas.mcp.plugin_materializer import compute_tree_sha256

    source = _source(tmp_path / "src" / "demo-plugin")
    result = PluginMaterializer(staging_root=tmp_path / "staging").materialize_local(source)

    assert result.provenance is not None
    assert compute_tree_sha256(Path(result.staged_root)) == result.provenance.tree_sha256


def test_module_has_no_network_or_process_surface() -> None:
    # ADR-073: "sin hooks ni red implícita" — por construcción, no por promesa.
    import atlas.mcp.plugin_materializer as module

    text = Path(module.__file__).read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:import|from)\s+([a-zA-Z0-9_.]+)", text, re.M)
    forbidden = {"subprocess", "socket", "urllib", "http", "requests", "asyncio"}
    assert not (set(imports) & forbidden), f"imports prohibidos: {set(imports) & forbidden}"
