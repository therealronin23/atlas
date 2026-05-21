"""
Tests para src/atlas/interfaces/telegram_bot.py — Gate C / C4.
Sin red real: el cliente de Telegram se mockea, y AtlasOps es un stub.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from atlas.interfaces.telegram_bot import (
    TelegramAPIError,
    TelegramAuthorizer,
    TelegramBot,
    TelegramClient,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeOps:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.status_data = {"mode": "NORMAL", "tasks_run": 7}
        self.task_response = {"status": "executed", "task_id": "t-1"}
        self.audit_entries = [
            {"timestamp": "2026-01-01T00:00:00Z", "agent": "cli",
             "action": "task.run", "result": "ok"},
        ]
        self.tools_list = [{"name": "shell.echo", "description": "echo a string"}]
        self.triage_data = {"mode": "NORMAL", "temperature_c": 55.0, "ram_free_mb": 4096}

    def status(self):
        self.calls.append(("status", ()))
        return self.status_data

    def submit_task(self, intent):
        self.calls.append(("submit_task", (intent,)))
        return self.task_response

    def recent_audit(self, n=10):
        self.calls.append(("recent_audit", (n,)))
        return self.audit_entries

    def list_tools(self):
        self.calls.append(("list_tools", ()))
        return self.tools_list

    def triage(self):
        self.calls.append(("triage", ()))
        return self.triage_data


class FakeClient:
    """Implementa la firma de TelegramClient sin hacer red."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.send_fail = False

    def send_message(self, chat_id, text, reply_markup=None):
        if self.send_fail:
            raise TelegramAPIError("simulated")
        self.sent.append((int(chat_id), text))
        return {"ok": True}

    def get_updates(self, offset=None, timeout_s=25):
        return []

    def answer_callback_query(self, callback_query_id, text=""):
        return {"ok": True}


def _make_bot(authorized_chat_ids=(42,), merkle=None) -> tuple[TelegramBot, FakeClient, FakeOps]:
    client = FakeClient()
    ops = FakeOps()
    auth = TelegramAuthorizer(list(authorized_chat_ids))
    return TelegramBot(client=client, authorizer=auth, ops=ops, merkle=merkle), client, ops


def _msg(chat_id: int, text: str, update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id}, "text": text},
    }


# ---------------------------------------------------------------------------
# Authorizer
# ---------------------------------------------------------------------------

def test_authorizer_allows_and_denies():
    auth = TelegramAuthorizer([1, 2, 3])
    assert auth.is_allowed(2) is True
    assert auth.is_allowed(99) is False


def test_authorizer_from_permission_profile():
    class FakeProfile:
        def telegram_config(self):
            return {"authorized_chat_ids": [10, 20]}
    auth = TelegramAuthorizer.from_permission_profile(FakeProfile())
    assert auth.is_allowed(10) is True
    assert auth.is_allowed(20) is True
    assert auth.is_allowed(30) is False


# ---------------------------------------------------------------------------
# Cliente: serializacion y errores
# ---------------------------------------------------------------------------

def test_client_constructor_requires_token():
    with pytest.raises(ValueError):
        TelegramClient(token="")


def test_client_send_message_builds_post_with_json_body():
    client = TelegramClient(token="ABC")

    captured = {}

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["data"] = req.data
        return FakeResp(json.dumps({"ok": True, "result": {}}).encode())

    with patch("atlas.interfaces.telegram_bot.urllib.request.urlopen", side_effect=fake_urlopen):
        client.send_message(chat_id=7, text="hola")

    assert captured["method"] == "POST"
    assert "sendMessage" in captured["url"]
    body = json.loads(captured["data"].decode())
    assert body == {"chat_id": 7, "text": "hola"}


def test_client_raises_on_telegram_error():
    client = TelegramClient(token="ABC")

    class FakeResp:
        def read(self):
            return json.dumps({"ok": False, "description": "bad chat"}).encode()
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass

    with patch(
        "atlas.interfaces.telegram_bot.urllib.request.urlopen",
        return_value=FakeResp(),
    ):
        with pytest.raises(TelegramAPIError):
            client.send_message(chat_id=7, text="x")


# ---------------------------------------------------------------------------
# Bot dispatcher
# ---------------------------------------------------------------------------

def test_bot_dispatches_status_command():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/status"))
    assert ("status", ()) in ops.calls
    assert client.sent and "status" in client.sent[0][1].lower()


def test_bot_dispatches_task_with_intent():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/task escribir README"))
    assert ("submit_task", ("escribir README",)) in ops.calls
    assert "executed" in client.sent[0][1] or "t-1" in client.sent[0][1]


def test_bot_task_without_intent_returns_usage():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/task"))
    assert ops.calls == []
    assert "Uso" in client.sent[0][1] or "uso" in client.sent[0][1]


def test_bot_dispatches_audit_with_count():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/audit 5"))
    assert ("recent_audit", (5,)) in ops.calls


def test_bot_audit_clamps_invalid_count():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/audit abc"))
    assert ("recent_audit", (10,)) in ops.calls
    bot.handle_update(_msg(42, "/audit 9999", update_id=2))
    assert ("recent_audit", (100,)) in ops.calls


def test_bot_dispatches_tools():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/tools"))
    assert ("list_tools", ()) in ops.calls
    assert "shell.echo" in client.sent[0][1]


def test_bot_dispatches_triage():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/triage"))
    assert ("triage", ()) in ops.calls
    assert "NORMAL" in client.sent[0][1]


def test_bot_rejects_unauthorized_and_logs_merkle():
    class FakeMerkle:
        def __init__(self):
            self.entries: list[dict] = []
        def log(self, **kw):
            self.entries.append(kw)
            return None

    merkle = FakeMerkle()
    bot, client, ops = _make_bot(authorized_chat_ids=(42,), merkle=merkle)
    bot.handle_update(_msg(99, "/status"))
    assert ops.calls == []
    assert client.sent and "denegado" in client.sent[0][1].lower()
    assert len(merkle.entries) == 1
    assert merkle.entries[0]["action"] == "telegram.unauthorized"
    assert merkle.entries[0]["payload"]["chat_id"] == 99


def test_bot_unknown_command_returns_message():
    bot, client, ops = _make_bot()
    bot.handle_update(_msg(42, "/banana"))
    assert ops.calls == []
    assert "no reconocido" in client.sent[0][1].lower()


def test_bot_handles_malformed_update_silently():
    bot, client, ops = _make_bot()
    bot.handle_update({})
    bot.handle_update({"message": "not a dict"})
    bot.handle_update({"message": {"chat": {}, "text": ""}})
    assert ops.calls == []
    assert client.sent == []


def test_bot_swallows_handler_exceptions():
    bot, client, ops = _make_bot()
    def raises(_):
        raise RuntimeError("boom")
    ops.submit_task = raises  # type: ignore[assignment]
    bot.handle_update(_msg(42, "/task hacer X"))
    assert "Error" in client.sent[0][1]
