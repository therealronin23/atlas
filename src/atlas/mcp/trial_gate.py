"""
Atlas Core — Pieza 2: trial-en-jaula per-kind (primera vertical).

Promueve ``candidato`` → ``probado-en-jaula`` cuando el contenido estático pasa
escaneo local (sin red). NO promueve a ``verificado`` — eso sigue siendo decisión
humana + escáner adoptado (Invariant/Snyk) en un slice posterior.

Diseño: docs/design/design_catalog_enrichment.md (Pieza 2).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from atlas.mcp.catalog import CatalogEntry
from atlas.mcp.installer import InstallAction, vet_action
from atlas.mcp.plugin_admission import PluginAdmissionGate
from atlas.mcp.spawn_trial import (
    SpawnTrial,
    catalog_entry_to_cmd,
    graduated_quarantine,
    is_atlas_native_module,
    requires_network_bootstrap,
)
from atlas.security.static_content import scan_static_content

_TRIALABLE_STATIC_KINDS = frozenset({"skill", "prompt", "command", "rule"})
_INSTALL_TRIALABLE_KINDS = frozenset({"mcp", "subagent", "tool", "workflow", "hook"})


def vet_install_command(name: str, install: str) -> str | None:
    """Escaneo adoptado del argv ``install`` (SentinelGate). Sin ejecutar."""
    cmd = install.strip()
    if not cmd:
        return "sin comando install"
    try:
        argv = shlex.split(cmd)
    except ValueError as exc:
        return f"install inválido: {exc}"
    if not argv:
        return "install vacío tras parseo"
    action = InstallAction(
        name=name,
        mode="connected",
        action="connect",
        command=argv,
        note="",
    )
    return vet_action(action)


@dataclass(frozen=True)
class TrialResult:
    """Resultado de un trial en jaula (sin red)."""

    name: str
    kind: str
    passed: bool
    skipped: bool
    reason: str
    suggested_status: str | None  # probado-en-jaula si passed; None si skipped/failed

    def to_dict(self) -> dict[str, str | bool | None]:
        return {
            "name": self.name,
            "kind": self.kind,
            "passed": self.passed,
            "skipped": self.skipped,
            "reason": self.reason,
            "suggested_status": self.suggested_status,
        }


def scan_content(text: str) -> str | None:
    """Escaneo estático de contenido. Devuelve razón de veto o None si admisible."""
    return scan_static_content(text)


def promote_after_trial(current_status: str, passed: bool) -> str | None:
    """Estado sugerido tras trial. Solo promueve candidato→probado-en-jaula."""
    if not passed:
        return None
    if current_status == "candidato":
        return "probado-en-jaula"
    return None


def trial_static_content(entry: CatalogEntry, content: str) -> TrialResult:
    """Trial genérico sobre texto ya cargado (sin I/O externa)."""
    veto = scan_content(content)
    passed = veto is None
    suggested = promote_after_trial(entry.status, passed)
    return TrialResult(
        name=entry.name,
        kind=entry.kind,
        passed=passed,
        skipped=False,
        reason=veto or "contenido estático OK",
        suggested_status=suggested,
    )


class TrialGate:
    """Orquestador per-kind. Primera vertical: skills/prompts/commands/rules servidos."""

    def __init__(
        self,
        *,
        skill_root: Path | None = None,
        agents_skill_root: Path | None = None,
        content_resolver: Callable[[CatalogEntry], str | None] | None = None,
        spawn_trial: SpawnTrial | None = None,
        plugin_admission_gate: PluginAdmissionGate | None = None,
        plugin_root_resolver: Callable[[CatalogEntry], Path | None] | None = None,
    ) -> None:
        self._skill_root = skill_root
        self._agents_skill_root = agents_skill_root
        self._content_resolver = content_resolver
        self._spawn_trial = spawn_trial
        self._plugin_admission_gate = plugin_admission_gate
        self._plugin_root_resolver = plugin_root_resolver

    def trial(self, entry: CatalogEntry) -> TrialResult:
        if entry.status not in {"candidato", "probado-en-jaula"}:
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=True,
                reason=f"status {entry.status!r} no trialable (solo candidato/probado-en-jaula)",
                suggested_status=None,
            )

        if entry.kind in _TRIALABLE_STATIC_KINDS:
            content = self._resolve_content(entry)
            if content is None:
                if entry.install.strip():
                    return self._requires_staging(entry, note="sin contenido local")
                return TrialResult(
                    name=entry.name,
                    kind=entry.kind,
                    passed=False,
                    skipped=True,
                    reason="sin contenido local resoluble (follow-up: resolver fuente)",
                    suggested_status=None,
                )
            return trial_static_content(entry, content)

        if entry.kind == "plugin":
            return self._trial_staged_plugin(entry)

        if entry.kind in _INSTALL_TRIALABLE_KINDS and entry.install.strip():
            if entry.kind == "mcp":
                return self._trial_mcp_install(entry)
            return self._requires_staging(entry)

        if entry.kind == "mcp" and entry.mode == "connected":
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=True,
                reason="MCP connected sin install declarado (spawn trial pendiente)",
                suggested_status=None,
            )

        return TrialResult(
            name=entry.name,
            kind=entry.kind,
            passed=False,
            skipped=True,
            reason=f"kind {entry.kind!r} sin trial implementado aún",
            suggested_status=None,
        )

    def _trial_install_argv(self, entry: CatalogEntry, *, note: str = "") -> TrialResult:
        veto = vet_install_command(entry.name, entry.install)
        passed = veto is None
        suggested = promote_after_trial(entry.status, passed)
        suffix = f" ({note})" if note else ""
        return TrialResult(
            name=entry.name,
            kind=entry.kind,
            passed=passed,
            skipped=False,
            reason=(veto or f"install argv OK{suffix}"),
            suggested_status=suggested,
        )

    def _requires_staging(self, entry: CatalogEntry, *, note: str = "") -> TrialResult:
        """Do not mistake a clean download command for inspected third-party bytes."""

        veto = vet_install_command(entry.name, entry.install)
        if veto is not None:
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=False,
                reason=veto,
                suggested_status=None,
            )
        suffix = f" ({note})" if note else ""
        return TrialResult(
            name=entry.name,
            kind=entry.kind,
            passed=False,
            skipped=True,
            reason=f"requiere staging local + escaneo antes de trial{suffix}",
            suggested_status=None,
        )

    def _trial_mcp_install(self, entry: CatalogEntry) -> TrialResult:
        argv_result = self._trial_install_argv(entry)
        if not argv_result.passed:
            return argv_result
        cmd = catalog_entry_to_cmd(entry)
        if requires_network_bootstrap(cmd):
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=True,
                reason="MCP remoto requiere staging local + escaneo antes de trial",
                suggested_status=None,
            )
        if self._spawn_trial is None:
            # staged-artifact-is-not-an-argv: sin spawn probe real, un argv
            # local "limpio" solo es evidencia de trial para código propio
            # (atlas.mcp.*, ya confiable); un módulo de terceros sin bytes
            # locales inspeccionados sigue necesitando staging, aunque su
            # argv no dispare requires_network_bootstrap (p.ej. `python -m
            # third_party_mcp` no es npx/uvx pero tampoco es nuestro).
            if is_atlas_native_module(cmd):
                return argv_result
            return self._requires_staging(
                entry, note="sin verificación de spawn para módulo de terceros"
            )
        spawn = self._spawn_trial.probe_entry(entry)
        if spawn.skipped:
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=True,
                skipped=False,
                reason=f"install argv OK; {spawn.reason}",
                suggested_status=argv_result.suggested_status,
            )
        if not spawn.ok:
            quarantine = graduated_quarantine(
                name=entry.name, kind=entry.kind, reason=spawn.reason
            )
            suffix = f" → {quarantine.action}" if quarantine else ""
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=False,
                reason=f"{spawn.reason}{suffix}",
                suggested_status=None,
            )
        return TrialResult(
            name=entry.name,
            kind=entry.kind,
            passed=True,
            skipped=False,
            reason=spawn.reason,
            suggested_status=argv_result.suggested_status,
        )

    def _trial_staged_plugin(self, entry: CatalogEntry) -> TrialResult:
        if self._plugin_admission_gate is None or self._plugin_root_resolver is None:
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=True,
                reason="plugin requiere staging local + PluginManifest + escaneo de admisión",
                suggested_status=None,
            )
        root = self._plugin_root_resolver(entry)
        if root is None:
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=True,
                reason="plugin sin raíz de staging resoluble",
                suggested_status=None,
            )
        admission = self._plugin_admission_gate.admit(
            root,
            expected_plugin_id=entry.name,
        )
        if admission.status == "admit":
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=True,
                skipped=False,
                reason="plugin staged admitido; activación sigue pendiente de Merkle/HITL",
                suggested_status=promote_after_trial(entry.status, True),
            )
        if admission.status == "review":
            return TrialResult(
                name=entry.name,
                kind=entry.kind,
                passed=False,
                skipped=False,
                reason="plugin staged requiere revisión humana",
                suggested_status=None,
            )
        return TrialResult(
            name=entry.name,
            kind=entry.kind,
            passed=False,
            skipped=False,
            reason=f"plugin staged bloqueado: {', '.join(admission.reason_codes)}",
            suggested_status=None,
        )

    def _resolve_content(self, entry: CatalogEntry) -> str | None:
        if self._content_resolver is not None:
            return self._content_resolver(entry)
        if entry.kind == "skill":
            for path in self._skill_paths(entry.name):
                if path.is_file():
                    return path.read_text(encoding="utf-8")
        return None

    def _skill_paths(self, name: str) -> list[Path]:
        paths: list[Path] = []
        if self._skill_root is not None:
            paths.append(self._skill_root / f"{name}.md")
        if self._agents_skill_root is not None:
            paths.append(self._agents_skill_root / name / "SKILL.md")
            paths.append(self._agents_skill_root / f"{name}.md")
        return paths
