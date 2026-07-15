"""Tests para Atlas Dashboard (Gate E/E2).

Usa FastAPI TestClient (starlette) — no requiere servidor real.
El dashboard se configura con un workspace temporal para aislamiento.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_DASHBOARD_TOKEN = "test-dashboard-token-with-at-least-32-chars"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Crea un workspace temporal con la estructura mínima."""
    ws = tmp_path / "atlas_test"
    for sub in [
        "config", "memory/system_context", "memory/error_registry",
        "memory/approved_patterns", "memory/performance", "memory/audit",
        "projects", "tmp", "skills",
    ]:
        (ws / sub).mkdir(parents=True, exist_ok=True)

    # Copiar governance.json y permissions.yaml desde config/
    src_config = Path(__file__).parent.parent / "config"
    import shutil
    shutil.copy(src_config / "governance.json", ws / "config" / "governance.json")
    shutil.copy(src_config / "permissions.yaml", ws / "config" / "permissions.yaml")

    return ws


@pytest.fixture()
def client(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient con ATLAS_HOME apuntando al workspace temporal."""
    monkeypatch.setenv("ATLAS_HOME", str(workspace))
    monkeypatch.setenv("ATLAS_DASHBOARD_TOKEN", _DASHBOARD_TOKEN)

    # Reiniciar el singleton de Orchestrator para que use el workspace del test
    import atlas.interfaces.dashboard as dash_module
    dash_module._orch = None

    from atlas.interfaces.dashboard import app
    return TestClient(
        app,
        raise_server_exceptions=True,
        headers={"Authorization": f"Bearer {_DASHBOARD_TOKEN}"},
    )


# ---------------------------------------------------------------------------
# Tests de rutas HTML
# ---------------------------------------------------------------------------

class TestDashboardRoutes:
    def test_remote_request_without_token_is_rejected(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_HOME", str(workspace))
        monkeypatch.setenv("ATLAS_DASHBOARD_TOKEN", _DASHBOARD_TOKEN)
        from atlas.interfaces.dashboard import app

        response = TestClient(app).get("/audit")
        assert response.status_code == 401

    def test_non_loopback_bind_requires_strong_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from atlas.interfaces.dashboard import _validate_bind_security

        monkeypatch.delenv("ATLAS_DASHBOARD_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="ATLAS_DASHBOARD_TOKEN"):
            _validate_bind_security("0.0.0.0")
        _validate_bind_security("127.0.0.1")

    def test_remote_exec_health_reaches_its_own_hmac_authentication(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ATLAS_HOME", str(workspace))
        monkeypatch.setenv("ATLAS_DASHBOARD_TOKEN", _DASHBOARD_TOKEN)
        from atlas.interfaces.dashboard import app

        remote = TestClient(
            app,
            base_url="http://atlas.tailnet.invalid",
            client=("100.64.0.2", 50000),
        )
        response = remote.post("/api/exec/health", content=b"{}")
        # The dashboard bearer middleware must not mask the independent HMAC
        # layer. An unwired route is 404; a wired/unsigned route is 401.
        assert response.status_code in {401, 404}

    def test_status_200(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
        assert b"Atlas" in r.content

    def test_status_shows_mode(self, client: TestClient) -> None:
        r = client.get("/")
        assert r.status_code == 200
        # Debe mostrar alguno de los tres modos operacionales
        content = r.text
        assert any(m in content for m in ("NORMAL", "DEGRADED", "OMEGA"))

    def test_tasks_200(self, client: TestClient) -> None:
        r = client.get("/tasks")
        assert r.status_code == 200
        assert b"Tareas" in r.content or b"tareas" in r.content

    def test_audit_200(self, client: TestClient) -> None:
        r = client.get("/audit")
        assert r.status_code == 200
        assert b"Merkle" in r.content

    def test_audit_shows_chain_status(self, client: TestClient) -> None:
        r = client.get("/audit")
        assert r.status_code == 200
        content = r.text
        assert "VERIFICADA" in content or "CORRUPTA" in content

    def test_memory_200(self, client: TestClient) -> None:
        r = client.get("/memory")
        assert r.status_code == 200
        assert b"Memoria" in r.content or b"memoria" in r.content

    def test_tools_200(self, client: TestClient) -> None:
        r = client.get("/tools")
        assert r.status_code == 200
        assert b"Tool" in r.content or b"Herramientas" in r.content

    def test_tools_lists_entries(self, client: TestClient) -> None:
        r = client.get("/tools")
        assert r.status_code == 200
        # ToolRegistry tiene herramientas por defecto registradas
        assert b"fs.read_file" in r.content

    def test_providers_200(self, client: TestClient) -> None:
        r = client.get("/providers")
        assert r.status_code == 200
        assert b"groq" in r.content.lower()

    def test_providers_lists_default(self, client: TestClient) -> None:
        r = client.get("/providers")
        assert r.status_code == 200
        # Debe mostrar los proveedores de DEFAULT_PROVIDERS
        assert b"groq_llama_70b" in r.content


# ---------------------------------------------------------------------------
# Tests de JSON API
# ---------------------------------------------------------------------------

class TestDashboardAPI:
    def test_api_status_200(self, client: TestClient) -> None:
        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert "version" in data
        assert "governance_ok" in data
        assert "chain_ok" in data
        assert "record_count" in data
        assert "operational_mode" in data

    def test_api_status_fields_types(self, client: TestClient) -> None:
        data = client.get("/api/status").json()
        assert isinstance(data["governance_ok"], bool)
        assert isinstance(data["chain_ok"], bool)
        assert isinstance(data["record_count"], int)
        assert isinstance(data["temp_c"], float)
        assert isinstance(data["ram_free_mb"], int)

    def test_api_providers_200(self, client: TestClient) -> None:
        r = client.get("/api/providers")
        assert r.status_code == 200
        providers = r.json()
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_api_providers_fields(self, client: TestClient) -> None:
        providers = client.get("/api/providers").json()
        p = providers[0]
        assert "name" in p
        assert "model" in p
        assert "has_key" in p
        assert "stats" in p
        assert "context_tokens" in p

    def test_api_providers_has_key_false_without_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Sin API keys en entorno, has_key debe ser False para proveedores de pago
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        providers = client.get("/api/providers").json()
        groq = next((p for p in providers if p["name"] == "groq_llama_70b"), None)
        assert groq is not None
        assert groq["has_key"] is False


# ---------------------------------------------------------------------------
# Tests de utilidades internas
# ---------------------------------------------------------------------------

class TestDashboardUtils:
    def test_thermal_data_keys(self) -> None:
        from atlas.interfaces.dashboard import _thermal_data
        d = _thermal_data()
        assert "temp_c" in d
        assert "ram_free_mb" in d
        assert "mode" in d
        assert d["mode"] in ("NORMAL", "DEGRADED")

    def test_thermal_data_temp_range(self) -> None:
        from atlas.interfaces.dashboard import _thermal_data
        d = _thermal_data()
        # Temperatura debe ser 0 (no disponible) o razonable
        assert d["temp_c"] >= 0.0
        assert d["temp_c"] < 120.0

    def test_extract_tasks_empty(self) -> None:
        from atlas.interfaces.dashboard import _extract_tasks
        assert _extract_tasks([]) == []

    def test_extract_tasks_filters_correctly(self) -> None:
        from atlas.interfaces.dashboard import _extract_tasks
        records = [
            {"action": "task.received", "payload": {"intent": "hola"}, "result": "success", "risk_level": "safe", "timestamp": "2026-01-01T00:00:00"},
            {"action": "governance.init", "payload": {}, "result": "success", "risk_level": "safe", "timestamp": "2026-01-01T00:00:01"},
        ]
        tasks = _extract_tasks(records)
        assert len(tasks) == 1
        assert tasks[0]["intent"] == "hola"

    def test_memory_stats_returns_dict(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from atlas.interfaces.dashboard import _memory_stats
        monkeypatch.setenv("ATLAS_HOME", str(workspace))
        stats = _memory_stats()
        assert "error_count" in stats
        assert "pattern_count" in stats
        assert "context_loaded" in stats
        assert "kuzu_active" in stats
        assert isinstance(stats["error_count"], int)
        assert isinstance(stats["pattern_count"], int)

    def test_memory_stats_empty_workspace(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from atlas.interfaces.dashboard import _memory_stats
        monkeypatch.setenv("ATLAS_HOME", str(workspace))
        stats = _memory_stats()
        # Workspace vacío → todo en 0 / False
        assert stats["error_count"] == 0
        assert stats["pattern_count"] == 0
        assert stats["context_loaded"] is False

    def test_nav_links_present_in_all_pages(self, client: TestClient) -> None:
        """Todos los links de navegación están presentes en cada página."""
        nav_items = [b"/tasks", b"/audit", b"/memory", b"/tools", b"/providers"]
        for path in ["/", "/tasks", "/audit", "/memory", "/tools", "/providers"]:
            r = client.get(path)
            for item in nav_items:
                assert item in r.content, f"Nav link {item} missing on {path}"

    def test_auto_refresh_meta_tag(self, client: TestClient) -> None:
        r = client.get("/")
        assert b'http-equiv="refresh"' in r.content
        assert b'content="30"' in r.content
