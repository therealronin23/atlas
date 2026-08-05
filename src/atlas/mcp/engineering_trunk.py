"""
Atlas Core — EngineeringTrunk: la raíz `engineering` del MCP trunk portable (F1).

Capa NEUTRA, transport-agnostic: expone el código dormido de src/atlas/engineering.
Permite consultar hallazgos, generar hipótesis, coordinar diagnósticos y 
ejecutar reproducciones aisladas.

Diseño: F1 del plan activo (ADC-WO-108 wired).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atlas.core.verify import UnifiedDiffVerifier, UniversalVerifier
from atlas.engineering.baselines import EngineeringReviewBaselineStore
from atlas.engineering.diagnostics import EngineeringDiagnosticCoordinator
from atlas.engineering.findings import EngineeringFindingStore, FindingLocation
from atlas.engineering.hypotheses import compose_hypotheses
from atlas.engineering.impacted_tests import impacted_tests
from atlas.engineering.review import (
    EngineeringReviewCoordinator,
    UniversalVerifierReviewAdapter,
)

class EngineeringTrunk:
    """Disciplina de ingeniería (hallazgos, reproducción, diagnóstico) como resources + tools."""

    def __init__(self, repo_root: Path, *, graph_db_path: Path | None = None) -> None:
        # `graph_db_path` es inyectable con el mismo idioma que `build_graph_server`:
        # el defecto `DEFAULT_GRAPH_DB` está clavado a `$HOME/atlas`, así que un
        # trunk "portable" que lo cerrara a fuego respondería con el grafo de ESTA
        # máquina para cualquier `repo_root` — findings de un repo contra la
        # estructura de otro.
        from atlas.memory.project_graph import DEFAULT_GRAPH_DB

        self._root = Path(repo_root)
        self._graph_db_path = Path(graph_db_path) if graph_db_path else DEFAULT_GRAPH_DB
        self._engineering_dir = self._root / "workspace" / "engineering"
        self._engineering_dir.mkdir(parents=True, exist_ok=True)

        self._findings = EngineeringFindingStore(self._engineering_dir / "findings.jsonl")
        self._baselines = EngineeringReviewBaselineStore(self._engineering_dir / "baselines.jsonl")
        self._review_coordinator = EngineeringReviewCoordinator(
            store=self._findings,
            adapters=[
                UniversalVerifierReviewAdapter(
                    adapter_id="unified_diff",
                    verifier=UniversalVerifier([UnifiedDiffVerifier()]),
                )
            ],
        )
        self._diagnostic_coordinator = EngineeringDiagnosticCoordinator(
            store=self._findings,
            classifier=None,  # Dummy fallback for now
        )
        # Bwrap jail and audit dependencies are required for reproduction
        # Here we mock them if we are just returning schemas or instantiate real ones if available
        # Audit required by EngineeringReproductionRunner
        
    def read_findings(self) -> list[dict[str, Any]]:
        """Devuelve los hallazgos recientes del journal."""
        return [f.model_dump() for f in self._findings.list()]
    
    def generate_hypotheses(self, path: str) -> dict[str, Any]:
        """Genera hipótesis combinadas (Grafo, Historia, Memoria) para una RUTA
        repo-relativa — la misma unidad que consume `get_impacted_tests` y que
        traen los findings en `FindingLocation.path`.

        Delega en `compose_hypotheses`, que ya deriva el módulo de la ruta y
        compone las tres fuentes de forma independiente. Recablearlas aquí a
        mano fue justo lo que dejó este tool sin poder ejecutarse.
        """
        from atlas.core.lesson_store import LessonStore

        composed = compose_hypotheses(
            FindingLocation(path=path),
            repo_root=self._root,
            graph_db_path=self._graph_db_path,
            lesson_store=LessonStore(self._root / "workspace" / "lessons"),
        )
        gh, hh, mh = composed.graph, composed.history, composed.memory
        return {
            "graph": {
                "available": gh.available,
                "importers": gh.importers,
                "blast_radius": gh.blast_radius,
                "reason": gh.reason,
            },
            "history": {
                "available": hh.available,
                "commit_count": hh.commit_count,
                "last_commit_at": hh.last_commit_at,
                "reason": hh.reason,
            },
            "memory": {
                "available": mh.available,
                "lesson_count": mh.lesson_count,
                "lesson_ids": list(mh.lesson_ids),
                "reason": mh.reason,
            },
        }
        
    def get_impacted_tests(self, changed_files: list[str]) -> list[str]:
        """Descubre los tests afectados por una lista de ficheros modificados."""
        return list(impacted_tests(changed_files, root=self._root))
