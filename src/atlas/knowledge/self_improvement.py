from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from atlas.knowledge.artifact import KnowledgeArtifact


@dataclass(frozen=True)
class SelfRelevantFinding:
    dep: str
    installed_version: str
    vuln_id: str
    severity: str | None
    fixed_version: str | None


# dep_name -> versión instalada (o None si no instalada)
InstalledProvider = Callable[[str], str | None]


def _normalize_pep503(name: str) -> str:
    # PEP 503: lowercase, colapsar guiones/guiones-bajos/puntos en "-"
    return re.sub(r"[-_.]+", "-", name).lower()


def _default_installed_provider(dep: str) -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(_normalize_pep503(dep))
    except PackageNotFoundError:
        return None


def _extract_fixed_version(vuln: dict[str, Any]) -> str | None:
    for affected in vuln.get("affected", []):
        for rng in affected.get("ranges", []):
            for event in rng.get("events", []):
                if "fixed" in event:
                    return event["fixed"]
    return None


def _extract_severity(vuln: dict[str, Any]) -> str | None:
    severities = vuln.get("severity", [])
    if severities:
        return severities[0].get("score")
    return None


class SelfImprovementBridge:
    def __init__(self, *, installed_provider: InstalledProvider | None = None) -> None:
        self._installed = installed_provider or _default_installed_provider

    def scan(self, artifact: KnowledgeArtifact) -> list[SelfRelevantFinding]:
        """Cruza las vulns del artifact OSV con las deps instaladas.

        Emite SelfRelevantFinding SOLO para deps que están instaladas en este
        entorno. NO se cablea a ningún loop vivo: es la señal que el
        self-maintenance loop podría consumir.
        """
        if artifact.domain != "security/cve":
            return []

        content = artifact.content
        if not isinstance(content, dict) or "vulns" not in content:
            return []

        findings: list[SelfRelevantFinding] = []
        for vuln in content["vulns"]:
            vuln_id = vuln.get("id", "")
            severity = _extract_severity(vuln)
            fixed_version = _extract_fixed_version(vuln)

            for affected in vuln.get("affected", []):
                pkg = affected.get("package", {})
                raw_name = pkg.get("name", "")
                if not raw_name:
                    continue
                norm_name = _normalize_pep503(raw_name)
                installed = self._installed(norm_name)
                if installed is None:
                    continue
                findings.append(
                    SelfRelevantFinding(
                        dep=norm_name,
                        installed_version=installed,
                        vuln_id=vuln_id,
                        severity=severity,
                        fixed_version=fixed_version,
                    )
                )

        return findings
