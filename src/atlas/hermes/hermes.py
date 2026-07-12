"""
Atlas Core — Hermes
Adaptador abstracto, mock de v0.1, constructor de DelegationPayload y cola offline.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.contracts import (
    DelegationPayload, DelegationReceipt, DelegationResult,
    HermesStatus, QueueStatus,
)
from atlas.hermes.kanban_bridge import KanbanBridge


# ===========================================================================
# Interfaz abstracta
# ===========================================================================

class HermesAdapter(ABC):
    @abstractmethod
    def health_check(self) -> HermesStatus: ...

    @abstractmethod
    def enqueue_task(self, payload: DelegationPayload) -> DelegationReceipt: ...

    @abstractmethod
    def get_task_result(self, task_id: str) -> DelegationResult | None: ...

    @abstractmethod
    def get_queue_status(self) -> QueueStatus: ...

    @abstractmethod
    def cancel_task(self, task_id: str) -> bool: ...


# ===========================================================================
# Mock — v0.1, sin llamadas reales
# ===========================================================================

class HermesMockAdapter(HermesAdapter):
    """
    Implementacion en memoria para v0.1.
    No hace ninguna llamada real a ningun VPS.
    Genera payloads verificables con firma HMAC.
    Simula latencia configurable.

    Incluye OfflineFallbackMode (Dead Man's Switch del chat de Gemini):
    Si Atlas Core no hace ping a Hermes durante X minutos, Hermes activa
    fallback de emergencia y notifica por Telegram que el PC local esta offline.
    En v0.1 este comportamiento se simula con el flag _offline_fallback_active.
    """

    SHADOW_TIMEOUT_MINUTES = 15   # minutos sin ping → activar sombra

    def __init__(
        self,
        simulated_latency_ms: int = 50,
        shared_secret: str = "atlas-mock-secret-v0.1",
    ) -> None:
        self._latency_ms = simulated_latency_ms
        self._secret = shared_secret.encode()
        self._queue: dict[str, DelegationPayload] = {}
        self._results: dict[str, DelegationResult] = {}
        self._lock = threading.Lock()
        self._online = False
        self._offline_fallback_active = False   # OfflineFallbackMode activo
        self._last_ping: datetime | None = None

    def health_check(self) -> HermesStatus:
        self._simulate_latency()
        return HermesStatus(
            reachable=self._online,
            mode="mock",
            queue_depth=len(self._queue),
            last_seen=datetime.now(timezone.utc).isoformat() if self._online else None,
            version="mock-0.1.0",
        )

    def enqueue_task(self, payload: DelegationPayload) -> DelegationReceipt:
        self._simulate_latency()
        signed = self._sign_payload(payload)
        with self._lock:
            self._queue[payload.id] = signed
            position = len(self._queue)
        return DelegationReceipt(
            delegation_id=payload.id,
            accepted=True,
            queue_position=position,
            estimated_eta_seconds=position * 30,
        )

    def get_task_result(self, task_id: str) -> DelegationResult | None:
        return self._results.get(task_id)

    def get_queue_status(self) -> QueueStatus:
        with self._lock:
            depth = len(self._queue)
            next_id = next(iter(self._queue), None) if self._queue else None
        return QueueStatus(
            depth=depth,
            oldest_task_age_seconds=None,
            next_task_id=next_id,
            processing=False,
        )

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            removed = self._queue.pop(task_id, None)
        return removed is not None

    def set_online(self, online: bool) -> None:
        self._online = online

    def ping(self) -> None:
        """Atlas llama a este metodo periodicamente. Reinicia el Dead Man's Switch."""
        self._last_ping = datetime.now(timezone.utc)
        self._offline_fallback_active = False

    def check_offline_fallback(self) -> bool:
        """
        Hermes comprueba si debe activar OfflineFallbackMode.
        Si no ha habido ping en SHADOW_TIMEOUT_MINUTES, activa fallback.
        """
        if self._last_ping is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._last_ping).total_seconds() / 60
        if elapsed > self.SHADOW_TIMEOUT_MINUTES:
            self._offline_fallback_active = True
        return self._offline_fallback_active

    @property
    def offline_fallback_active(self) -> bool:
        return self._offline_fallback_active

    def verify_signature(self, payload: DelegationPayload) -> bool:
        expected = self._compute_sig(payload.to_dict())
        return hmac.compare_digest(payload.signature, expected)

    # ------------------------------------------------------------------
    # Privado
    # ------------------------------------------------------------------

    def _sign_payload(self, payload: DelegationPayload) -> DelegationPayload:
        sig = self._compute_sig(payload.to_dict())
        from dataclasses import replace
        return DelegationPayload(
            task_id=payload.task_id,
            task_intent=payload.task_intent,
            priority=payload.priority,
            timeout_seconds=payload.timeout_seconds,
            callback_endpoint=payload.callback_endpoint,
            id=payload.id,
            created_at=payload.created_at,
            expires_at=payload.expires_at,
            encrypted=payload.encrypted,
            signature=sig,
            metadata=payload.metadata,
        )

    def _compute_sig(self, data: dict[str, Any]) -> str:
        # Excluir signature del calculo
        payload_data = {k: v for k, v in data.items() if k != "signature"}
        msg = json.dumps(payload_data, sort_keys=True, ensure_ascii=False).encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def _simulate_latency(self) -> None:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)


