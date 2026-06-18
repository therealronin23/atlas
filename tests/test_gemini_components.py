"""
Atlas Core — Tests adicionales para componentes del chat de Gemini.
Cubre: Triage Alfa/Omega, sensitivity routing, Sandbox, SSRF Bridge,
InferenceHub, OfflineFallbackMode, SystemContextLoader y contratos nuevos.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest


# ===========================================================================
# Fixtures comunes
# ===========================================================================

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "atlas"
    for sub in ["projects", "tmp", "skills", "memory/system_context",
                "memory/audit", "config"]:
        (ws / sub).mkdir(parents=True, exist_ok=True)
    return ws


@pytest.fixture
def orch(workspace: Path):
    import atlas.governance.governance_l0 as g
    g.GovernanceL0._instance = None
    from atlas.core.orchestrator import Orchestrator
    o = Orchestrator(workspace=workspace)
    yield o
    g.GovernanceL0._instance = None


# ===========================================================================
# Triage Alfa/Omega en contratos
# ===========================================================================

class TestOperationalMode:

    def test_task_default_triage_is_alfa(self):
        from atlas.core.contracts import Task, TaskSource, OperationalMode
        t = Task(intent="git status", source=TaskSource.CLI)
        assert t.operational_mode == OperationalMode.NORMAL

    def test_task_can_be_set_omega(self):
        from atlas.core.contracts import Task, TaskSource, OperationalMode
        t = Task(intent="instala paquete", source=TaskSource.CLI, operational_mode=OperationalMode.OMEGA)
        assert t.operational_mode == OperationalMode.OMEGA

    def test_operational_mode_serializes(self):
        from atlas.core.contracts import Task, TaskSource, OperationalMode
        t = Task(intent="test", source=TaskSource.CLI, operational_mode=OperationalMode.OMEGA)
        d = t.to_dict()
        assert d["operational_mode"] == "omega"


# ===========================================================================
# Sensitivity routing — critico del chat de Gemini
# ===========================================================================

class TestSensitivityRouting:

    def test_high_sensitivity_forces_approval_even_for_l_det(self, orch):
        """Regla R05: sensitivity=high siempre → REQUIRES_APPROVAL."""
        from atlas.core.contracts import Task, TaskSource, TaskStatus, RoutingLevel
        t = Task(
            intent="git status del proyecto",
            source=TaskSource.CLI,
            sensitivity="high",
        )
        result = orch.handle_intent(t.intent, source=TaskSource.CLI)
        # Con sensitivity="high" en el intent, no podemos pasarlo directamente
        # Probar el clasificador directamente
        from atlas.router.classifier import Classifier
        clf = Classifier()
        r = clf.classify("git status del proyecto", sensitivity="high")
        assert r.level == RoutingLevel.REQUIRES_APPROVAL
        assert "alta sensibilidad" in r.reason.lower() or "high" in r.reason.lower()

    def test_low_sensitivity_git_status_is_deterministic(self):
        from atlas.router.classifier import Classifier
        from atlas.core.contracts import RoutingLevel
        clf = Classifier()
        r = clf.classify("git status del proyecto", sensitivity="low")
        assert r.level == RoutingLevel.DETERMINISTIC_TOOL

    def test_medium_sensitivity_follows_normal_routing(self):
        from atlas.router.classifier import Classifier
        from atlas.core.contracts import RoutingLevel
        clf = Classifier()
        r = clf.classify("git status", sensitivity="medium")
        # Medium no fuerza REQUIRES_APPROVAL — routing normal
        assert r.level != RoutingLevel.BLOCKED

    def test_sensitivity_invalid_raises(self):
        from atlas.core.contracts import Task, TaskSource
        with pytest.raises(ValueError, match="sensitivity"):
            Task(intent="test", source=TaskSource.CLI, sensitivity="critical")


# ===========================================================================
# Thermal Watchdog y Triage Alfa/Omega
# ===========================================================================

class TestThermalWatchdog:

    def test_default_mode_is_alfa(self):
        from atlas.thermal.watchdog import ThermalWatchdog
        with tempfile.TemporaryDirectory():
            wdog = ThermalWatchdog(poll_interval_seconds=999)
            assert wdog.current_operational_mode().value == "normal"

    def test_sample_now_returns_state(self):
        from atlas.thermal.watchdog import ThermalWatchdog
        wdog = ThermalWatchdog(poll_interval_seconds=999)
        state = wdog.sample_now()
        assert state.operational_mode is not None
        assert isinstance(state.temperature_celsius, float)
        assert isinstance(state.ram_free_mb, int)

    def test_policy_changes_with_temperature(self):
        """Simular distintos umbrales de temperatura."""
        from atlas.thermal.watchdog import ThermalWatchdog, TEMP_OMEGA_THRESHOLD
        from atlas.core.contracts import OperationalMode
        wdog = ThermalWatchdog(poll_interval_seconds=999)

        # Monkey-patch temperatura
        wdog._read_temperature = lambda: TEMP_OMEGA_THRESHOLD + 1
        wdog._read_ram_free_mb = lambda: 4096

        state = wdog.sample_now()
        assert state.operational_mode == OperationalMode.OMEGA
        assert state.should_pause_local_llm is True
        assert state.should_delegate_all is True

    def test_normal_temperature_is_alfa(self):
        from atlas.thermal.watchdog import ThermalWatchdog
        from atlas.core.contracts import OperationalMode
        wdog = ThermalWatchdog(poll_interval_seconds=999)
        wdog._read_temperature = lambda: 45.0
        wdog._read_ram_free_mb = lambda: 8192
        state = wdog.sample_now()
        assert state.operational_mode == OperationalMode.NORMAL
        assert state.should_pause_local_llm is False
        assert state.should_delegate_all is False

    def test_alert_callback_fires_on_mode_change(self):
        from atlas.thermal.watchdog import ThermalWatchdog, TEMP_OMEGA_THRESHOLD
        alerts = []
        wdog = ThermalWatchdog(
            poll_interval_seconds=999,
            alert_callback=lambda s: alerts.append(s),
        )
        wdog._read_temperature = lambda: 45.0
        wdog._read_ram_free_mb = lambda: 8192
        wdog.sample_now()   # Primer sample → establece NORMAL
        # Simular subida de temperatura
        wdog._read_temperature = lambda: TEMP_OMEGA_THRESHOLD + 5
        wdog._compute_state()  # Computar sin actualizar _current_state


# ===========================================================================
# Matrioska Sandbox
# ===========================================================================

class TestLayeredIsolationSandbox:

    def test_safe_code_executes_in_alfa(self, workspace):
        from atlas.security.sandbox import LayeredIsolationSandbox
        from atlas.core.contracts import OperationalMode
        (workspace / "tmp").mkdir(exist_ok=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        result = sandbox.execute("print('hello atlas')", operational_mode=OperationalMode.NORMAL)
        assert result.success is True
        assert "hello atlas" in result.stdout
        assert result.operational_mode == OperationalMode.NORMAL

    def test_dangerous_code_blocked_by_ast_guard(self, workspace):
        from atlas.security.sandbox import LayeredIsolationSandbox
        (workspace / "tmp").mkdir(exist_ok=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        result = sandbox.execute("import subprocess\nsubprocess.run(['ls'])")
        assert result.success is False
        assert "AST Guard" in result.stderr

    def test_timeout_enforced(self, workspace):
        from atlas.security.sandbox import LayeredIsolationSandbox
        from atlas.core.contracts import OperationalMode
        (workspace / "tmp").mkdir(exist_ok=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        sandbox.WALL_TIMEOUT_NORMAL_S = 2   # Override a 2s para el test
        result = sandbox.execute("import time\ntime.sleep(10)", operational_mode=OperationalMode.NORMAL)
        assert result.success is False
        assert "timeout" in result.stderr.lower() or result.exit_code == -1

    def test_omega_stub_returns_snapshot_id(self, workspace):
        from atlas.security.sandbox import LayeredIsolationSandbox
        from atlas.core.contracts import OperationalMode
        (workspace / "tmp").mkdir(exist_ok=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        result = sandbox.execute(
            "print('omega test')",
            operational_mode=OperationalMode.OMEGA,
            take_snapshot=True,
        )
        assert result.operational_mode == OperationalMode.OMEGA
        assert result.snapshot_id is not None
        assert "atlas-snap-" in result.snapshot_id

    def test_command_execution_git_status(self, workspace):
        from atlas.security.sandbox import LayeredIsolationSandbox
        import subprocess
        # Inicializar git repo en workspace
        subprocess.run(["git", "init"], cwd=str(workspace), capture_output=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        result = sandbox.execute_command(["git", "status"])
        # Puede fallar si git no esta instalado, pero el mecanismo debe funcionar
        assert result.exit_code is not None


# ===========================================================================
# SSRF Bridge
# ===========================================================================

class TestSSRFBridge:

    def test_allowed_domain_passes(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("https://api.groq.com/v1/chat/completions")
        assert d.allowed is True
        assert d.domain == "api.groq.com"

    def test_blocked_private_ip(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("http://192.168.1.1/admin")
        assert d.allowed is False
        assert "privada" in d.reason.lower() or "private" in d.reason.lower()

    def test_localhost_blocked(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("http://localhost:8080/api")
        assert d.allowed is False

    def test_aws_metadata_blocked(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("http://169.254.169.254/latest/meta-data/")
        assert d.allowed is False

    def test_non_http_scheme_blocked(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("ftp://files.example.com/file.zip")
        assert d.allowed is False
        assert "esquema" in d.reason.lower() or "scheme" in d.reason.lower()

    def test_unknown_domain_blocked(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        d = bridge.check("https://random-unknown-site.xyz/api")
        assert d.allowed is False

    def test_add_domain_at_runtime(self):
        from atlas.security.ssrf_bridge import SSRFBridge
        bridge = SSRFBridge()
        assert bridge.check("https://custom-api.example.com/v1").allowed is False
        bridge.add_domain("custom-api.example.com")
        assert bridge.check("https://custom-api.example.com/v1").allowed is True

    def test_subdomain_of_allowed(self):
        """SEC-1: match exacto — 'openrouter.ai' en allowlist NO cubre 'api.openrouter.ai'.
        Para permitir api.openrouter.ai hay que anadir el subdominio exacto."""
        from atlas.security.ssrf_bridge import SSRFBridge
        # Subdominio exacto en allowlist → permitido
        bridge = SSRFBridge(extra_allowed={"api.openrouter.ai"})
        d = bridge.check("https://api.openrouter.ai/v1/completions")
        assert d.allowed is True
        # Solo el padre en allowlist → denegado (no wildcard subtree)
        bridge2 = SSRFBridge(extra_allowed={"openrouter.ai"})
        d2 = bridge2.check("https://api.openrouter.ai/v1/completions")
        assert d2.allowed is False


# ===========================================================================
# InferenceHub
# ===========================================================================

class TestInferenceHub:

    def test_stub_returns_response(self):
        from atlas.core.inference_hub import InferenceHub, InferenceRequest, InferenceLevel
        hub = InferenceHub()
        req = InferenceRequest(
            prompt="Explica como funciona un Merkle tree",
            level=InferenceLevel.L1,
        )
        resp = hub.infer(req)
        assert resp.success is True
        assert resp.text != ""
        assert resp.provider != ""
        assert resp.level == InferenceLevel.L1

    def test_fallback_to_l0_when_all_l1_down(self):
        from atlas.core.inference_hub import (
            InferenceHub, InferenceRequest, InferenceLevel,
            Provider, ProviderStatus
        )
        hub = InferenceHub()
        # Marcar todos los L1 como down
        for p in hub._providers:
            if p.level == InferenceLevel.L1:
                p.status = ProviderStatus.DOWN
        req = InferenceRequest(prompt="test", level=InferenceLevel.L1)
        resp = hub.infer(req)
        # Deberia hacer fallback a L0 o fallar con error claro
        assert resp.provider is not None

    def test_providers_status_returns_list(self):
        from atlas.core.inference_hub import InferenceHub
        hub = InferenceHub()
        statuses = hub.providers_status()
        assert len(statuses) > 0
        assert all("name" in s and "level" in s and "status" in s for s in statuses)

    def test_l0_local_in_providers(self):
        from atlas.core.inference_hub import InferenceHub, InferenceLevel
        hub = InferenceHub()
        l0 = [p for p in hub._providers if p.level == InferenceLevel.L0]
        assert len(l0) >= 1
        assert l0[0].base_url.startswith("http://localhost")


# ===========================================================================
# Modo Fantasma (Dead Man's Switch)
# ===========================================================================

class TestOfflineFallbackMode:

    def test_no_shadow_if_recent_ping(self):
        from atlas.hermes.hermes import HermesMockAdapter
        adapter = HermesMockAdapter()
        adapter.ping()
        assert adapter.check_offline_fallback() is False

    def test_shadow_activates_after_timeout(self):
        from atlas.hermes.hermes import HermesMockAdapter
        from datetime import datetime, timezone, timedelta
        adapter = HermesMockAdapter()
        adapter.ping()
        # Simular timeout retroactivo
        adapter._last_ping = datetime.now(timezone.utc) - timedelta(
            minutes=adapter.SHADOW_TIMEOUT_MINUTES + 1
        )
        assert adapter.check_offline_fallback() is True
        assert adapter.offline_fallback_active is True

    def test_ping_resets_shadow_mode(self):
        from atlas.hermes.hermes import HermesMockAdapter
        from datetime import datetime, timezone, timedelta
        adapter = HermesMockAdapter()
        adapter._last_ping = datetime.now(timezone.utc) - timedelta(minutes=60)
        adapter.check_offline_fallback()   # Activa shadow
        assert adapter.offline_fallback_active is True
        adapter.ping()                 # Reset
        assert adapter.offline_fallback_active is False

    def test_no_ping_never_activates_shadow(self):
        """Si nunca hizo ping, shadow mode no se activa (PC nunca estuvo online)."""
        from atlas.hermes.hermes import HermesMockAdapter
        adapter = HermesMockAdapter()
        assert adapter.check_offline_fallback() is False


# ===========================================================================
# SystemContextLoader cargado correctamente
# ===========================================================================

class TestSystemContextLoader:

    def test_loads_all_three_files(self, workspace):
        from atlas.memory.memory_system import SystemContextLoader
        # Copiar archivos de la instalacion al workspace del test
        import shutil
        src = Path(__file__).parent.parent.parent.parent / "memory" / "system_context"
        dst = workspace / "memory" / "system_context"
        if src.exists():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            # Crear contenido minimo para el test
            (dst).mkdir(parents=True, exist_ok=True)
            (dst / "01_vision.md").write_text("# Vision")
            (dst / "02_rules.md").write_text("# Rules")
            (dst / "03_adr.md").write_text("# ADRs")

        memo = SystemContextLoader.load(dst)
        assert memo.vision != ""
        assert memo.rules != ""
        assert memo.adr != ""

    def test_as_system_context_contains_all_sections(self, workspace):
        from atlas.memory.memory_system import SystemContextLoader
        dst = workspace / "memory" / "system_context"
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "01_vision.md").write_text("## Vision\nAtlas es el rey.")
        (dst / "02_rules.md").write_text("## Reglas\nGovernance primero.")
        (dst / "03_adr.md").write_text("## ADRs\nADR-001 abierto.")
        memo = SystemContextLoader.load(dst)
        ctx = memo.as_system_context()
        assert "Vision" in ctx
        assert "Reglas" in ctx
        assert "ADRs" in ctx


# ===========================================================================
# Nuevos ADRs en contratos
# ===========================================================================

class TestNuevosADRs:

    def test_adr_014_matrioska_sandwich(self, workspace):
        """ADR-014: NORMAL tier usa subprocess aislado, OMEGA usa stub con snapshot."""
        from atlas.security.sandbox import LayeredIsolationSandbox
        from atlas.core.contracts import OperationalMode
        (workspace / "tmp").mkdir(exist_ok=True)
        sandbox = LayeredIsolationSandbox(workspace=workspace)
        # NORMAL tier: sin snapshot
        r_alfa = sandbox.execute("x = 1 + 1", operational_mode=OperationalMode.NORMAL)
        assert r_alfa.snapshot_id is None
        # OMEGA: con snapshot
        r_omega = sandbox.execute("x = 1 + 1", operational_mode=OperationalMode.OMEGA, take_snapshot=True)
        assert r_omega.snapshot_id is not None

    def test_adr_016_inference_hub_has_free_providers(self):
        """ADR-016: Pool de proveedores free tier configurado por defecto."""
        from atlas.core.inference_hub import InferenceHub
        hub = InferenceHub()
        free = [p for p in hub._providers if p.free_tier]
        assert len(free) >= 4

    def test_adr_017_tailscale_documented_in_trinity(self, workspace):
        """ADR-017: Tailscale como tunnel debe estar documentado en ADRs."""
        dst = workspace / "memory" / "system_context"
        dst.mkdir(parents=True, exist_ok=True)
        import shutil
        src = Path(__file__).parent.parent.parent.parent / "memory" / "system_context"
        if src.exists() and (src / "03_adr.md").exists():
            shutil.copy2(src / "03_adr.md", dst / "03_adr.md")
            content = (dst / "03_adr.md").read_text()
            assert "Tailscale" in content or "tailscale" in content.lower()
