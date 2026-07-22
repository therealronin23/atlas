"""T0.5b, paso 2 — clasificación semántica del corpus contra el plan maestro.

Paso 1 (PRIME Cycle 4, `corpus_inventory.py`) estableció la línea base por
convención de ruta: 602/701 docs (86%) quedaron honestamente `sin_clasificar`
porque una regla de ruta no es juicio de contenido. Este módulo cierra esa
brecha por similitud coseno de embeddings contra las secciones T0-T6 de
`docs/design/atlas_master_plan.md §5`, con el umbral 0.5 YA MEDIDO en una
sesión previa (2026-07-17: positivos>=0.533, ruido<=0.449) — no se re-deriva
aquí, se reusa.

Los tests usan un embedder FALSO (determinista, sin cargar el modelo ONNX de
fastembed) — mismo principio que el resto de la suite: rápido y hermético.
La corrida con el embedder REAL es un prove-it en vivo, fuera de pytest.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.knowledge.corpus_inventory import inventory_corpus
from atlas.knowledge.corpus_semantic_classifier import (
    SEMANTIC_MATCH_THRESHOLD,
    classify_corpus_semantically,
    extract_plan_sections,
)


class _FakeEmbedder:
    """Vectores one-hot por marcador: cada `marker` ocupa una dimensión
    propia, así que textos con marcadores DISTINTOS dan coseno 0.0 entre sí
    y textos con el MISMO marcador dan coseno 1.0. Necesario porque el
    coseno es invariante a escala — un embedder falso de 1 dimensión no
    puede distinguir direcciones, solo magnitud (que el coseno ignora)."""

    def __init__(self, markers: dict[str, float] | list[str] | None = None) -> None:
        keys = list(markers) if markers else []
        self._dims = {marker: i for i, marker in enumerate(keys)}

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * len(self._dims)
        for marker, i in self._dims.items():
            if marker in text:
                vec[i] = 1.0
        return vec

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class TestExtractPlanSections:
    def test_extracts_synthetic_tramos(self) -> None:
        text = (
            "# Plan\n\n"
            "## 5. El plan por tramos (orden con porqué)\n\n"
            "### T0 — Sucesión\n\nContenido de T0.\n\n"
            "### T1 — Autoconstrucción\n\nContenido de T1.\n\n"
            "## 6. Otra sección\n\nNo debe colarse en T1.\n"
        )

        sections = extract_plan_sections(text)

        assert set(sections) == {"T0", "T1"}
        assert "Contenido de T0." in sections["T0"]
        assert "Contenido de T1." in sections["T1"]
        assert "No debe colarse" not in sections["T1"]
        assert "No debe colarse" not in sections["T0"]

    def test_extracts_real_master_plan_t0_through_t6(self) -> None:
        plan_path = (
            Path(__file__).resolve().parent.parent
            / "docs" / "design" / "atlas_master_plan.md"
        )
        text = plan_path.read_text(encoding="utf-8")

        sections = extract_plan_sections(text)

        assert set(sections) == {"T0", "T1", "T2", "T3", "T4", "T5", "T6"}
        for tramo, body in sections.items():
            assert body.strip(), f"sección {tramo} vacía"

    def test_no_tramos_section_returns_empty(self) -> None:
        assert extract_plan_sections("# Sin tramos aquí\n") == {}


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _plan(root: Path) -> None:
    _write(
        root,
        "docs/design/atlas_master_plan.md",
        "## 5. El plan por tramos\n\n"
        "### T0 — Sucesión\n\nMARKER_T0 texto del tramo cero.\n\n"
        "### T1 — Autoconstrucción\n\nMARKER_T1 texto del tramo uno.\n",
    )


class TestClassifyCorpusSemantically:
    def test_doc_above_threshold_gets_reclassified(self, tmp_path: Path) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/random/nota.md", "MARKER_T0 esta nota habla de sucesión")
        inventory = inventory_corpus(tmp_path)
        # el plan mismo cae en 'alimenta_item' por regla de ruta exacta
        # (corpus_inventory._PATH_RULES) — solo la nota queda sin_clasificar.
        assert inventory["buckets"]["sin_clasificar"] == 1

        result = classify_corpus_semantically(
            inventory,
            repo_root=tmp_path,
            embedder=_FakeEmbedder({"MARKER_T0": 1.0}),
        )

        nota = next(d for d in result["docs"] if d["path"] == "docs/random/nota.md")
        assert nota["bucket"] == "alimenta_item_semantico"
        assert nota["semantic_match"] == "T0"
        assert nota["semantic_score"] == 1.0

    def test_doc_below_threshold_stays_unclassified_with_score_recorded(
        self, tmp_path: Path
    ) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/random/nota.md", "texto sin ningún marcador conocido")
        inventory = inventory_corpus(tmp_path)

        result = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=_FakeEmbedder({"MARKER_T0": 1.0})
        )

        nota = next(d for d in result["docs"] if d["path"] == "docs/random/nota.md")
        assert nota["bucket"] == "sin_clasificar"  # honesto: nunca inventa confianza
        assert nota["semantic_score"] == 0.0
        assert nota["semantic_match"] is None

    def test_bucket_counts_stay_consistent(self, tmp_path: Path) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/a.md", "MARKER_T0 habla de sucesión")
        _write(tmp_path, "docs/b.md", "MARKER_T1 habla de autoconstrucción")
        _write(tmp_path, "docs/c.md", "sin marcador")
        inventory = inventory_corpus(tmp_path)
        total_before = inventory["total_docs"]

        result = classify_corpus_semantically(
            inventory,
            repo_root=tmp_path,
            embedder=_FakeEmbedder({"MARKER_T0": 1.0, "MARKER_T1": 1.0}),
        )

        assert result["buckets"]["alimenta_item_semantico"] == 2
        assert result["buckets"]["sin_clasificar"] == 1  # solo c.md, sin marcador
        assert sum(result["buckets"].values()) == total_before

    def test_already_classified_docs_are_left_untouched(self, tmp_path: Path) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/archive/viejo.md", "MARKER_T0 esto está archivado")
        inventory = inventory_corpus(tmp_path)
        archived = next(d for d in inventory["docs"] if d["path"] == "docs/archive/viejo.md")
        assert archived["bucket"] == "historico"  # regla de ruta paso 1

        result = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=_FakeEmbedder({"MARKER_T0": 1.0})
        )

        reclassified = next(d for d in result["docs"] if d["path"] == "docs/archive/viejo.md")
        assert reclassified["bucket"] == "historico"  # sin tocar
        assert "semantic_score" not in reclassified  # nunca se procesó

    def test_empty_doc_is_skipped_without_crashing(self, tmp_path: Path) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/vacio.md", "   \n\n  ")
        inventory = inventory_corpus(tmp_path)

        result = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=_FakeEmbedder({"MARKER_T0": 1.0})
        )

        vacio = next(d for d in result["docs"] if d["path"] == "docs/vacio.md")
        assert vacio["bucket"] == "sin_clasificar"

    def test_stale_inventory_entry_for_deleted_file_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/borrado.md", "MARKER_T0 contenido")
        inventory = inventory_corpus(tmp_path)
        (tmp_path / "docs" / "borrado.md").unlink()

        result = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=_FakeEmbedder({"MARKER_T0": 1.0})
        )

        borrado = next(d for d in result["docs"] if d["path"] == "docs/borrado.md")
        assert borrado["bucket"] == "sin_clasificar"

    def test_threshold_is_overridable(self, tmp_path: Path) -> None:
        _plan(tmp_path)
        _write(tmp_path, "docs/nota.md", "MARKER_T0 texto")
        inventory = inventory_corpus(tmp_path)
        embedder = _FakeEmbedder({"MARKER_T0": 1.0})  # coseno exacto = 1.0

        strict = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=embedder, threshold=1.5,
        )
        lax = classify_corpus_semantically(
            inventory, repo_root=tmp_path, embedder=embedder, threshold=0.5,
        )

        nota_strict = next(d for d in strict["docs"] if d["path"] == "docs/nota.md")
        nota_lax = next(d for d in lax["docs"] if d["path"] == "docs/nota.md")
        assert nota_strict["bucket"] == "sin_clasificar"  # 1.0 < 1.5
        assert nota_lax["bucket"] == "alimenta_item_semantico"  # 1.0 >= 0.5

    def test_default_threshold_matches_measured_value(self) -> None:
        assert SEMANTIC_MATCH_THRESHOLD == 0.5

    def test_best_matching_section_wins_over_a_weaker_partial_match(
        self, tmp_path: Path
    ) -> None:
        # Doc que menciona AMBOS marcadores pero pesa más hacia T1 (2 hits
        # de T1 por 1 de T0, codificado como dos dimensiones T1 vs una T0):
        # T0=[1,0,0], T1=[0,1,1] por diseño del embedder; doc comparte las
        # tres dimensiones -> más alineado con T1 (2/3 de la norma) que T0.
        _plan(tmp_path)
        _write(tmp_path, "docs/nota.md", "MARKER_T0 MARKER_T1 MARKER_T1B texto mixto")
        _write(
            tmp_path,
            "docs/design/atlas_master_plan.md",
            "## 5. El plan por tramos\n\n"
            "### T0 — Sucesión\n\nMARKER_T0 solo esto.\n\n"
            "### T1 — Autoconstrucción\n\nMARKER_T1 MARKER_T1B mucho más peso.\n",
        )
        inventory = inventory_corpus(tmp_path)

        result = classify_corpus_semantically(
            inventory,
            repo_root=tmp_path,
            embedder=_FakeEmbedder(["MARKER_T0", "MARKER_T1", "MARKER_T1B"]),
        )

        nota = next(d for d in result["docs"] if d["path"] == "docs/nota.md")
        assert nota["semantic_match"] == "T1"


class TestCliWiring:
    def test_corpus_inventory_semantic_flag_end_to_end(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        # wire-before-claim: --semantic tiene un caller de producción real.
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        _plan(tmp_path)
        _write(tmp_path, "docs/nota.md", "MARKER_T0 esta nota habla de sucesión")
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
        monkeypatch.setenv("ATLAS_EMBEDDER", "stub")  # sin cargar el modelo ONNX
        runner = CliRunner()

        result = runner.invoke(cli, ["corpus-inventory", "--semantic"])

        assert result.exit_code == 0, result.output
        assert "sin_clasificar tras semántica" in result.output
        assert "umbral coseno=" in result.output

    def test_corpus_inventory_without_semantic_flag_unchanged(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        from click.testing import CliRunner

        from atlas.interfaces.cli import cli

        _plan(tmp_path)
        monkeypatch.setenv("ATLAS_CORE_ROOT", str(tmp_path))
        runner = CliRunner()

        result = runner.invoke(cli, ["corpus-inventory"])

        assert result.exit_code == 0, result.output
        assert "umbral coseno=" not in result.output