class HermesKanbanAdapter(HermesAdapter):
    """
    Adaptador real sobre Hermes Agent kanban local/remoto.

    Usa `hermes kanban` como superficie durable de delegación. Si el bridge no
    es reachable, la tarea cae a OfflineQueue y se levanta HermesUnreachable,
    igual que el adapter REST. En éxito NO duplica la tarea en OfflineQueue:
    el board de Hermes ya es la fuente durable.
    """

    DEFAULT_ASSIGNEE = "default"

    def __init__(
        self,
        bridge: KanbanBridge | None = None,
        *,
        offline_queue: "OfflineQueue | None" = None,
        assignee: str | None = None,
    ) -> None:
        self._bridge = bridge or KanbanBridge()
        self._offline_queue = offline_queue
        self._assignee = (assignee or os.environ.get("HERMES_KANBAN_ASSIGNEE") or self.DEFAULT_ASSIGNEE).strip()

    def health_check(self) -> HermesStatus:
        reachable = self._bridge.reachable()
        depth = 0
        if reachable:
            try:
                stats = self._bridge.run("stats", "--json")
                by_status = ((stats.parsed or {}).get("by_status") or {}) if isinstance(stats.parsed, dict) else {}
                depth = sum(
                    int(count) for status, count in by_status.items()
                    if status not in {"done", "archived"}
                )
            except Exception:  # noqa: BLE001
                depth = 0
        return HermesStatus(
            reachable=reachable,
            mode="kanban" if reachable else "offline",
            queue_depth=depth,
            last_seen=datetime.now(timezone.utc).isoformat() if reachable else None,
            version="hermes-kanban",
        )

    def enqueue_task(self, payload: DelegationPayload) -> DelegationReceipt:
        title = _kanban_title(payload.task_intent)
        result = self._bridge.create_task(
            title=title,
            body=payload.task_intent,
            assignee=self._assignee,
            triage=False,
        )
        if not result.ok:
            if self._offline_queue is not None:
                self._offline_queue.enqueue(QueueEntry(delegation=payload))
            raise HermesUnreachable(result.stderr or "kanban create failed")
        task_id = _extract_kanban_task_id(result.parsed)
        return DelegationReceipt(
            delegation_id=task_id or payload.id,
            accepted=True,
            queue_position=None,
            estimated_eta_seconds=None,
        )

    def get_task_result(self, task_id: str) -> DelegationResult | None:
        result = self._bridge.run("show", task_id, "--json")
        if not result.ok:
            return None
        parsed = result.parsed or {}
        task = parsed.get("task") if isinstance(parsed, dict) else None
        if not isinstance(task, dict):
            return None
        latest_summary = parsed.get("latest_summary") if isinstance(parsed, dict) else None
        return DelegationResult(
            delegation_id=task.get("id", task_id),
            task_id=task.get("id", task_id),
            status=str(task.get("status", "unknown")),
            result={"latest_summary": latest_summary, "task": task},
            completed_at=task.get("completed_at"),
            error=None,
            skill_generated=False,
        )

    def get_queue_status(self) -> QueueStatus:
        stats = self._bridge.run("stats", "--json")
        parsed = stats.parsed if isinstance(stats.parsed, dict) else {}
        by_status = parsed.get("by_status", {}) if isinstance(parsed, dict) else {}
        depth = sum(
            int(count) for status, count in by_status.items()
            if status not in {"done", "archived"}
        )
        next_task_id = None
        ready = self._bridge.run("list", "--status", "ready", "--json")
        if ready.ok and isinstance(ready.parsed, list) and ready.parsed:
            next_task_id = ready.parsed[0].get("id")
        return QueueStatus(
            depth=depth,
            oldest_task_age_seconds=parsed.get("oldest_ready_age_seconds") if isinstance(parsed, dict) else None,
            next_task_id=next_task_id,
            processing=False,
        )

    def cancel_task(self, task_id: str) -> bool:
        result = self._bridge.run("archive", task_id)
        return result.ok

    def check_offline_fallback(self) -> bool:
        return not self._bridge.reachable()


