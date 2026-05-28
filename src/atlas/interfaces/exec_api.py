"""
ADR-027 — /api/exec/* endpoints for Hermes-driven capability execution.

Atlas exposes a small REST surface so Hermes-Agent (running in the VPS) can
ask Atlas (running on the laptop) to perform actions on the user's behalf:
shell commands, file ops, browser actions.

Security model:

  HMAC-SHA256 over the raw request body with the shared HERMES_API_KEY.
  Plus a millisecond-precision ISO timestamp header to defeat replay
  attacks (rejected if drift > 300s).

  Once authenticated, the request goes through the SAME ADR-020 capability
  pipeline as direct CLI use — CapabilityIssuer + PermissionProfile +
  AtlasExecutor + MerkleLogger. Hermes does NOT gain new privileges, only
  a transport.

  All refusals and successes hit Merkle, including the HMAC-key-id hash
  for forensic correlation.

  The router is mounted into the dashboard FastAPI app only if
  HERMES_API_KEY is present in the environment. If not, requests get 503
  (operational misconfig, not auth fail) and a one-shot Merkle warning
  fires at attach time.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADER_SIGNATURE = "X-Hermes-Signature"
HEADER_TIMESTAMP = "X-Hermes-Timestamp"
TIMESTAMP_DRIFT_S = 300   # 5 min; matches typical NTP tolerance
SHARED_SECRET_ENV = "HERMES_API_KEY"


# ---------------------------------------------------------------------------
# HMAC helpers
# ---------------------------------------------------------------------------


def _shared_secret() -> bytes | None:
    raw = os.environ.get(SHARED_SECRET_ENV, "").strip()
    return raw.encode("utf-8") if raw else None


def _verify_signature(secret: bytes, body: bytes, signature_hex: str) -> bool:
    """Constant-time HMAC-SHA256 verification."""
    if not signature_hex:
        return False
    try:
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    except Exception:
        return False
    return hmac.compare_digest(expected, signature_hex.strip())


def _verify_timestamp(ts_header: str) -> tuple[bool, str]:
    """Parse ISO-8601 timestamp; reject if drift > TIMESTAMP_DRIFT_S."""
    if not ts_header:
        return False, "missing"
    try:
        # Accept "...Z" and "+00:00" suffixes
        normalized = ts_header.strip().replace("Z", "+00:00")
        ts = datetime.fromisoformat(normalized)
    except Exception:
        return False, "unparseable"
    now = datetime.now(timezone.utc)
    drift = abs((now - ts).total_seconds())
    if drift > TIMESTAMP_DRIFT_S:
        return False, f"drift_{int(drift)}s"
    return True, "ok"


def _key_id(secret: bytes) -> str:
    """First 8 hex chars of SHA-256(secret). Logged for correlation; never reveals the secret."""
    return hashlib.sha256(secret).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Request authentication (centralised)
# ---------------------------------------------------------------------------


async def _authenticate(request: Request, orch: Any) -> bytes:
    """Verify the HMAC + timestamp on the request, return the raw body.

    Raises HTTPException on failure. Always logs the refusal to Merkle.
    """
    secret = _shared_secret()
    if not secret:
        # Misconfig — different from auth fail to surface it in logs
        orch._merkle.log(
            action="exec.refused.no_key",
            agent="exec_api",
            result="refused",
            risk_level="moderate",
            payload={"reason": f"{SHARED_SECRET_ENV} not configured"},
        )
        raise HTTPException(status_code=503, detail="exec api not configured")

    body = await request.body()

    ts_ok, ts_reason = _verify_timestamp(request.headers.get(HEADER_TIMESTAMP, ""))
    if not ts_ok:
        orch._merkle.log(
            action="exec.refused.stale_request",
            agent="exec_api",
            result="refused",
            risk_level="moderate",
            payload={"reason": ts_reason, "key_id": _key_id(secret)},
        )
        raise HTTPException(status_code=401, detail="invalid timestamp")

    sig = request.headers.get(HEADER_SIGNATURE, "")
    if not _verify_signature(secret, body, sig):
        orch._merkle.log(
            action="exec.refused.bad_signature",
            agent="exec_api",
            result="refused",
            risk_level="high",
            payload={"key_id": _key_id(secret)},
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    return body


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


def build_router(orch_provider: Any) -> APIRouter:
    """Build the /api/exec router.

    `orch_provider` is a callable returning the live Orchestrator. We accept
    it as a parameter (rather than importing dashboard._get_orch directly)
    to avoid a circular import and to keep the module unit-testable.
    """
    router = APIRouter(prefix="/api/exec", tags=["exec"])

    # ------------------------------------------------------------------
    # POST /api/exec/shell
    # ------------------------------------------------------------------

    @router.post("/shell")
    async def exec_shell(request: Request) -> dict[str, Any]:
        """
        Run a shell command via AtlasExecutor with an ExecCapability.

        Request body (JSON):
          {
            "command": "git",
            "args": ["status", "--short"],
            "working_dir": "tmp",   # optional, relative to workspace
            "timeout_s": 30         # optional, 1..600
          }
        """
        orch = orch_provider()
        body = await _authenticate(request, orch)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json body")

        command = payload.get("command", "")
        args = tuple(payload.get("args", []) or [])
        timeout_s = int(payload.get("timeout_s", 30))
        working_dir = payload.get("working_dir") or None

        try:
            cap = orch.capability_issuer.issue_exec(
                command,
                args=args,
                working_dir=working_dir,
                timeout_s=timeout_s,
            )
        except Exception as exc:
            orch._merkle.log(
                action="exec.refused.capability_denied",
                agent="exec_api",
                result="refused",
                risk_level="high",
                payload={"verb": "shell", "command": command, "reason": str(exc)},
            )
            raise HTTPException(status_code=403, detail=str(exc))

        try:
            result = orch.executor.execute_exec(cap)
        except Exception as exc:
            orch._merkle.log(
                action="exec.failed.shell",
                agent="exec_api",
                result="failure",
                risk_level="moderate",
                payload={"command": command, "error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=f"execution failed: {exc}")

        # SandboxResult is a dataclass with stdout/stderr/returncode/duration_ms
        rc = getattr(result, "returncode", -1)
        orch._merkle.log(
            action="exec.shell.via_hermes",
            agent="exec_api",
            result="success" if rc == 0 else "failure",
            risk_level="moderate",
            payload={
                "command": command,
                "returncode": rc,
                "duration_ms": getattr(result, "duration_ms", 0),
            },
        )
        return {
            "ok": rc == 0,
            "returncode": rc,
            "stdout": getattr(result, "stdout", ""),
            "stderr": getattr(result, "stderr", ""),
            "duration_ms": getattr(result, "duration_ms", 0),
        }

    # ------------------------------------------------------------------
    # POST /api/exec/file
    # ------------------------------------------------------------------

    @router.post("/file")
    async def exec_file(request: Request) -> dict[str, Any]:
        """
        Read or write a file via AtlasExecutor + Read/WriteCapability.

        Request body (JSON):
          {"action": "read",  "path": "tmp/foo.txt"}
          {"action": "write", "path": "tmp/foo.txt", "data": "...", "encoding": "utf-8"}
        """
        orch = orch_provider()
        body = await _authenticate(request, orch)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json body")

        action = payload.get("action", "")
        path = payload.get("path", "")
        if action not in {"read", "write"} or not path:
            raise HTTPException(status_code=400, detail="action must be read|write and path required")

        try:
            if action == "read":
                cap = orch.capability_issuer.issue_read(path)
                data = orch.executor.execute_read(cap)
                rc_ok = True
                orch._merkle.log(
                    action="exec.file.read.via_hermes",
                    agent="exec_api",
                    result="success",
                    risk_level="safe",
                    payload={"path": path, "bytes": len(data)},
                )
                # Return as text if utf-8 decodable; else base64
                try:
                    return {"ok": True, "data": data.decode("utf-8"), "encoding": "utf-8"}
                except UnicodeDecodeError:
                    import base64
                    return {"ok": True, "data": base64.b64encode(data).decode("ascii"), "encoding": "base64"}
            else:
                cap = orch.capability_issuer.issue_write(path)
                encoding = payload.get("encoding", "utf-8")
                if encoding == "base64":
                    import base64
                    raw = base64.b64decode(payload.get("data", ""))
                else:
                    raw = payload.get("data", "").encode("utf-8")
                written = orch.executor.execute_write(cap, raw)
                orch._merkle.log(
                    action="exec.file.write.via_hermes",
                    agent="exec_api",
                    result="success",
                    risk_level="moderate",
                    payload={"path": path, "bytes": written},
                )
                return {"ok": True, "bytes_written": written}
        except HTTPException:
            raise
        except Exception as exc:
            orch._merkle.log(
                action=f"exec.failed.file_{action}",
                agent="exec_api",
                result="failure",
                risk_level="moderate",
                payload={"path": path, "error": str(exc)},
            )
            raise HTTPException(status_code=403, detail=str(exc))

    # ------------------------------------------------------------------
    # POST /api/exec/intent
    # ------------------------------------------------------------------

    @router.post("/intent")
    async def exec_intent(request: Request) -> dict[str, Any]:
        """
        Run a natural-language intent through Atlas's full pipeline.

        Hermes (VPS) delegates here when Telegram asks for anything beyond
        small talk — search, exec, file, memory. Atlas owns the skills;
        Hermes is just the I/O hemisphere.

        Request body (JSON):
          {"intent": "busca cuándo se inventó el teléfono"}

        Returns:
          {"ok": bool, "task_id": str, "status": str,
           "result": Any, "error": str|None, "route": str|None,
           "tool": str|None}
        """
        from atlas.core.contracts import TaskSource

        orch = orch_provider()
        body = await _authenticate(request, orch)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json body")

        intent = (payload.get("intent") or "").strip()
        if not intent:
            raise HTTPException(status_code=400, detail="intent required")

        try:
            task = orch.handle_intent(intent, source=TaskSource.API)
        except Exception as exc:
            orch._merkle.log(
                action="exec.failed.intent",
                agent="exec_api",
                result="failure",
                risk_level="moderate",
                payload={"intent": intent[:200], "error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=f"intent failed: {exc}")

        orch._merkle.log(
            action="exec.intent.via_hermes",
            agent="exec_api",
            result="success" if task.status.value == "done" else "failure",
            risk_level="moderate",
            payload={
                "intent": intent[:200],
                "task_id": task.id,
                "status": task.status.value,
                "route": task.route.value if task.route else None,
            },
        )
        return {
            "ok": task.status.value == "done",
            "task_id": task.id,
            "status": task.status.value,
            "result": task.result if task.result is not None else "",
            "error": task.error,
            "route": task.route.value if task.route else None,
            "tool": task.tool_name,
        }

    # ------------------------------------------------------------------
    # POST /api/exec/audit
    # ------------------------------------------------------------------

    @router.post("/audit")
    async def exec_audit(request: Request) -> dict[str, Any]:
        """
        Record a Hermes-origin action into Atlas's append-only Merkle ledger.

        Reverse twin direction (ADR-029): Hermes-Agent runs unaudited natively,
        so it POSTs each meaningful action here to gain a tamper-evident receipt
        in Atlas's chain. Atlas stays the system of record; Hermes gains the
        forensic guarantee it lacks.

        Request body (JSON):
          {"action": "skill.run", "result": "success",
           "risk_level": "moderate", "payload": {"skill": "..."}}

        Returns the chained receipt: {"ok", "id", "action", "hash_self", "hash_prev"}.
        """
        allowed_results = {"success", "failure", "blocked", "pending", "refused"}
        allowed_risks = {"safe", "moderate", "high", "critical"}

        orch = orch_provider()
        body = await _authenticate(request, orch)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json body")

        action = (payload.get("action") or "").strip()
        if not action:
            raise HTTPException(status_code=400, detail="action required")
        result = payload.get("result", "success")
        if result not in allowed_results:
            raise HTTPException(status_code=400, detail=f"result must be one of {sorted(allowed_results)}")
        risk = payload.get("risk_level", "safe")
        if risk not in allowed_risks:
            raise HTTPException(status_code=400, detail=f"risk_level must be one of {sorted(allowed_risks)}")
        data = payload.get("payload", {})
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="payload must be an object")

        # Provenance: force the agent and namespace the action so a Hermes-origin
        # record can never be mistaken for an Atlas-native one.
        namespaced = action if action.startswith("hermes.") else f"hermes.{action}"
        record = orch._merkle.log(
            action=namespaced,
            agent="hermes_vps",
            result=result,
            risk_level=risk,
            payload=data,
        )
        return {
            "ok": True,
            "id": record.id,
            "action": record.action,
            "hash_self": record.hash_self,
            "hash_prev": record.hash_prev,
        }

    # ------------------------------------------------------------------
    # POST /api/exec/browser
    # ------------------------------------------------------------------

    @router.post("/browser")
    async def exec_browser(request: Request) -> dict[str, Any]:
        """
        Drive Playwright (Gate F1 BrowserTool).

        Request body (JSON):
          {"action": "navigate",   "url": "https://example.com"}
          {"action": "screenshot", "name": "demo"}
          {"action": "extract",    "selector": "h1"}
        """
        orch = orch_provider()
        await _authenticate(request, orch)
        try:
            payload = json.loads(await request.body())
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid json body")

        action = payload.get("action", "")
        if action not in {"navigate", "screenshot", "extract"}:
            raise HTTPException(status_code=400, detail="action must be navigate|screenshot|extract")

        try:
            browser = orch._get_browser_tool()
        except Exception as exc:
            orch._merkle.log(
                action="exec.refused.browser_unavailable",
                agent="exec_api",
                result="refused",
                risk_level="moderate",
                payload={"reason": str(exc)},
            )
            raise HTTPException(status_code=503, detail=f"browser tool not available: {exc}")

        try:
            if action == "navigate":
                url = payload.get("url", "")
                if not url:
                    raise HTTPException(status_code=400, detail="url required")
                result = browser.navigate(url)
            elif action == "screenshot":
                name = payload.get("name", "exec_api_shot")
                result = browser.screenshot(name)
            else:
                selector = payload.get("selector", "")
                if not selector:
                    raise HTTPException(status_code=400, detail="selector required")
                result = browser.extract(selector)
        except HTTPException:
            raise
        except Exception as exc:
            orch._merkle.log(
                action=f"exec.failed.browser_{action}",
                agent="exec_api",
                result="failure",
                risk_level="moderate",
                payload={"action": action, "error": str(exc)},
            )
            raise HTTPException(status_code=500, detail=str(exc))

        orch._merkle.log(
            action=f"exec.browser.{action}.via_hermes",
            agent="exec_api",
            result="success",
            risk_level="moderate",
            payload={"action": action},
        )
        # Result may be a path or a dict — coerce
        return {"ok": True, "action": action, "result": str(result)}

    return router


__all__ = [
    "build_router",
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "TIMESTAMP_DRIFT_S",
]
