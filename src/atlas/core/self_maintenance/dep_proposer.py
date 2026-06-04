"""ADR-039 slice 6 — Materializa un bump de dependencia como patch revisable.

Toma un ``DepCandidate`` (descubierto por ``DepScout``), localiza el piso de la
dependencia en ``pyproject.toml``, sube el piso a la última estable y construye
un **diff unificado revisable** (`a/ b/`, aplicable por `git apply`). Entrega el
patch al pipeline de ColdUpdate (ADR-025) vía el callable ``propose`` inyectado
con ``origin="self_audit"``: ColdUpdate valida en worktree (pytest+mypy) y la
adopción real exige el seam del decisor (ADR-040). **Nunca aplica solo.**

Fail-closed: si el piso de la dep no se encuentra en ``pyproject``, no se fabrica
ningún patch (se audita y se devuelve ``None``).
"""

from __future__ import annotations

import difflib
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas.core.self_maintenance.candidate import DepCandidate
from atlas.logging.merkle_logger import MerkleLogger


class DepProposer:
    """Convierte un ``DepCandidate`` en un patch de bump entregado a ColdUpdate."""

    AGENT = "self_maintenance.dep_proposer"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        propose: Callable[..., Any],
        pyproject_path: Path,
    ) -> None:
        self._merkle = merkle
        self._propose = propose
        self._pyproject = pyproject_path

    def propose_bump(self, candidate: DepCandidate) -> Any:
        """Materializa el bump y lo entrega a ColdUpdate. ``None`` si no hay diana."""
        try:
            original = self._pyproject.read_text(encoding="utf-8")
        except OSError:
            self._audit(candidate, result="pyproject_unreadable", proposal=None)
            return None

        bumped = self._bump(original, candidate)
        if bumped is None or bumped == original:
            self._audit(candidate, result="no_target", proposal=None)
            return None

        patch = self._unified_diff(original, bumped)
        intent = (
            f"bump dependencia {candidate.name} {candidate.current} → {candidate.latest}"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".patch", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(patch)
            patch_path = Path(fh.name)

        proposal = self._propose(
            intent,
            patch_path,
            origin="self_audit",
            risk="low",
            evidence={
                "dependency": candidate.name,
                "from": candidate.current,
                "to": candidate.latest,
                "source": candidate.source.url,
            },
        )
        self._audit(candidate, result="proposed", proposal=proposal)
        return proposal

    # ------------------------------------------------------------------

    def _bump(self, text: str, candidate: DepCandidate) -> str | None:
        """Sube el piso ``>=current`` a ``>=latest`` en la línea de la dep.

        Reemplaza solo la primera ocurrencia de ``<name>...>=<current>`` (con
        extras opcionales). El nombre se ancla con frontera para no confundir
        ``uvicorn`` con ``uvicorn-extra``."""
        name = re.escape(candidate.name)
        current = re.escape(candidate.current)
        # name, posibles extras [..], luego >= y la versión actual.
        pattern = re.compile(
            rf'(["\']{name}(?:\[[^\]]*\])?>=){current}(["\',])'
        )
        new_text, n = pattern.subn(rf'\g<1>{candidate.latest}\g<2>', text, count=1)
        return new_text if n == 1 else None

    def _unified_diff(self, original: str, bumped: str) -> str:
        rel = self._pyproject.name
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            bumped.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
        )
        return "".join(diff)

    def _audit(self, candidate: DepCandidate, *, result: str, proposal: Any) -> None:
        try:
            pid = getattr(proposal, "id", None)
            self._merkle.log(
                action="self_maintenance.dep_proposer_bump",
                agent=self.AGENT,
                result=result,
                risk_level="moderate",
                payload={
                    "dependency": candidate.name,
                    "from": candidate.current,
                    "to": candidate.latest,
                    "proposal_id": pid,
                    "applied": False,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe la materialización
            pass