# ===========================================================================
# Constructor de DelegationPayload
# ===========================================================================

class DelegationBuilder:
    """Construye DelegationPayloads con defaults correctos."""

    @staticmethod
    def build(
        task_id: str,
        intent: str,
        priority: int,
        timeout_seconds: int = 300,
        metadata: dict[str, Any] | None = None,
    ) -> DelegationPayload:
        return DelegationPayload(
            task_id=task_id,
            task_intent=intent,
            priority=priority,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )


def _kanban_title(intent: str, limit: int = 96) -> str:
    clean = " ".join((intent or "").strip().split())
    if not clean:
        return "Atlas delegated task"
    return clean[:limit]


def _extract_kanban_task_id(parsed: Any) -> str | None:
    if isinstance(parsed, dict):
        task_id = parsed.get("id")
        if isinstance(task_id, str) and task_id:
            return task_id
    return None


# ===========================================================================
# Cola offline persistente
# ===========================================================================

@dataclass
class QueueEntry:
    delegation: DelegationPayload
    enqueued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    attempts: int = 0
    last_attempt: str | None = None
    status: str = "pending"   # "pending" | "sent" | "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "delegation": self.delegation.to_dict(),
            "enqueued_at": self.enqueued_at,
            "attempts": self.attempts,
            "last_attempt": self.last_attempt,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueEntry":
        return cls(
            delegation=DelegationPayload(**data["delegation"]),
            enqueued_at=data["enqueued_at"],
            attempts=data["attempts"],
            last_attempt=data.get("last_attempt"),
            status=data["status"],
        )


