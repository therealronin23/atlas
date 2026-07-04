"""
Atlas Core — Claude Code Tool (sub-tool de Atlas que delega en el CLI 'claude').

Invoca el CLI de Claude Code como subproceso, siguiendo la misma disciplina
de gobernanza que CrawlerTool: pasa por ExternalFsBridge antes de tocar el
filesystem externo, requiere credenciales explícitas, y audita cada llamada en
Merkle. Es una herramienta de DELEGACIÓN (puede mutar el host según la tarea
que se le confíe) — el loop agéntico debe envolverla (ADR-037).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atlas.logging.merkle_logger import MerkleLogger
from atlas.security.external_fs_bridge import ExternalFsBridge


@dataclass(frozen=True)
class ClaudeCodeResult:
    task: str
    cwd: str
    success: bool
    result_text: str
    cost_usd: float
    session_id: str
    error: str | None = None


class ClaudeCodeTool:
    """Delegación gobernada hacia el CLI de Claude Code."""

    def __init__(
        self,
        workspace: Path,
        fs_bridge: ExternalFsBridge,
        merkle: MerkleLogger | None = None,
        claude_bin: str = "claude",
        timeout_s: float = 300.0,
        model: str = "claude-sonnet-5",
    ) -> None:
        self._workspace = workspace
        self._fs_bridge = fs_bridge
        self._merkle = merkle
        self._claude_bin = claude_bin
        self._timeout_s = timeout_s
        self._model = model

    def delegate(
        self, task: str, cwd: str, *, permission_mode: str = "plan"
    ) -> ClaudeCodeResult:
        decision = self._fs_bridge.check(cwd)
        if not decision.allowed:
            self._log(
                "claude_code.delegate",
                "blocked",
                risk_level="high",
                payload={"cwd": cwd, "reason": decision.reason},
            )
            raise PermissionError(
                f"ExternalFsBridge bloqueó el directorio: {decision.reason}"
            )

        if "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ:
            error = "CLAUDE_CODE_OAUTH_TOKEN no está definida en el entorno"
            self._log(
                "claude_code.delegate",
                "failed",
                risk_level="moderate",
                payload={"cwd": cwd, "task": task, "error": error},
            )
            return ClaudeCodeResult(
                task=task,
                cwd=cwd,
                success=False,
                result_text="",
                cost_usd=0.0,
                session_id="",
                error=error,
            )

        try:
            proc = subprocess.run(
                [
                    self._claude_bin,
                    "-p",
                    task,
                    "--output-format",
                    "json",
                    "--permission-mode",
                    permission_mode,
                    "--model",
                    self._model,
                ],
                cwd=decision.resolved_path,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
            )
        except subprocess.TimeoutExpired:
            error = "timeout: el comando claude excedió el tiempo límite"
            self._log(
                "claude_code.delegate",
                "failed",
                risk_level="moderate",
                payload={"cwd": cwd, "task": task, "error": error},
            )
            return ClaudeCodeResult(
                task=task,
                cwd=cwd,
                success=False,
                result_text="",
                cost_usd=0.0,
                session_id="",
                error=error,
            )

        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            error = f"stdout no es JSON válido: {(proc.stderr or proc.stdout)[:500]}"
            self._log(
                "claude_code.delegate",
                "failed",
                risk_level="moderate",
                payload={"cwd": cwd, "task": task, "error": error},
            )
            return ClaudeCodeResult(
                task=task,
                cwd=cwd,
                success=False,
                result_text="",
                cost_usd=0.0,
                session_id="",
                error=error,
            )

        is_error = bool(out.get("is_error", False))
        result_text = str(out.get("result") or "")
        session_id = str(out.get("session_id") or "")
        cost_usd = float(out.get("total_cost_usd") or 0.0)
        success = not is_error

        self._log(
            "claude_code.delegate",
            "ok" if success else "failed",
            risk_level="safe" if success else "moderate",
            payload={
                "cwd": cwd,
                "task": task,
                "success": success,
                "cost_usd": cost_usd,
                "session_id": session_id,
                "error": result_text if is_error else None,
            },
        )

        return ClaudeCodeResult(
            task=task,
            cwd=cwd,
            success=success,
            result_text=result_text,
            cost_usd=cost_usd,
            session_id=session_id,
            error=result_text if is_error else None,
        )

    def _log(
        self,
        action: str,
        result: str,
        *,
        risk_level: str = "safe",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self._merkle is None:
            return
        self._merkle.log(
            action=action,
            agent="claude_code.tool",
            result=result,
            risk_level=risk_level,
            payload=payload or {},
        )
