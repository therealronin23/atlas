from __future__ import annotations

import difflib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from packaging.version import InvalidVersion, Version
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


def _version_in_range(installed: str, ranges: list[dict]) -> bool:
    """Devuelve True si installed cae dentro de algún rango OSV afectado.

    Formato OSV: {"type": "SEMVER"|"ECOSYSTEM"|"GIT", "events": [{"introduced":"X"},{"fixed":"Y"}]}
    Rango [introduced, fixed). Rangos GIT se ignoran. ranges vacío → False.
    """
    if not ranges:
        return False
    try:
        inst_ver = Version(installed)
    except InvalidVersion:
        return False
    for rng in ranges:
        if rng.get("type") == "GIT":
            continue
        introduced_str = "0"
        fixed_str = None
        for event in rng.get("events", []):
            if "introduced" in event:
                introduced_str = event["introduced"] or "0"
            if "fixed" in event:
                fixed_str = event["fixed"]
        try:
            intro_ver = Version(introduced_str if introduced_str else "0")
            if inst_ver >= intro_ver:
                if fixed_str is None or inst_ver < Version(fixed_str):
                    return True
        except InvalidVersion:
            continue
    return False


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
                if not _version_in_range(installed, affected.get("ranges", [])):
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


class CveDepProposer:
    """Materializa un bump de seguridad (CVE-driven) como patch para ColdUpdate.

    Recibe un SelfRelevantFinding con fixed_version conocida, genera un diff
    unificado sobre pyproject.toml y lo entrega a ColdUpdateManager.propose
    vía el callable inyectado. Nunca aplica el cambio solo.
    """

    AGENT = "knowledge.cve_dep_proposer"

    def __init__(
        self,
        *,
        pyproject_path: Path,
        propose: "Callable[..., Any]",
        merkle: "Any",
    ) -> None:
        self._pyproject = pyproject_path
        self._propose = propose
        self._merkle = merkle

    def propose_bump(self, finding: SelfRelevantFinding) -> "Any | None":
        """Propone dep-bump desde installed hasta fixed_version vía ColdUpdate.

        Devuelve la propuesta creada, o None si no aplica (sin fixed_version,
        dep no encontrada en pyproject, o diff vacío).
        """
        if finding.fixed_version is None:
            return None

        try:
            original = self._pyproject.read_text(encoding="utf-8")
        except OSError:
            self._audit(finding, result="pyproject_unreadable", proposal=None)
            return None

        bumped = self._bump(original, finding)
        if bumped is None or bumped == original:
            self._audit(finding, result="dep_not_in_pyproject", proposal=None)
            return None

        patch = self._unified_diff(original, bumped)
        risk = self._risk(finding.severity)
        intent = (
            f"CVE {finding.vuln_id}: bump {finding.dep} "
            f"{finding.installed_version} → {finding.fixed_version}"
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
            risk=risk,
            evidence={
                "dependency": finding.dep,
                "from": finding.installed_version,
                "to": finding.fixed_version,
                "vuln_id": finding.vuln_id,
                "severity": finding.severity,
            },
        )
        self._audit(finding, result="proposed", proposal=proposal)
        return proposal

    # ------------------------------------------------------------------

    def _bump(self, text: str, finding: SelfRelevantFinding) -> "str | None":
        name = re.escape(finding.dep)
        current = re.escape(finding.installed_version)
        pattern = re.compile(
            rf'({name}(?:\[[^\]]*\])?>=){current}([,\s"\'\n]|$)'
        )
        new_text, n = pattern.subn(
            rf'\g<1>{finding.fixed_version}\g<2>', text, count=1
        )
        return new_text if n == 1 else None

    def _unified_diff(self, original: str, bumped: str) -> str:
        rel = self._pyproject.name
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                bumped.splitlines(keepends=True),
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            )
        )

    @staticmethod
    def _risk(severity: "str | None") -> str:
        if severity is None:
            return "medium"
        try:
            return "high" if float(severity) > 7.0 else "medium"
        except (ValueError, TypeError):
            return "medium"

    def _audit(
        self, finding: SelfRelevantFinding, *, result: str, proposal: "Any"
    ) -> None:
        try:
            pid = getattr(proposal, "id", None)
            self._merkle.log(
                action="knowledge.cve_dep_proposed",
                agent=self.AGENT,
                result=result,
                risk_level="moderate",
                payload={
                    "dependency": finding.dep,
                    "from": finding.installed_version,
                    "to": finding.fixed_version,
                    "vuln_id": finding.vuln_id,
                    "proposal_id": pid,
                    "applied": False,
                },
            )
        except Exception:  # noqa: BLE001 — la auditoría no rompe el flujo
            pass