class OfflineQueue:
    """
    Cola FIFO con prioridad. Persiste entre reinicios.
    Prioridad >= 4 se procesa antes que cualquier entrada de prioridad inferior.
    Maximo 100 entradas (configurable). Las de prioridad baja se descartan si se supera.
    """

    MAX_ENTRIES = 100

    def __init__(self, store_path: Path) -> None:
        self._path = store_path / "hermes_queue.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._entries: list[QueueEntry] = self._load()

    def enqueue(self, entry: QueueEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            # Ordenar: prioridad descendente, luego FIFO por enqueued_at
            self._entries.sort(
                key=lambda e: (-e.delegation.priority, e.enqueued_at)
            )
            # Recortar si se supera el maximo
            if len(self._entries) > self.MAX_ENTRIES:
                # Descartar las de menor prioridad al final de la lista
                self._entries = self._entries[: self.MAX_ENTRIES]
            self._persist()

    def peek(self) -> QueueEntry | None:
        with self._lock:
            pending = [e for e in self._entries if e.status == "pending"]
            return pending[0] if pending else None

    def mark_sent(self, delegation_id: str) -> None:
        with self._lock:
            for entry in self._entries:
                if entry.delegation.id == delegation_id:
                    entry.status = "sent"
                    break
            self._persist()

    def mark_failed(self, delegation_id: str) -> None:
        with self._lock:
            for entry in self._entries:
                if entry.delegation.id == delegation_id:
                    entry.status = "failed"
                    entry.attempts += 1
                    entry.last_attempt = datetime.now(timezone.utc).isoformat()
                    break
            self._persist()

    def all_pending(self) -> list[QueueEntry]:
        with self._lock:
            return [e for e in self._entries if e.status == "pending"]

    @property
    def depth(self) -> int:
        with self._lock:
            return sum(1 for e in self._entries if e.status == "pending")

    def status(self) -> QueueStatus:
        with self._lock:
            pending = [e for e in self._entries if e.status == "pending"]
            return QueueStatus(
                depth=len(pending),
                oldest_task_age_seconds=None,
                next_task_id=pending[0].delegation.task_id if pending else None,
                processing=False,
            )

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _load(self) -> list[QueueEntry]:
        if not self._path.exists():
            return []
        results = []
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(QueueEntry.from_dict(json.loads(line)))
                    except Exception:
                        continue
        return results


# ===========================================================================
# REST adapter — Gate C
# ===========================================================================

class HermesError(Exception):
    """Base de todos los errores del HermesRestAdapter."""


class HermesUnreachable(HermesError):
    """Se han agotado los reintentos. La tarea queda en OfflineQueue si existe."""


class HermesAuthError(HermesError):
    """Hermes ha rechazado la firma HMAC (401/403)."""


class HermesBadResponse(HermesError):
    """El cuerpo de respuesta no encaja con el contrato esperado."""


class HermesRestAdapter(HermesAdapter):
    """
    Implementacion real sobre REST HTTPS + HMAC-SHA256 (ADR-011).

    Cada request incluye dos cabeceras:
      X-Atlas-Timestamp: unix segundos (proteccion replay)
      X-Atlas-Signature: hex(HMAC-SHA256(secret, f"{ts}\\n{body}"))

    Cliente HTTP: urllib (stdlib). Sin nuevas dependencias.
    Retry: max_retries intentos con backoff exponencial (1s, 2s, 4s, ...).
    Tras agotar reintentos en enqueue_task: la entrada va a OfflineQueue si se
    inyecto una, y se levanta HermesUnreachable. Los demas metodos no encolan.
    """

    DEFAULT_USER_AGENT = "atlas-core/0.2 (HermesRestAdapter)"

    def __init__(
        self,
        base_url: str,
        shared_secret: str,
        offline_queue: "OfflineQueue | None" = None,
        timeout_connect_s: float = 5.0,
        timeout_read_s: float = 10.0,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        user_agent: str | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not shared_secret:
            raise ValueError("shared_secret is required")
        self._base_url = base_url.rstrip("/")
        self._secret = shared_secret.encode()
        self._offline_queue = offline_queue
        self._timeout = max(timeout_connect_s, timeout_read_s)
        self._max_retries = max(1, int(max_retries))
        self._backoff_base = max(0.0, float(backoff_base_s))
        self._user_agent = user_agent or self.DEFAULT_USER_AGENT

    def health_check(self) -> HermesStatus:
        try:
            data = self._request("GET", "/health")
        except HermesError:
            return HermesStatus(reachable=False, mode="offline")
        return HermesStatus(
            reachable=bool(data.get("reachable", True)),
            mode=str(data.get("mode", "live")),
            queue_depth=int(data.get("queue_depth", 0)),
            last_seen=data.get("last_seen"),
            version=data.get("version"),
        )

    def enqueue_task(self, payload: DelegationPayload) -> DelegationReceipt:
        signed = self._sign_payload(payload)
        body = signed.to_dict()
        try:
            data = self._request("POST", "/tasks", body=body)
        except HermesUnreachable:
            if self._offline_queue is not None:
                self._offline_queue.enqueue(QueueEntry(delegation=signed))
            raise
        return DelegationReceipt(
            delegation_id=data.get("delegation_id", signed.id),
            accepted=bool(data.get("accepted", False)),
            queue_position=data.get("queue_position"),
            estimated_eta_seconds=data.get("estimated_eta_seconds"),
            error=data.get("error"),
        )

    def get_task_result(self, task_id: str) -> DelegationResult | None:
        try:
            data = self._request("GET", f"/tasks/{task_id}")
        except HermesBadResponse as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise
        return DelegationResult(
            delegation_id=data["delegation_id"],
            task_id=data["task_id"],
            status=data["status"],
            result=data.get("result"),
            error=data.get("error"),
            completed_at=data.get("completed_at"),
            skill_generated=bool(data.get("skill_generated", False)),
            skill_md=data.get("skill_md"),
        )

    def get_queue_status(self) -> QueueStatus:
        data = self._request("GET", "/queue")
        return QueueStatus(
            depth=int(data.get("depth", 0)),
            oldest_task_age_seconds=data.get("oldest_task_age_seconds"),
            next_task_id=data.get("next_task_id"),
            processing=bool(data.get("processing", False)),
        )

    def cancel_task(self, task_id: str) -> bool:
        try:
            self._request("DELETE", f"/tasks/{task_id}")
        except HermesBadResponse as exc:
            if getattr(exc, "status", None) == 404:
                return False
            raise
        return True

    def check_offline_fallback(self) -> bool:
        """
        True si Hermes no es alcanzable (proxy de Dead Man Switch para REST).
        El VPS puede activar su propia logica; aqui detectamos caida de red.
        """
        try:
            status = self.health_check()
        except HermesError:
            return True
        return not status.reachable

    def _sign_payload(self, payload: DelegationPayload) -> DelegationPayload:
        from dataclasses import replace as _replace
        sig = self._compute_payload_sig(payload.to_dict())
        return _replace(payload, signature=sig)

    def _compute_payload_sig(self, data: dict[str, Any]) -> str:
        payload_data = {k: v for k, v in data.items() if k != "signature"}
        msg = json.dumps(payload_data, sort_keys=True, ensure_ascii=False).encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        raw_body = b""
        if body is not None:
            raw_body = json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            ts = str(int(time.time()))
            sig = self._compute_request_sig(ts, raw_body)
            headers = {
                "User-Agent": self._user_agent,
                "Content-Type": "application/json",
                "X-Atlas-Timestamp": ts,
                "X-Atlas-Signature": sig,
            }
            req = urllib.request.Request(
                url=url, method=method, data=raw_body if raw_body else None, headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    return self._parse_response(resp.status, resp.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                if status in (401, 403):
                    raise HermesAuthError(f"auth rejected: HTTP {status}") from exc
                if status == 404:
                    err = HermesBadResponse(f"not found: {path}")
                    err.status = 404  # type: ignore[attr-defined]
                    raise err from exc
                if 500 <= status < 600:
                    last_exc = exc
                else:
                    err = HermesBadResponse(f"unexpected HTTP {status}")
                    err.status = status  # type: ignore[attr-defined]
                    raise err from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
                last_exc = exc

            if attempt < self._max_retries:
                time.sleep(self._backoff_base * (2 ** (attempt - 1)))

        raise HermesUnreachable(
            f"{method} {path} failed after {self._max_retries} attempts: {last_exc}"
        )

    def _compute_request_sig(self, timestamp: str, body: bytes) -> str:
        msg = timestamp.encode("utf-8") + b"\n" + body
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    @staticmethod
    def _parse_response(status: int, raw: bytes) -> dict[str, Any]:
        if status == 204 or not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            err = HermesBadResponse(f"invalid JSON body: {exc}")
            err.status = status  # type: ignore[attr-defined]
            raise err from exc
        if not isinstance(data, dict):
            err = HermesBadResponse("response body must be a JSON object")
            err.status = status  # type: ignore[attr-defined]
            raise err
        return data
