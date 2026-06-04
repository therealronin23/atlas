"""ADR-039 slice 7 — Codegen como patch dirigido (revisable, nunca apply solo).

El humano **apunta** un objetivo (``CodegenTarget``: qué cambiar y en qué
fichero). El proposer pide a un generador (LLM de control) un diff unificado,
**impone fail-closed que el patch solo toca el fichero apuntado** (dentro de los
prefijos permitidos), y lo entrega a ColdUpdate (ADR-025) con
``origin="self_audit"``. ColdUpdate valida en worktree (pytest+mypy) y la
adopción exige el seam del decisor (ADR-040): el humano revisa el diff antes de
nada.

Coherencia con ADR-025 ("no autonomous code generation in MVP"): esto es
*post-MVP* y entra **solo** como patch revisable, gateado igual que un patch
manual — nunca como apply autónomo. La generación es libre; la *aplicación* no.
A diferencia del Analyst, aquí no hay contenido no confiable: el objetivo lo
fija el humano, no un foro. El guard de alcance evita que el LLM, por error o
por desvío, edite ficheros distintos del apuntado.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from atlas.core.self_maintenance.candidate import CodegenTarget
from atlas.logging.merkle_logger import MerkleLogger

# Mismos prefijos que ColdUpdate: el patch nunca sale de estas zonas.
_ALLOWED_PREFIXES = ("src/", "tests/", "scripts/", "docs/", "config/")

# Cabeceras de fichero de un diff unificado / git.
_FILE_HDR = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", re.MULTILINE)
_GIT_HDR = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.MULTILINE)


class CodegenProposer:
    """Genera un patch dirigido y lo entrega a ColdUpdate. Nunca aplica."""

    AGENT = "self_maintenance.codegen_proposer"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        generate: Callable[[CodegenTarget], str],
        propose: Callable[..., Any],
    ) -> None:
        self._merkle = merkle
        self._generate = generate
        self._propose = propose

    def propose_patch(self, target: CodegenTarget) -> Any:
        """Materializa un patch para el objetivo apuntado. ``None`` si no procede."""
        if not self._target_in_scope(target.path):
            self._audit(target, result="target_out_of_scope", proposal=None)
            return None

        try:
            raw = self._generate(target)
        except Exception:  # noqa: BLE001 — fallo del generador → sin patch
            self._audit(target, result="generation_failed", proposal=None)
            return None

        patch = self._extract_diff(raw)
        if patch is None:
            self._audit(target, result="no_diff", proposal=None)
            return None

        touched = self._touched_paths(patch)
        if not touched or any(p != target.path for p in touched):
            # El patch toca algo distinto del fichero apuntado: rechazo fail-closed.
            self._audit(target, result="patch_out_of_scope", proposal=None)
            return None

        with tempfile.NamedTemporaryFile(
            "w", suffix=".patch", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(patch)
            patch_path = Path(fh.name)

        proposal = self._propose(
            f"codegen dirigido: {target.goal} ({target.path})",
            patch_path,
            origin="self_audit",
            risk="high",
            evidence={"goal": target.goal, "path": target.path},
        )
        self._audit(target, result="proposed", proposal=proposal)
        return proposal

    # ------------------------------------------------------------------

    @staticmethod
    def _target_in_scope(path: str) -> bool:
        return bool(path) and path.startswith(_ALLOWED_PREFIXES)

    @staticmethod
    def _extract_diff(raw: str) -> str | None:
        """Saca el diff del texto del LLM (quita fences ```), o ``None`` si no hay."""
        text = raw.strip()
        fence = re.search(r"```(?:diff|patch)?\n(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        if "--- " in text and "+++ " in text:
            return text + ("\n" if not text.endswith("\n") else "")
        return None

    @staticmethod
    def _touched_paths(patch: str) -> set[str]:
        """Ficheros que el patch modifica (sin ``a/``/``b/``, sin ``/dev/null``)."""
        paths: set[str] = set()
        for m in _FILE_HDR.finditer(patch):
            paths.add(m.group(1))
        for m in _GIT_HDR.finditer(patch):
            paths.add(m.group(1))
            paths.add(m.group(2))
        paths.discard("/dev/null")
        return paths

    def _audit(self, target: CodegenTarget, *, result: str, proposal: Any) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.codegen_proposer_patch",
                agent=self.AGENT,
                result=result,
                risk_level="high",
                payload={
                    "goal": target.goal[:200],
                    "path": target.path,
                    "proposal_id": getattr(proposal, "id", None),
                    "applied": False,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe la materialización
            pass
