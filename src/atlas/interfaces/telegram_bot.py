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

import hashlib
import hmac
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

    def status(self) -> dict[str, Any]: ...
    def submit_task(self, intent: str) -> dict[str, Any]: ...
    def recent_audit(self, n: int = 10) -> list[dict[str, Any]]: ...
    def list_tools(self) -> list[dict[str, Any]]: ...
    def triage(self) -> dict[str, Any]: ...
    def pending_approvals(self) -> list[dict[str, Any]]: ...
    def approve(
        self,
        task_id: str,
        approved: bool,
        *,
        abort: bool = False,
        approve_only: list[str] | None = None,
    ) -> dict[str, Any]: ...


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
        raw_cfg = profile.telegram_config
        cfg = raw_cfg() if callable(raw_cfg) else raw_cfg
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


def verify_telegram_passphrase(
    passphrase: str,
    expected_hash: str,
    *,
    salt: str = "atlas-telegram-approve",
) -> bool:
    """Compara passphrase con hash SHA-256 almacenado en permissions.yaml."""
    if not expected_hash:
        return False
    supplied = hashlib.sha256(f"{salt}:{passphrase}".encode()).hexdigest()
    return hmac.compare_digest(supplied, expected_hash)


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

    def get_updates(self, offset: int | None = None, timeout_s: int = 25) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout_s}
        if offset is not None:
            params["offset"] = offset
        data = self._call("getUpdates", params=params)
        result = data.get("result", [])
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            body["reply_markup"] = reply_markup
        return self._call("sendMessage", body=body)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> dict[str, Any]:
        return self._call("answerCallbackQuery", body={
            "callback_query_id": callback_query_id, "text": text,
        })

    def _call(
        self, method: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
                payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
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
        *,
        telegram_config: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._auth = authorizer
        self._ops = ops
        self._merkle = merkle
        self._telegram_cfg = telegram_config or {}
        self._offset: int | None = None
        self._running = False
        self._handlers = {
            "/status": self._cmd_status,
            "/task": self._cmd_task,
            "/audit": self._cmd_audit,
            "/tools": self._cmd_tools,
            "/triage": self._cmd_triage,
            "/pending": self._cmd_pending,
            "/approve": self._cmd_approve,
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

    def handle_update(self, update: dict[str, Any]) -> None:
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

        # Slash commands take priority; otherwise treat the whole message
        # as a natural-language intent and route it through the task pipeline.
        if text.startswith("/"):
            command, _, arg = text.partition(" ")
            handler = self._handlers.get(command.lower())
            if handler is None:
                self._safe_send(
                    chat_id,
                    f"Comando no reconocido: {command}\n"
                    "Comandos: " + ", ".join(sorted(self._handlers.keys())) +
                    "\nO escribe directamente sin /.",
                )
                return
            try:
                reply = handler(arg.strip())
            except Exception as exc:
                reply = f"Error ejecutando {command}: {exc}"
        else:
            # Natural-language intent → submit as task
            try:
                reply = self._cmd_task(text)
            except Exception as exc:
                reply = f"Error procesando intent: {exc}"
        self._safe_send(chat_id, reply)

    def _handle_callback(self, callback: dict[str, Any]) -> None:
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
        # Formatos: <pfx>:<id>:yes | :no | :abort | :only:<tc_id>  (ADR-033)
        if len(parts) < 3 or parts[0] != self.CALLBACK_PREFIX:
            try:
                self._client.answer_callback_query(cb_id, "callback malformado")
            except TelegramAPIError:
                pass
            return

        task_id, decision = parts[1], parts[2]
        only_id = parts[3] if decision == "only" and len(parts) >= 4 else None
        if decision == "only" and not only_id:
            try:
                self._client.answer_callback_query(cb_id, "callback malformado")
            except TelegramAPIError:
                pass
            return

        approved = decision in ("yes", "only")
        abort = decision == "abort"
        if approved and self._passphrase_required():
            try:
                self._client.answer_callback_query(
                    cb_id,
                    "Usa /approve <task_id> <passphrase>",
                )
            except TelegramAPIError:
                pass
            self._safe_send(
                int(chat_id),
                f"Aprobacion de {task_id} requiere passphrase. "
                "Uso: /approve <task_id> <passphrase>",
            )
            return
        try:
            result = self._ops.approve(
                task_id, approved, abort=abort,
                approve_only=[only_id] if only_id else None,
            )
        except Exception as exc:
            try:
                self._client.answer_callback_query(cb_id, f"error: {exc}")
            except TelegramAPIError:
                pass
            return

        if only_id:
            text = f"Aprobada solo {only_id} (task_id={task_id})."
        elif approved:
            text = f"Aprobada (task_id={task_id})."
        elif abort:
            text = f"Cancelada (task_id={task_id})."
        else:
            text = f"Rechazada (task_id={task_id})."
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

    def notify_all(self, text: str, reply_markup: dict[str, Any] | None = None) -> int:
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
        if self._passphrase_required():
            text += (
                "\n\nPassphrase requerida: usa /approve <task_id> <passphrase> "
                "(los botones inline estan deshabilitados para aprobar)."
            )
            self.notify_all(text)
        else:
            self.notify_all(text, reply_markup=self._approval_keyboard(task_id, p))

    def _approval_keyboard(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Teclado inline de aprobación. Para loops agénticos con >1 mutación
        (ADR-033) añade una fila por mutación ('Solo <name>' → approve_only) y
        un 'Cancelar' (deny+abort). callback_data se mantiene <64 bytes."""
        rows = [[
            {"text": "Si", "callback_data": f"{self.CALLBACK_PREFIX}:{task_id}:yes"},
            {"text": "No", "callback_data": f"{self.CALLBACK_PREFIX}:{task_id}:no"},
        ]]
        muts = payload.get("pending_mutations") or []
        if len(muts) > 1:
            for m in muts:
                mid = str(m.get("id") or "")
                cb = f"{self.CALLBACK_PREFIX}:{task_id}:only:{mid}"
                if mid and len(cb.encode("utf-8")) <= 64:
                    rows.append([{
                        "text": f"Solo {m.get('name', mid)}",
                        "callback_data": cb,
                    }])
            rows.append([{
                "text": "Cancelar (abort)",
                "callback_data": f"{self.CALLBACK_PREFIX}:{task_id}:abort",
            }])
        return {"inline_keyboard": rows}

    def on_agentic_progress(self, event: Any) -> None:
        """ADR-033 #4: traza de progreso del loop agéntico. OPT-IN: silencioso
        salvo `ATLAS_TELEGRAM_PROGRESS=1` o `telegram.progress_updates: true`
        en governance, para no inundar el chat en cada iteración."""
        if not self._progress_enabled():
            return
        p = getattr(event, "payload", {}) or {}
        tool = p.get("tool", "?")
        it = p.get("iteration", "?")
        summary = str(p.get("summary", "") or "")[:160]
        self.notify_all(
            f"[Progreso] task {p.get('task_id','?')} · iter {it} · {tool}\n{summary}"
        )

    def _progress_enabled(self) -> bool:
        if os.environ.get("ATLAS_TELEGRAM_PROGRESS", "") == "1":
            return True
        return bool(self._telegram_cfg.get("progress_updates"))

    def on_cold_update_batch_ready(self, event: Any) -> None:
        p = getattr(event, "payload", {}) or {}
        n = len(p.get("included", []))
        excluded_n = len(p.get("excluded", []))
        tests = "OK" if p.get("tests_passed") else "FALLÓ"
        intents = ", ".join(p.get("included_intents", [])[:5])
        text = (
            f"[ColdUpdate] Lote listo para revisión: {n} cambios incluidos, "
            f"{excluded_n} excluidos. Tests: {tests}.\n"
            f"Cambios: {intents}\n"
            f"ID lote: {p.get('batch_id', '?')}\n"
            f"Revisa con: atlas update batch-review"
        )
        self.notify_all(text)

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
            line = (f"  {it.get('task_id','?')} — {it.get('intent','')}"
                    f" ({it.get('reason','')})")
            muts = it.get("pending_mutations") or []
            if muts:
                names = ", ".join(f"{m.get('id')}:{m.get('name')}" for m in muts)
                line += f"\n    mutaciones: {names}"
            out.append(line)
        return "\n".join(out)

    def _cmd_approve(self, arg: str) -> str:
        parts = arg.split(maxsplit=1)
        if len(parts) < 2:
            return "Uso: /approve <task_id> <passphrase>"
        task_id, passphrase = parts[0].strip(), parts[1].strip()
        if self._passphrase_required() and not self._verify_passphrase(passphrase):
            return "Passphrase incorrecta."
        try:
            result = self._ops.approve(task_id, True)
        except Exception as exc:
            return f"Error aprobando {task_id}: {exc}"
        if result.get("status") == "unknown":
            return f"No habia approval pendiente para {task_id}."
        return f"Aprobada (task_id={task_id}, status={result.get('status', '?')})."

    def _passphrase_required(self) -> bool:
        return bool(self._telegram_cfg.get("require_passphrase_for_approve"))

    def _verify_passphrase(self, passphrase: str) -> bool:
        expected = str(self._telegram_cfg.get("passphrase_hash") or "")
        return verify_telegram_passphrase(passphrase, expected)

    # ------------------------------------------------------------------
    # Formateo
    # ------------------------------------------------------------------

    @staticmethod
    def _format_status(data: dict[str, Any]) -> str:
        lines = ["Atlas Core — status"]
        for k, v in data.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    @staticmethod
    def _format_task_submission(data: dict[str, Any]) -> str:
        status = data.get("status", "submitted")
        if status == "delegated":
            return f"Delegado a Hermes (id={data.get('delegation_id', '?')})."
        if status == "requires_approval":
            return f"Requiere aprobacion (task_id={data.get('task_id', '?')})."

        # Error path
        if data.get("error"):
            return f"❌ Error: {data['error']}"

        result = data.get("result")

        # No result payload — fall back to the old summary line
        if result is None:
            return f"Tarea aceptada: status={status} id={data.get('task_id', '?')}"

        # String result (rare)
        if isinstance(result, str):
            return result[:3500]

        # LLM response (LOCAL_SAFE pipeline)
        if isinstance(result, dict):
            text = result.get("text") or result.get("response") or result.get("answer")
            if text:
                meta = []
                if result.get("model"): meta.append(result["model"])
                if result.get("tokens"): meta.append(f"{result['tokens']}t")
                if result.get("latency_ms"): meta.append(f"{result['latency_ms']}ms")
                suffix = f"\n\n— {' · '.join(meta)}" if meta else ""
                return str(text)[:3500] + suffix

            # Command / exec output
            stdout = result.get("stdout")
            if stdout is not None:
                rc = result.get("returncode", "?")
                body = (stdout or "(sin salida)").rstrip()
                stderr = (result.get("stderr") or "").strip()
                tail = f"\n\nstderr:\n{stderr[:500]}" if stderr else ""
                return f"$ rc={rc}\n{body[:3000]}{tail}"

            # Generic dict fallback: compact pretty-print
            import json as _json
            return f"```\n{_json.dumps(result, ensure_ascii=False, indent=2)[:3500]}\n```"

        # Anything else
        return str(result)[:3500]

    @staticmethod
    def _format_audit(entries: list[dict[str, Any]]) -> str:
        out = [f"Ultimas {len(entries)} entradas:"]
        for e in entries:
            ts = e.get("timestamp", "")
            agent = e.get("agent", "")
            action = e.get("action", "")
            result = e.get("result", "")
            out.append(f"  {ts} [{agent}] {action} -> {result}")
        return "\n".join(out)

    @staticmethod
    def _format_tools(tools: list[dict[str, Any]]) -> str:
        out = [f"Herramientas ({len(tools)}):"]
        for t in tools:
            name = t.get("name", "?")
            desc = t.get("description", "")
            out.append(f"  - {name}: {desc}")
        return "\n".join(out)

    @staticmethod
    def _format_triage(data: dict[str, Any]) -> str:
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
