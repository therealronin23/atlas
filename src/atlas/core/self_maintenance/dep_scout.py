"""ADR-039 slice 6 — Scout de dependencias (bumps PyPI, read-only).

Descubre dependencias con una versión más nueva disponible en PyPI (fuente
autoritativa). Mismo molde que ``RegistryScout``: egress gateado por
``SSRFBridge``, fetch inyectado (tests sin red real), fail-closed en egress,
red y parseo. **No muta ni propone:** emite ``DepCandidate``; la
materialización del bump como patch revisable es del ``DepProposer`` (mismo
slice) y la validación/apply es de ColdUpdate (ADR-025).

Las pre-releases se descartan: solo se proponen versiones estables. La
comparación de versiones usa ``packaging.version`` (ya presente como dep
transitiva), no heurística propia.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from packaging.version import InvalidVersion, Version

from atlas.core.self_maintenance.candidate import (
    PROVENANCE_AUTHORITATIVE,
    DepCandidate,
    Source,
)
from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.ssrf_bridge import SSRFBridge

# JSON autoritativo de PyPI para una distribución.
PYPI_JSON_URL = "https://pypi.org/pypi/{name}/json"


class DepScout:
    """Descubre bumps de dependencias en PyPI (ADR-039 slice 6). Read-only."""

    AGENT = "self_maintenance.dep_scout"

    def __init__(
        self,
        *,
        merkle: MerkleLogger,
        bridge: SSRFBridge,
        fetch: Callable[[str], str],
        deps_provider: Callable[[], list[tuple[str, str]]],
    ) -> None:
        self._merkle = merkle
        self._bridge = bridge
        self._fetch = fetch
        self._deps_provider = deps_provider

    def discover(self) -> list[DepCandidate]:
        """Devuelve las deps con bump estable disponible. Fail-closed por dep."""
        candidates: list[DepCandidate] = []
        for name, current in self._deps_provider() or []:
            cand = self._check_one(name, current)
            if cand is not None:
                candidates.append(cand)
        self._audit(len(candidates), [c.name for c in candidates])
        return candidates

    def _check_one(self, name: str, current: str) -> DepCandidate | None:
        url = PYPI_JSON_URL.format(name=name)
        if not self._bridge.check(url).allowed:
            return None
        try:
            body = self._fetch(url)
            latest = str(json.loads(body)["info"]["version"]).strip()
        except Exception:  # noqa: BLE001 — fail-closed: red/JSON/clave ausente → se omite
            return None
        if not self._is_newer_stable(latest, current):
            return None
        return DepCandidate(
            name=name,
            current=current,
            latest=latest,
            source=Source(
                provenance=PROVENANCE_AUTHORITATIVE,
                url=url,
                raw_excerpt="",  # PyPI JSON es estructurado; no hay prosa que digerir
            ),
        )

    @staticmethod
    def _is_newer_stable(latest: str, current: str) -> bool:
        """``True`` solo si ``latest`` es estable y estrictamente mayor que ``current``."""
        try:
            lv, cv = Version(latest), Version(current)
        except InvalidVersion:
            return False
        if lv.is_prerelease or lv.is_devrelease:
            return False
        return lv > cv

    def _audit(self, count: int, names: list[str]) -> None:
        try:
            self._merkle.log(
                action="self_maintenance.dep_scout_discover",
                agent=self.AGENT,
                result="ok",
                risk_level="safe",
                payload={"candidate_count": count, "names": names},
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe el descubrimiento
            pass
