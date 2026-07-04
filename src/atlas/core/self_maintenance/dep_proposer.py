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
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

from atlas.core.self_maintenance.candidate import DepCandidate
from atlas.logging.merkle_logger import MerkleLogger


def _installed_version(name: str) -> str | None:
    """Versión instalada de la dist ``name`` en el entorno, o ``None`` si falta.

    Solo stdlib (``importlib.metadata``): sin red ni subproceso ``pip``."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


class DepProposer:
    """Convierte un ``DepCandidate`` en un patch de bump entregado a ColdUpdate."""

    AGENT = "self_maintenance.dep_proposer"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        propose: Callable[..., Any],
        pyproject_path: Path,
        installed_version: Callable[[str], str | None] | None = None,
        analyst: Any | None = None,
    ) -> None:
        self._merkle = merkle
        self._propose = propose
        self._pyproject = pyproject_path
        self._installed_version = installed_version or _installed_version
        self._analyst = analyst

    def propose_bump(self, candidate: DepCandidate) -> Any:
        """Materializa el bump y lo entrega a ColdUpdate. ``None`` si no hay diana.

        El piso propuesto se **ancla a la versión instalada**: nunca se propone un
        piso por encima de lo que el entorno tiene realmente. Sin este ancla, un
        ``latest`` mayor que lo instalado entra como ``>=latest`` y la suite pasa
        igual (pytest no valida pisos) → deriva silenciosa declarado-vs-real
        (backlog: "dep-bump autónomo crea deriva floor>instalado")."""
        try:
            original = self._pyproject.read_text(encoding="utf-8")
        except OSError:
            self._audit(candidate, result="pyproject_unreadable", proposal=None)
            return None

        floor = self._effective_floor(candidate)
        if floor is None:
            # No instalado (o versión ilegible): no se puede anclar → fail-closed.
            self._audit(candidate, result="not_installed", proposal=None)
            return None

        bumped = self._bump(original, candidate, floor)
        if bumped is None or bumped == original:
            self._audit(candidate, result="no_target", proposal=None)
            return None

        patch = self._unified_diff(original, bumped)
        intent = f"bump dependencia {candidate.name} {candidate.current} → {floor}"
        with tempfile.NamedTemporaryFile(
            "w", suffix=".patch", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(patch)
            patch_path = Path(fh.name)

        evidence: dict[str, Any] = {
            "dependency": candidate.name,
            "from": candidate.current,
            "to": floor,
            "latest": candidate.latest,
            "source": candidate.source.url,
        }
        # Juicio de DepAnalyst (señal, no gate): opcional y retrocompatible —
        # sin analyst inyectado el comportamiento es idéntico a antes.
        if self._analyst is not None:
            try:
                verdict = self._analyst.review(candidate)
                evidence["judgment"] = verdict.to_dict()
            except Exception:  # noqa: BLE001 — nunca bloquea la propuesta
                pass

        proposal = self._propose(
            intent,
            patch_path,
            origin="self_audit",
            risk="low",
            evidence=evidence,
        )
        self._audit(candidate, result="proposed", proposal=proposal)
        return proposal

    # ------------------------------------------------------------------

    def _effective_floor(self, candidate: DepCandidate) -> str | None:
        """Piso a proponer, acotado a lo instalado. ``None`` si no se puede anclar.

        Nunca devuelve un piso por encima de la versión instalada: si ``latest``
        la supera, se ancla a lo instalado (un bump real del entorno lo elevará en
        una pasada posterior, ya con esa versión presente)."""
        installed = self._installed_version(candidate.name)
        if installed is None:
            return None
        try:
            iv = Version(installed)
            lv = Version(candidate.latest)
        except InvalidVersion:
            return None
        return candidate.latest if lv <= iv else installed

    def _bump(self, text: str, candidate: DepCandidate, target: str) -> str | None:
        """Sube el piso ``>=current`` a ``>=target`` en la línea de la dep.

        Reemplaza solo la primera ocurrencia de ``<name>...>=<current>`` (con
        extras opcionales). El nombre se ancla con frontera para no confundir
        ``uvicorn`` con ``uvicorn-extra``."""
        name = re.escape(candidate.name)
        current = re.escape(candidate.current)
        # name, posibles extras [..], luego >= y la versión actual.
        pattern = re.compile(
            rf'(["\']{name}(?:\[[^\]]*\])?>=){current}(["\',])'
        )
        new_text, n = pattern.subn(rf'\g<1>{target}\g<2>', text, count=1)
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
