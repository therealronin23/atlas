"""
Atlas 24h Self-Audit Loop.

This module implements the cold, auditable loop. It observes the repository and
runtime, records findings and candidate improvements, and writes reports. It
does not hot-patch Atlas and it does not merge into main.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from atlas.core.environment_sensor import capture_fingerprint
from atlas.logging.merkle_logger import MerkleLogger


@dataclass
class SelfAuditFinding:
    id: str
    category: str
    severity: str
    title: str
    detail: str
    recommendation: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class SelfAuditCandidate:
    id: str
    title: str
    risk: str
    status: str
    rationale: str
    patch_path: str | None = None
    proposal_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SelfAuditCycle:
    index: int
    started_at: str
    finished_at: str
    git: dict[str, Any]
    environment: dict[str, Any]
    health: dict[str, Any]
    findings: list[SelfAuditFinding] = field(default_factory=list)
    candidates: list[SelfAuditCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "git": self.git,
            "environment": self.environment,
            "health": self.health,
            "findings": [f.to_dict() for f in self.findings],
            "candidates": [c.to_dict() for c in self.candidates],
        }


@dataclass
class SelfAuditReport:
    id: str
    profile: str
    hours_requested: float
    started_at: str
    finished_at: str
    status: str
    cycles: list[SelfAuditCycle] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile": self.profile,
            "hours_requested": self.hours_requested,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "cycles": [c.to_dict() for c in self.cycles],
        }


class SelfAuditRunner:
    """Runs bounded, auditable self-audit cycles."""

    VALID_PROFILES = {"quick", "full", "resilience", "autonomy"}

    def __init__(
        self,
        project_root: Path,
        merkle: MerkleLogger,
        *,
        docs_dir: Path | None = None,
        health_provider: Callable[[], dict[str, Any]] | None = None,
        patch_generator: Any = None,   # PatchGenerator | None (lazy to avoid import cycle)
    ) -> None:
        self._root = project_root.resolve()
        self._merkle = merkle
        self._docs_dir = docs_dir or (self._root / "docs")
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._docs_dir / "self_audit_latest.json"
        self._stop_file = self._root / ".atlas_self_audit_stop"
        self._health_provider = health_provider
        self._patch_generator = patch_generator

    def run(
        self,
        *,
        hours: float = 24.0,
        profile: str = "full",
        cycle_interval_minutes: float = 60.0,
        max_cycles: int | None = None,
        dry_run: bool = False,
    ) -> SelfAuditReport:
        if profile not in self.VALID_PROFILES:
            raise ValueError(f"profile invalido: {profile}")
        if hours <= 0:
            raise ValueError("hours debe ser > 0")
        if cycle_interval_minutes <= 0:
            raise ValueError("cycle_interval_minutes debe ser > 0")

        started = self._now()
        report = SelfAuditReport(
            id=datetime.now(timezone.utc).strftime("self-audit-%Y%m%d-%H%M%S"),
            profile=profile,
            hours_requested=hours,
            started_at=started,
            finished_at=started,
            status="running",
        )
        self._clear_stop()
        self._log("self_audit.started", "success", {
            "report_id": report.id,
            "hours": hours,
            "profile": profile,
            "dry_run": dry_run,
        })

        deadline = time.monotonic() + (hours * 3600)
        interval_s = cycle_interval_minutes * 60
        cycles_target = max_cycles or max(1, int((hours * 60) // cycle_interval_minutes))

        for index in range(1, cycles_target + 1):
            if self.stop_requested() or time.monotonic() >= deadline:
                report.status = "stopped" if self.stop_requested() else "completed"
                break
            cycle = self.run_cycle(index=index, profile=profile, dry_run=dry_run)
            report.cycles.append(cycle)
            report.finished_at = cycle.finished_at
            self._write_report(report)
            if index < cycles_target and time.monotonic() + interval_s < deadline:
                time.sleep(interval_s)

        if report.status == "running":
            report.status = "completed"
            report.finished_at = self._now()
        self._write_report(report)
        self._log("self_audit.finished", "success", {
            "report_id": report.id,
            "status": report.status,
            "cycles": len(report.cycles),
        })
        return report

    def run_cycle(
        self,
        *,
        index: int = 1,
        profile: str = "full",
        dry_run: bool = False,
    ) -> SelfAuditCycle:
        started = self._now()
        git = self._git_snapshot()
        environment = capture_fingerprint(project_root=self._root).to_dict()
        health = self._health_snapshot()
        findings = self._diagnose(git, health)
        candidates = self._candidates_from_findings(findings, dry_run=dry_run)
        finished = self._now()
        cycle = SelfAuditCycle(
            index=index,
            started_at=started,
            finished_at=finished,
            git=git,
            environment=environment,
            health=health,
            findings=findings,
            candidates=candidates,
        )
        self._log("self_audit.cycle", "success", {
            "index": index,
            "profile": profile,
            "findings": len(findings),
            "candidates": len(candidates),
            "dry_run": dry_run,
        })
        return cycle

    def status(self) -> dict[str, Any]:
        latest = self.latest_report()
        return {
            "stop_requested": self.stop_requested(),
            "latest_report": latest,
        }

    def latest_report(self) -> dict[str, Any] | None:
        if not self._state_file.exists():
            return None
        try:
            return json.loads(self._state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def proposals(self) -> list[dict[str, Any]]:
        report = self.latest_report() or {}
        proposals: list[dict[str, Any]] = []
        for cycle in report.get("cycles", []):
            proposals.extend(cycle.get("candidates", []))
        return proposals

    def stop(self) -> None:
        self._stop_file.write_text(self._now(), encoding="utf-8")
        self._log("self_audit.stop_requested", "success", {})

    def stop_requested(self) -> bool:
        return self._stop_file.exists()

    def _clear_stop(self) -> None:
        if self._stop_file.exists():
            self._stop_file.unlink()

    def _git_snapshot(self) -> dict[str, Any]:
        return {
            "branch": self._git(["branch", "--show-current"]),
            "head": self._git(["rev-parse", "--short", "HEAD"]),
            "status_short": self._git(["status", "--short"]).splitlines(),
        }

    def _health_snapshot(self) -> dict[str, Any]:
        if self._health_provider is None:
            return {"available": False, "reason": "no health_provider"}
        try:
            return {"available": True, "report": self._health_provider()}
        except Exception as exc:  # pragma: no cover - defensive boundary
            return {"available": False, "reason": str(exc)}

    def _diagnose(
        self,
        git: dict[str, Any],
        health: dict[str, Any],
    ) -> list[SelfAuditFinding]:
        findings: list[SelfAuditFinding] = []
        status = [str(s) for s in git.get("status_short", [])]
        tracked_dirty = [s for s in status if not s.startswith("?? ")]
        untracked = [s[3:] for s in status if s.startswith("?? ")]
        if tracked_dirty:
            findings.append(SelfAuditFinding(
                id="repo-dirty-tracked",
                category="resilience",
                severity="high",
                title="Tracked worktree changes present",
                detail="Tracked files are modified before self-audit begins.",
                recommendation="Start the 24h loop from a clean tracked worktree.",
            ))
        if ".claude/" in untracked or (self._root / ".claude").exists():
            findings.append(SelfAuditFinding(
                id="claude-untracked",
                category="security",
                severity="medium",
                title=".claude directory is untracked",
                detail=".claude/ exists outside git. Keep it excluded unless explicitly approved.",
                recommendation="Do not include .claude/ in self-audit patches.",
            ))
        if not (self._root / "AGENTS.md").exists():
            findings.append(SelfAuditFinding(
                id="agents-missing",
                category="docs_drift",
                severity="critical",
                title="AGENTS.md missing",
                detail="AGENTS.md is the session source of truth.",
                recommendation="Restore AGENTS.md before autonomous audit cycles.",
            ))
        if not health.get("available"):
            findings.append(SelfAuditFinding(
                id="health-unavailable",
                category="observability",
                severity="medium",
                title="Health provider unavailable",
                detail=str(health.get("reason", "")),
                recommendation="Wire Orchestrator.health_report into SelfAuditRunner.",
            ))
        return findings

    def _candidates_from_findings(
        self,
        findings: list[SelfAuditFinding],
        *,
        dry_run: bool,
    ) -> list[SelfAuditCandidate]:
        candidates: list[SelfAuditCandidate] = []
        for finding in findings:
            risk = "high" if finding.severity in {"critical", "high"} else "medium"
            candidate = SelfAuditCandidate(
                id=f"candidate-{finding.id}",
                title=f"Resolve {finding.title}",
                risk=risk,
                status="dry_run" if dry_run else "needs_patch",
                rationale=finding.recommendation,
            )
            # Item 3 MVP: if a PatchGenerator is wired in, try to auto-stub a
            # patch for the candidate. Patches are .patch files awaiting HITL
            # review (never hot-applied here).
            if not dry_run and self._patch_generator is not None:
                try:
                    patch = self._patch_generator.generate_for_candidate(
                        candidate, finding,
                    )
                except Exception as exc:  # noqa: BLE001 — gen failure must not break loop
                    self._log("self_audit.patch_failed", "failure", {
                        "candidate": candidate.id,
                        "error": str(exc),
                    })
                    patch = None
                if patch is not None:
                    candidate.patch_path = patch.patch_path
                    candidate.status = "patch_proposed"
                    self._log("self_audit.patch_generated", "success", {
                        "candidate": candidate.id,
                        "category": finding.category,
                        "patch_id": patch.id,
                        "risk": patch.risk,
                        "patch_path": patch.patch_path,
                    })
            candidates.append(candidate)
        return candidates

    def _write_report(self, report: SelfAuditReport) -> None:
        data = report.to_dict()
        self._state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        dated = self._docs_dir / f"self_audit_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        dated.write_text(self._render_markdown(data), encoding="utf-8")

    def _render_markdown(self, data: dict[str, Any]) -> str:
        lines = [
            f"# Self Audit Report — {data['id']}",
            "",
            f"- Status: `{data['status']}`",
            f"- Profile: `{data['profile']}`",
            f"- Started: `{data['started_at']}`",
            f"- Finished: `{data['finished_at']}`",
            f"- Cycles: `{len(data.get('cycles', []))}`",
            "",
            "## Findings",
            "",
        ]
        findings = [
            finding
            for cycle in data.get("cycles", [])
            for finding in cycle.get("findings", [])
        ]
        if not findings:
            lines.append("- No findings.")
        for finding in findings:
            lines.append(
                f"- **{finding['severity']}** `{finding['category']}` — "
                f"{finding['title']}: {finding['recommendation']}"
            )
        lines.extend(["", "## Candidates", ""])
        candidates = [
            candidate
            for cycle in data.get("cycles", [])
            for candidate in cycle.get("candidates", [])
        ]
        if not candidates:
            lines.append("- No candidates.")
        for candidate in candidates:
            lines.append(
                f"- `{candidate['status']}` **{candidate['risk']}** — "
                f"{candidate['title']}"
            )
        lines.append("")
        return "\n".join(lines)

    def _git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._root,
            capture_output=True,
            text=True,
            check=False,
        )
        return (result.stdout or result.stderr or "").strip()

    def _log(self, action: str, result: str, payload: dict[str, Any]) -> None:
        self._merkle.log(
            action=action,
            agent="self_audit_runner",
            result=result,
            risk_level="high",
            payload=payload,
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
