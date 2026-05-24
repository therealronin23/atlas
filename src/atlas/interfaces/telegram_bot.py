"""
Atlas Core — Telegram bot (Gate C / C4).

Esqueleto sin dependencias externas (urllib stdlib). Implementa:
  - TelegramClient: getUpdates / sendMessage / answerCallbackQuery
  - TelegramAuthorizer: whitelist chat_id (ADR-013)
  - AtlasOps: protocolo que el Orchestrator implementara en C4-sesion2
  - TelegramBot: dispatcher de /status, /task, /audit, /tools, /triage

La integracion real con Orchestrator y el flujo de approval con botones inline
se completan en una sesion posterior. Aqui se define la frontera limpia para
poder testear ambos lados por separado.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol


# ===========================================================================
# Protocolo que el Orchestrator implementara
# ===========================================================================

class AtlasOps(Protocol):
    """Operaciones que el bot necesita exponer. Implementadas por Orchestrator."""

    def status(self) -> dict: ...
    def submit_task(self, intent: str) -> dict: ...
    def recent_audit(self, n: int = 10) -> list[dict]: ...
    def list_tools(self) -> list[dict]: ...
    def triage(self) -> dict: ...
    def pending_approvals(self) -> list[dict]: ...
    def approve(self, task_id: str, approved: bool) -> dict: ...


# ===========================================================================
# Authorizer
# ===========================================================================

class TelegramAuthorizer:
    """
    Whitelist de chat_ids autorizados (ADR-013).
    Construible desde una lista directa o desde PermissionProfile.telegram_config().
    """

    def __init__(self, allowed_chat_ids: list[int]) -> None:
        self._allowed = {int(cid) for cid in allowed_chat_ids}

    @classmethod
    def from_permission_profile(cls, profile: Any) -> "TelegramAuthorizer":
        cfg = profile.telegram_config()
        ids = list(cfg.get("authorized_chat_ids") or [])
        env_ids = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_IDS")
        if env_ids:
            for raw in env_ids.replace(";", ",").split(","):
                raw = raw.strip()
                if raw:
                    ids.append(int(raw))
        return cls(ids)

    def is_allowed(self, chat_id: int) -> bool:
        return int(chat_id) in self._allowed

    def allowed_ids(self) -> list[int]:
        return sorted(self._allowed)


# ===========================================================================
# Cliente HTTP minimo sobre la Bot API
# ===========================================================================

class TelegramAPIError(Exception):
    pass


class TelegramClient:
    """
    Wrapper fino sobre https://api.telegram.org/bot<TOKEN>/<method>.
    Soporta llamadas GET (params) y POST (json body).
    """

    BASE = "https://api.telegram.org"

    def __init__(self, token: str, timeout_s: float = 30.0) -> None:
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self._token = token
        self._timeout = timeout_s

    def get_updates(self, offset: int | None = None, timeout_s: int = 25) -> list[dict]:
        params: dict[str, Any] = {"timeout": timeout_s}
        if offset is not None:
            params["offset"] = offset
        data = self._call("getUpdates", params=params)
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        body: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            body["reply_markup"] = reply_markup
        return self._call("sendMessage", body=body)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> dict:
        return self._call("answerCallbackQuery", body={
            "callback_query_id": callback_query_id, "text": text,
        })

    def _call(
        self, method: str, params: dict | None = None, body: dict | None = None,
    ) -> dict:
        url = f"{self.BASE}/bot{self._token}/{method}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        raw_body: bytes | None = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            raw_body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url=url, data=raw_body, headers=headers,
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TelegramAPIError(f"transport error: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TelegramAPIError(f"non-JSON body: {exc}") from exc
        if not payload.get("ok"):
            raise TelegramAPIError(
                f"telegram error: {payload.get('description', 'unknown')}"
            )
        return payload


# ===========================================================================
# Bot — dispatcher de comandos
# ===========================================================================

class TelegramBot:
    """
    Loop de polling y dispatcher de comandos. Sin estado en disco.

    Comandos:
      /status              estado completo de Atlas
      /task <intent>       enviar tarea al Orchestrator
      /audit [n]           ultimas N entradas del Merkle Logger (default 10)
      /tools               lista de herramientas registradas
      /triage              OperationalMode + temperatura + RAM
      /pending             lista approvals pendientes
    """

    AGENT = "telegram_bot"
    CALLBACK_PREFIX = "approve"

    def __init__(
        self,
        client: TelegramClient,
        authorizer: TelegramAuthorizer,
        ops: AtlasOps,
        merkle: Any = None,
    ) -> None:
        self._client = client
        self._auth = authorizer
        self._ops = ops
        self._merkle = merkle
        self._offset: int | None = None
        self._running = False
        self._handlers = {
            "/status": self._cmd_status,
            "/task": self._cmd_task,
            "/audit": self._cmd_audit,
            "/tools": self._cmd_tools,
            "/triage": self._cmd_triage,
            "/pending": self._cmd_pending,
        }

    def run_polling(self, poll_interval_s: float = 0.0) -> None:
        """Loop bloqueante. Detener con stop()."""
        self._running = True
        while self._running:
            try:
                updates = self._client.get_updates(offset=self._offset)
            except TelegramAPIError:
                time.sleep(max(poll_interval_s, 1.0))
                continue
            for update in updates:
                self._offset = int(update.get("update_id", 0)) + 1
                try:
                    self.handle_update(update)
                except Exception:
                    continue
            if poll_interval_s:
                time.sleep(poll_interval_s)

    def stop(self) -> None:
        self._running = False

    def handle_update(self, update: dict) -> None:
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            self._handle_callback(callback)
            return

        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None or not text:
            return

        if not self._auth.is_allowed(int(chat_id)):
            self._log_unauthorized(chat_id, text)
            self._safe_send(chat_id, "Acceso denegado.")
            return

        command, _, arg = text.partition(" ")
        handler = self._handlers.get(command.lower())
        if handler is None:
            self._safe_send(chat_id, f"Comando no reconocido: {command}")
            return
        try:
            reply = handler(arg.strip())
        except Exception as exc:
            reply = f"Error ejecutando {command}: {exc}"
        self._safe_send(chat_id, reply)

    def _handle_callback(self, callback: dict) -> None:
        cb_id = callback.get("id", "")
        from_user = callback.get("from") or {}
        chat = (callback.get("message") or {}).get("chat") or {}
        chat_id = chat.get("id") or from_user.get("id")
        data = callback.get("data") or ""

        if chat_id is None or not self._auth.is_allowed(int(chat_id)):
            self._log_unauthorized(chat_id or 0, f"callback:{data}")
            try:
                self._client.answer_callback_query(cb_id, "denegado")
            except TelegramAPIError:
                pass
            return

        parts = data.split(":")
        if len(parts) != 3 or parts[0] != self.CALLBACK_PREFIX:
            try:
                self._client.answer_callback_query(cb_id, "callback malformado")
            except TelegramAPIError:
                pass
            return

        task_id, decision = parts[1], parts[2]
        approved = decision == "yes"
        try:
            result = self._ops.approve(task_id, approved)
        except Exception as exc:
            try:
                self._client.answer_callback_query(cb_id, f"error: {exc}")
            except TelegramAPIError:
                pass
            return

        text = (
            f"Aprobada (task_id={task_id})." if approved
            else f"Rechazada (task_id={task_id})."
        )
        try:
            self._client.answer_callback_query(cb_id, text)
        except TelegramAPIError:
            pass
        if result.get("status") == "unknown":
            text = f"No habia approval pendiente para {task_id}."
        self._safe_send(int(chat_id), text)

    # ------------------------------------------------------------------
    # Notificaciones (subscriptores del EventBus)
    # ------------------------------------------------------------------

    def notify_all(self, text: str, reply_markup: dict | None = None) -> int:
        """Envia 'text' a todos los chat_ids autorizados. Retorna cuantos OK."""
        ok = 0
        for chat_id in self._auth.allowed_ids():
            try:
                self._client.send_message(chat_id, text, reply_markup=reply_markup)
                ok += 1
            except TelegramAPIError:
                continue
        return ok

    def on_thermal_alert(self, event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        self.notify_all(
            f"[Thermal] mode={p.get('mode','?')} temp={p.get('temperature_c','?')}C "
            f"ram_free={p.get('ram_free_mb','?')}MB — {p.get('policy','')}"
        )

    def on_shadow_alert(self, event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        self.notify_all(
            f"[Shadow] Hermes no recibe ping de Atlas desde "
            f"{p.get('elapsed_minutes','?')}min. Activado OfflineFallbackMode."
        )

    def on_approval_required(self, event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        task_id = p.get("task_id", "?")
        intent = p.get("intent", "")
        reason = p.get("reason", "")
        text = f"Approval requerido\nIntent: {intent}\nMotivo: {reason}\nID: {task_id}"
        markup = {
            "inline_keyboard": [[
                {"text": "Si", "callback_data": f"{self.CALLBACK_PREFIX}:{task_id}:yes"},
                {"text": "No", "callback_data": f"{self.CALLBACK_PREFIX}:{task_id}:no"},
            ]]
        }
        self.notify_all(text, reply_markup=markup)

    def on_session_started(self, event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        version = p.get("version", "?")
        pending = p.get("queued_tasks", 0)
        self.notify_all(
            f"Atlas Core v{version} online — {pending} tareas pendientes en cola."
        )

    # ------------------------------------------------------------------
    # Handlers de comandos
    # ------------------------------------------------------------------

    def _cmd_status(self, _arg: str) -> str:
        data = self._ops.status()
        return self._format_status(data)

    def _cmd_task(self, arg: str) -> str:
        if not arg:
            return "Uso: /task <intent>"
        data = self._ops.submit_task(arg)
        return self._format_task_submission(data)

    def _cmd_audit(self, arg: str) -> str:
        n = self._parse_int(arg, default=10, lo=1, hi=100)
        entries = self._ops.recent_audit(n)
        if not entries:
            return "Sin entradas en el log."
        return self._format_audit(entries)

    def _cmd_tools(self, _arg: str) -> str:
        tools = self._ops.list_tools()
        if not tools:
            return "Sin herramientas registradas."
        return self._format_tools(tools)

    def _cmd_triage(self, _arg: str) -> str:
        data = self._ops.triage()
        return self._format_triage(data)

    def _cmd_pending(self, _arg: str) -> str:
        items = self._ops.pending_approvals()
        if not items:
            return "Sin approvals pendientes."
        out = [f"Approvals pendientes ({len(items)}):"]
        for it in items:
            out.append(f"  {it.get('task_id','?')} — {it.get('intent','')}"
                       f" ({it.get('reason','')})")
        return "\n".join(out)

    # ------------------------------------------------------------------
    # Formateo
    # ------------------------------------------------------------------

    @staticmethod
    def _format_status(data: dict) -> str:
        lines = ["Atlas Core — status"]
        for k, v in data.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    @staticmethod
    def _format_task_submission(data: dict) -> str:
        status = data.get("status", "submitted")
        if status == "delegated":
            return f"Delegado a Hermes (id={data.get('delegation_id', '?')})."
        if status == "requires_approval":
            return f"Requiere aprobacion (task_id={data.get('task_id', '?')})."
        return f"Tarea aceptada: status={status} id={data.get('task_id', '?')}"

    @staticmethod
    def _format_audit(entries: list[dict]) -> str:
        out = [f"Ultimas {len(entries)} entradas:"]
        for e in entries:
            ts = e.get("timestamp", "")
            agent = e.get("agent", "")
            action = e.get("action", "")
            result = e.get("result", "")
            out.append(f"  {ts} [{agent}] {action} -> {result}")
        return "\n".join(out)

    @staticmethod
    def _format_tools(tools: list[dict]) -> str:
        out = [f"Herramientas ({len(tools)}):"]
        for t in tools:
            name = t.get("name", "?")
            desc = t.get("description", "")
            out.append(f"  - {name}: {desc}")
        return "\n".join(out)

    @staticmethod
    def _format_triage(data: dict) -> str:
        mode = data.get("mode", "?")
        temp = data.get("temperature_c", "?")
        ram = data.get("ram_free_mb", "?")
        return f"mode={mode}  temp={temp}C  ram_free={ram}MB"

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_int(arg: str, default: int, lo: int, hi: int) -> int:
        if not arg:
            return default
        try:
            n = int(arg)
        except ValueError:
            return default
        return max(lo, min(hi, n))

    def _safe_send(self, chat_id: int, text: str) -> None:
        try:
            self._client.send_message(chat_id, text)
        except TelegramAPIError:
            pass

    def _log_unauthorized(self, chat_id: int, text: str) -> None:
        if self._merkle is None:
            return
        try:
            self._merkle.log(
                action="telegram.unauthorized",
                agent=self.AGENT,
                result="rejected",
                risk_level="medium",
                payload={"chat_id": int(chat_id), "preview": text[:64]},
            )
        except Exception:
            pass
