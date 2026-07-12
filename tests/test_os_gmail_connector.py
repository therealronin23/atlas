"""GmailReadOnlyConnector — primer conector real (ADR-065). Sin red real:
`urllib.request.urlopen` va mockeado en todos los tests."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from typing import Any
from unittest.mock import MagicMock

import pytest

from atlas.fabric.connectors.gmail import GmailReadOnlyConnector

TOKEN_VAR = "GMAIL_OAUTH_TOKEN"
SECRET_TOKEN = "ya29.super-secret-oauth-token-value-should-never-leak"


def test_list_messages_without_token_blocks_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TOKEN_VAR, raising=False)
    urlopen_mock = MagicMock()
    monkeypatch.setattr(urllib.request, "urlopen", urlopen_mock)

    connector = GmailReadOnlyConnector(token_env_var=TOKEN_VAR)
    result = connector.list_messages()

    assert result["ok"] is False
    assert result["status"] == "BLOCKED_BY_MISSING_DEPENDENCY"
    assert result["real"] is False
    urlopen_mock.assert_not_called()


def test_list_messages_with_token_hits_real_api_with_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_VAR, SECRET_TOKEN)

    fake_body = {"messages": [{"id": "m1"}, {"id": "m2"}], "resultSizeEstimate": 2}
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(fake_body).encode("utf-8")

    captured_request: dict[str, Any] = {}

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> Any:
        captured_request["request"] = request
        captured_request["timeout"] = timeout
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    connector = GmailReadOnlyConnector(token_env_var=TOKEN_VAR)
    result = connector.list_messages(query="is:unread", max_results=5)

    assert result["ok"] is True
    assert result["real"] is True
    assert result["provenance"] == "gmail_api_readonly"
    assert result["count"] == 2
    assert result["messages"] == fake_body["messages"]

    sent_request = captured_request["request"]
    assert sent_request.get_header("Authorization") == f"Bearer {SECRET_TOKEN}"
    assert "gmail.googleapis.com" in sent_request.full_url
    assert captured_request["timeout"] == 10


def test_capabilities_never_include_email_send() -> None:
    connector = GmailReadOnlyConnector(token_env_var=TOKEN_VAR)
    caps = connector.capabilities()

    assert "email.read" in caps
    assert "email.draft" in caps
    assert "email.send" not in caps


def test_token_never_leaks_in_success_or_error_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_VAR, SECRET_TOKEN)

    fake_body = {"messages": [{"id": "m1"}]}
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(fake_body).encode("utf-8")
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout=None: response
    )

    connector = GmailReadOnlyConnector(token_env_var=TOKEN_VAR)
    ok_result = connector.list_messages()
    assert SECRET_TOKEN not in json.dumps(ok_result)

    def raise_401(request: urllib.request.Request, timeout: float | None = None) -> Any:
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", None, io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_401)

    error_result = connector.list_messages()
    assert error_result["ok"] is False
    assert error_result["real"] is True
    assert SECRET_TOKEN not in json.dumps(error_result)
    assert SECRET_TOKEN not in error_result["detail"]
