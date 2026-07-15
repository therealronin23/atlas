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
    verify_telegram_passphrase,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeOps:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.approve_kwargs: list[dict] = []
        self.status_data = {"mode": "NORMAL", "tasks_run": 7}
        self.task_response = {"status": "executed", "task_id": "t-1"}
        self.approve_response = {"task_id": "t-approve", "status": "done", "approved": True}
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

    def pending_approvals(self):
        self.calls.append(("pending_approvals", ()))
        return []

    def approve(self, task_id, approved=True, *, abort=False, approve_only=None):
        self.calls.append(("approve", (task_id, approved)))
        # ADR-033: registrar kwargs de aprobación parcial/cancelación aparte
        # para que los tests puedan inspeccionarlos sin romper aserciones viejas.
        self.approve_kwargs.append({"abort": abort, "approve_only": approve_only})
        if abort:
            return {"task_id": task_id, "status": "cancelled", "approved": False}
        return self.approve_response if approved else {
            "task_id": task_id, "status": "cancelled", "approved": False,
        }


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


def test_authorizer_merges_env_chat_id(monkeypatch: pytest.MonkeyPatch):
    class FakeProfile:
        def telegram_config(self):
            return {"authorized_chat_ids": [10]}

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    auth = TelegramAuthorizer.from_permission_profile(FakeProfile())

    assert auth.is_allowed(10) is True
    assert auth.is_allowed(42) is True


def test_authorizer_separates_group_chat_from_authorized_sender() -> None:
    auth = TelegramAuthorizer([-100123], allowed_user_ids=[42])

    assert auth.is_allowed(-100123) is True
    assert auth.is_update_allowed(-100123, 42) is True
    assert auth.is_update_allowed(-100123, 99) is False


def test_authorizer_reads_authorized_user_ids_from_profile() -> None:
    class FakeProfile:
        def telegram_config(self):
            return {
                "authorized_chat_ids": [-100123],
                "authorized_user_ids": [42],
            }

    auth = TelegramAuthorizer.from_permission_profile(FakeProfile())

    assert auth.is_update_allowed(-100123, 42) is True
    assert auth.is_update_allowed(-100123, 99) is False


def test_authorizer_accepts_permission_profile_property(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    from atlas.governance.permission_profile import PermissionProfile

    cfg = tmp_path / "permissions.yaml"
    cfg.write_text(
        "workspace:\n"
        "  auto_write:\n    - tmp/\n"
        "  confirm_write:\n    - projects/\n"
        "  read_only:\n    - config/governance.json\n"
        "  read_extended: []\n"
        "absolute_blocks:\n  - /etc/\n"
        "system_read_allowed: []\n"
        "telegram:\n  authorized_chat_ids: [77]\n"
        "shell_allowlist:\n  - echo\n"
    )
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "88")
    profile = PermissionProfile(config_path=cfg, workspace=tmp_path / "atlas")

    auth = TelegramAuthorizer.from_permission_profile(profile)

    assert auth.is_allowed(77) is True
    assert auth.is_allowed(88) is True


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


def test_bot_rejects_unauthorized_sender_inside_allowed_group() -> None:
    client = FakeClient()
    ops = FakeOps()
    auth = TelegramAuthorizer([-100123], allowed_user_ids=[42])
    bot = TelegramBot(client=client, authorizer=auth, ops=ops)

    bot.handle_update({
        "update_id": 1,
        "message": {
            "chat": {"id": -100123, "type": "group"},
            "from": {"id": 99},
            "text": "/status",
        },
    })

    assert ops.calls == []
    assert client.sent and "denegado" in client.sent[0][1].lower()


def test_bot_accepts_authorized_sender_inside_allowed_group() -> None:
    client = FakeClient()
    ops = FakeOps()
    auth = TelegramAuthorizer([-100123], allowed_user_ids=[42])
    bot = TelegramBot(client=client, authorizer=auth, ops=ops)

    bot.handle_update({
        "update_id": 1,
        "message": {
            "chat": {"id": -100123, "type": "group"},
            "from": {"id": 42},
            "text": "/status",
        },
    })

    assert ("status", ()) in ops.calls


def test_callback_rejects_unauthorized_sender_inside_allowed_group() -> None:
    client = FakeClient()
    ops = FakeOps()
    auth = TelegramAuthorizer([-100123], allowed_user_ids=[42])
    bot = TelegramBot(client=client, authorizer=auth, ops=ops)

    bot.handle_update({
        "callback_query": {
            "id": "cb-group",
            "from": {"id": 99},
            "message": {"chat": {"id": -100123, "type": "group"}},
            "data": "approve:task-99:yes",
        }
    })

    assert not any(call[0] == "approve" for call in ops.calls)


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


def test_verify_telegram_passphrase():
    import hashlib

    phrase = "atlas-secret"
    expected = hashlib.sha256(f"atlas-telegram-approve:{phrase}".encode()).hexdigest()
    assert verify_telegram_passphrase(phrase, expected) is True
    assert verify_telegram_passphrase("wrong", expected) is False


def test_callback_approve_blocked_when_passphrase_required():
    bot, client, ops = _make_bot()
    bot._telegram_cfg = {
        "require_passphrase_for_approve": True,
        "passphrase_hash": "abc",
    }
    callback = {
        "id": "cb1",
        "from": {"id": 42},
        "message": {"chat": {"id": 42}},
        "data": "approve:task-99:yes",
    }
    bot.handle_update({"callback_query": callback})
    assert ("approve", ("task-99", True)) not in ops.calls
    assert any("passphrase" in text.lower() for _, text in client.sent)


def test_cmd_approve_with_passphrase():
    import hashlib

    phrase = "gate-g"
    expected = hashlib.sha256(f"atlas-telegram-approve:{phrase}".encode()).hexdigest()
    bot, client, ops = _make_bot()
    bot._telegram_cfg = {
        "require_passphrase_for_approve": True,
        "passphrase_hash": expected,
    }
    bot.handle_update(_msg(42, "/approve t-approve gate-g"))
    assert ("approve", ("t-approve", True)) in ops.calls


# ---------------------------------------------------------------------------
# on_cold_update_batch_ready — notificación proactiva de lote de self_audit
# ---------------------------------------------------------------------------

class _FakeEvent:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


def test_on_cold_update_batch_ready_notifies_with_key_data():
    bot, client, ops = _make_bot()
    event = _FakeEvent({
        "batch_id": "batch-1",
        "included": ["cu-1", "cu-2"],
        "included_intents": ["bump uvicorn", "fix lint"],
        "excluded": [{"proposal_id": "cu-3", "reason": "rompe algo"}],
        "tests_passed": True,
        "pytest_summary": "1 passed",
    })

    bot.on_cold_update_batch_ready(event)

    assert len(client.sent) == 1
    _, text = client.sent[0]
    assert "batch-1" in text
    assert "2" in text  # incluidos
    assert "1" in text  # excluidos
    assert "bump uvicorn" in text
    assert "fix lint" in text


def test_on_cold_update_batch_ready_handles_missing_fields():
    bot, client, ops = _make_bot()
    event = _FakeEvent({})

    bot.on_cold_update_batch_ready(event)

    assert len(client.sent) == 1
    _, text = client.sent[0]
    assert "?" in text
