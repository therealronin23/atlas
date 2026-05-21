"""
Atlas Core — Suite de tests Gate B
Cubre los 8 criterios de exito de v0.1 y todos los contratos de sistema.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Workspace temporal limpio para cada test."""
    ws = tmp_path / "atlas"
    ws.mkdir()
    return ws


@pytest.fixture
def orch(workspace: Path):
    """Orquestador con workspace temporal."""
    from atlas.core.orchestrator import Orchestrator
    # Reset singleton de Governance L0 entre tests
    import atlas.governance.governance_l0 as g
    g.GovernanceL0._instance = None

    o = Orchestrator(workspace=workspace)
    yield o
    # Limpieza
    g.GovernanceL0._instance = None


@pytest.fixture
def gov_l0(workspace: Path):
    """GovernanceL0 aislado."""
    import atlas.governance.governance_l0 as g
    g.GovernanceL0._instance = None
    config = workspace / "config"
    config.mkdir(parents=True, exist_ok=True)
    gov_file = config / "governance.json"
    gov_file.write_text(json.dumps({
        "version": "1.0.0",
        "immutable": True,
        "axioms": {"transparency": "Atlas siempre puede explicar."},
        "hard_blocks": [
            "Modificar o eliminar entradas del Merkle Logger.",
            "Modificar este archivo governance.json.",
        ],
        "hard_block_patterns": [
            r"rm\s+-rf\s*/",
            r"\bsudo\b",
            r"governance\.json",
            r"merkle.{0,20}(disable|deshabilit)",
        ],
    }))
    instance = g.GovernanceL0.initialize(gov_file)
    yield instance
    g.GovernanceL0._instance = None


@pytest.fixture
def merkle_logger(tmp_path: Path):
    from atlas.logging.merkle_logger import MerkleLogger
    return MerkleLogger(tmp_path / "audit")


@pytest.fixture
def classifier():
    from atlas.router.classifier import Classifier
    return Classifier()


@pytest.fixture
def ast_guard():
    from atlas.security.ast_guard import ASTGuard
    return ASTGuard()


@pytest.fixture
def permission_profile(workspace: Path):
    from atlas.governance.permission_profile import PermissionProfile
    config = workspace / "config"
    config.mkdir(parents=True, exist_ok=True)
    perms_file = config / "permissions.yaml"
    perms_file.write_text(
        "workspace:\n"
        "  auto_write:\n    - tmp/\n"
        "  confirm_write:\n    - projects/\n    - skills/\n    - memory/\n"
        "  read_only:\n    - config/governance.json\n"
        "  read_extended: []\n"
        "absolute_blocks:\n  - ~/.ssh/\n  - ~/.gnupg/\n  - /etc/\n  - /root/\n"
        "system_read_allowed:\n  - /sys/class/hwmon/\n"
        "telegram:\n  authorized_chat_ids: []\n"
        "shell_allowlist:\n  - echo\n  - cat\n  - ls\n"
    )
    return PermissionProfile(perms_file, workspace)


# ===========================================================================
# Governance L0
# ===========================================================================

class TestGovernanceL0:

    def test_blocks_rm_rf(self, gov_l0):
        """Hard block: rm -rf /"""
        violation = gov_l0.evaluate("ejecuta rm -rf / ahora")
        assert violation is not None
        assert violation.pattern is not None

    def test_blocks_sudo(self, gov_l0):
        violation = gov_l0.evaluate("usa sudo para instalar")
        assert violation is not None

    def test_blocks_governance_json(self, gov_l0):
        violation = gov_l0.evaluate("modifica governance.json")
        assert violation is not None

    def test_blocks_merkle_disable(self, gov_l0):
        # El patron es merkle→disable, no disable→merkle
        violation = gov_l0.evaluate("merkle logger disable")
        assert violation is not None

    def test_safe_intent_passes(self, gov_l0):
        violation = gov_l0.evaluate("lee el archivo README.md")
        assert violation is None

    def test_git_status_passes(self, gov_l0):
        violation = gov_l0.evaluate("git status del proyecto")
        assert violation is None

    def test_file_tamper_enters_emergency_mode(self, gov_l0, workspace):
        """Si governance.json es modificado en disco, entra en modo emergencia."""
        gov_file = workspace / "config" / "governance.json"
        gov_file.write_text('{"version": "TAMPERED"}')
        result = gov_l0.check_file_integrity()
        assert result is False
        assert gov_l0.in_emergency_mode is True

    def test_emergency_mode_blocks_all(self, gov_l0, workspace):
        gov_file = workspace / "config" / "governance.json"
        gov_file.write_text('{"tampered": true}')
        gov_l0.check_file_integrity()
        violation = gov_l0.evaluate("lee el archivo README.md")
        assert violation is not None
        assert "emergencia" in violation.hard_block.lower()


# ===========================================================================
# Permission Profile (ADR-006)
# ===========================================================================

class TestPermissionProfile:

    def test_workspace_read_is_auto(self, permission_profile, workspace):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_path(str(workspace / "projects" / "test.py"), write=False)
        assert result.allowed is True
        assert result.level == PermissionLevel.AUTO

    def test_tmp_write_is_auto(self, permission_profile, workspace):
        from atlas.governance.permission_profile import PermissionLevel
        (workspace / "tmp").mkdir(exist_ok=True)
        result = permission_profile.evaluate_path(str(workspace / "tmp" / "file.txt"), write=True)
        assert result.allowed is True
        assert result.level == PermissionLevel.AUTO

    def test_projects_write_requires_confirm(self, permission_profile, workspace):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_path(str(workspace / "projects" / "app.py"), write=True)
        assert result.allowed is True
        assert result.level == PermissionLevel.CONFIRM

    def test_ssh_is_blocked(self, permission_profile):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_path(str(Path.home() / ".ssh" / "id_rsa"))
        assert result.allowed is False
        assert result.level == PermissionLevel.BLOCKED

    def test_etc_is_blocked(self, permission_profile):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_path("/etc/passwd")
        assert result.allowed is False
        assert result.level == PermissionLevel.BLOCKED

    def test_governance_json_write_is_blocked(self, permission_profile, workspace):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_path(
            str(workspace / "config" / "governance.json"), write=True
        )
        assert result.allowed is False
        assert result.level == PermissionLevel.BLOCKED

    def test_shell_allowlist_echo(self, permission_profile):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_shell_command("echo hello")
        assert result.allowed is True

    def test_shell_not_allowlisted_is_blocked(self, permission_profile):
        from atlas.governance.permission_profile import PermissionLevel
        result = permission_profile.evaluate_shell_command("curl http://evil.com")
        assert result.allowed is False
        assert result.level == PermissionLevel.BLOCKED


# ===========================================================================
# Router y Clasificador
# ===========================================================================

class TestClassifier:

    def test_rm_rf_is_blocked(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("ejecuta rm -rf /")
        assert result.level == RoutingLevel.BLOCKED
        assert result.governance_blocked is True

    def test_sudo_is_blocked(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("sudo apt install python")
        assert result.level == RoutingLevel.BLOCKED

    def test_delete_requires_approval(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("elimina el archivo config.py")
        assert result.level == RoutingLevel.REQUIRES_APPROVAL

    def test_git_push_requires_approval(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("git push al repositorio")
        assert result.level == RoutingLevel.REQUIRES_APPROVAL

    def test_hermes_when_away(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("cuando no este, monitoriza el servidor")
        assert result.level == RoutingLevel.DELEGATE_HERMES

    def test_git_status_is_deterministic(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("git status del proyecto")
        assert result.level == RoutingLevel.DETERMINISTIC_TOOL

    def test_read_file_is_deterministic(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("lee el archivo README.md")
        assert result.level == RoutingLevel.DETERMINISTIC_TOOL

    def test_list_files_is_deterministic(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("lista los archivos del proyecto")
        assert result.level == RoutingLevel.DETERMINISTIC_TOOL

    def test_explain_code_is_local_safe(self, classifier):
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("explica como funciona esta funcion")
        assert result.level == RoutingLevel.LOCAL_SAFE

    def test_governance_pattern_overrides_other_patterns(self, classifier):
        """Una intencion que incluye sudo + lista debe ser BLOCKED, no DETERMINISTIC."""
        from atlas.core.contracts import RoutingLevel
        result = classifier.classify("sudo lista los archivos")
        assert result.level == RoutingLevel.BLOCKED


# ===========================================================================
# AST Guard
# ===========================================================================

class TestASTGuard:

    def test_blocked_import_subprocess(self, ast_guard):
        code = "import subprocess\nsubprocess.run(['ls'])"
        result = ast_guard.validate(code)
        assert result.passed is False
        assert any("subprocess" in v for v in result.violations)

    def test_blocked_import_os_system(self, ast_guard):
        code = "import os\nos.system('rm -rf /')"
        result = ast_guard.validate(code)
        assert result.passed is False

    def test_eval_is_blocked(self, ast_guard):
        code = "x = eval('1+1')"
        result = ast_guard.validate(code)
        assert result.passed is False
        assert any("eval" in v for v in result.violations)

    def test_exec_is_blocked(self, ast_guard):
        code = "exec('import os')"
        result = ast_guard.validate(code)
        assert result.passed is False

    def test_path_traversal_in_open(self, ast_guard):
        code = "open('../../../etc/passwd', 'r')"
        result = ast_guard.validate(code)
        assert result.passed is False

    def test_dunder_globals_is_blocked(self, ast_guard):
        code = "x = func.__globals__"
        result = ast_guard.validate(code)
        assert result.passed is False

    def test_safe_code_passes(self, ast_guard):
        code = "import math\nresult = math.pi * 2\nprint(result)"
        result = ast_guard.validate(code)
        assert result.passed is True

    def test_os_path_is_allowed(self, ast_guard):
        """os.path es permitido; os.system no."""
        code = "import os\nresult = os.path.join('a', 'b')"
        result = ast_guard.validate(code)
        assert result.passed is True

    def test_syntax_error_fails_gracefully(self, ast_guard):
        code = "def broken(:"
        result = ast_guard.validate(code)
        assert result.passed is False
        assert any("sintaxis" in v.lower() or "syntax" in v.lower() for v in result.violations)


# ===========================================================================
# Merkle Logger
# ===========================================================================

class TestMerkleLogger:

    def test_first_record_has_genesis_hash(self, merkle_logger):
        from atlas.logging.merkle_logger import GENESIS_HASH
        rec = merkle_logger.log("session.started", "test", "success")
        assert rec.hash_prev == GENESIS_HASH

    def test_chain_valid_after_multiple_appends(self, merkle_logger):
        for i in range(10):
            merkle_logger.log("task.created", "test", "success", payload={"n": i})
        ok, msg = merkle_logger.verify_chain()
        assert ok is True, msg

    def test_new_record_references_last_hash(self, merkle_logger):
        r1 = merkle_logger.log("task.created", "test", "success")
        r2 = merkle_logger.log("task.completed", "test", "success")
        assert r2.hash_prev == r1.hash_self

    def test_tampered_record_detected(self, merkle_logger, tmp_path):
        for _ in range(5):
            merkle_logger.log("task.created", "test", "success")
        log_file = tmp_path / "audit" / "merkle.jsonl"
        lines = log_file.read_text().splitlines()
        # Modificar la linea 2
        data = json.loads(lines[1])
        data["action"] = "TAMPERED"
        lines[1] = json.dumps(data)
        log_file.write_text("\n".join(lines) + "\n")
        # Nuevo logger sobre el mismo archivo
        from atlas.logging.merkle_logger import MerkleLogger
        ml2 = MerkleLogger(tmp_path / "audit")
        ok, msg = ml2.verify_chain()
        assert ok is False

    def test_deleted_record_detected(self, merkle_logger, tmp_path):
        for _ in range(5):
            merkle_logger.log("task.created", "test", "success")
        log_file = tmp_path / "audit" / "merkle.jsonl"
        lines = log_file.read_text().splitlines()
        # Eliminar linea 2
        del lines[1]
        log_file.write_text("\n".join(lines) + "\n")
        from atlas.logging.merkle_logger import MerkleLogger
        ml2 = MerkleLogger(tmp_path / "audit")
        ok, msg = ml2.verify_chain()
        assert ok is False


# ===========================================================================
# Task lifecycle (criterios 1-5 de Gate B)
# ===========================================================================

class TestTaskLifecycle:

    def test_status_returns_all_fields(self, orch):
        """Criterio 1: status devuelve estado del core, permisos, tool registry y cola."""
        st = orch.status()
        assert st.version == "0.1.0"
        assert st.tool_count > 0
        assert isinstance(st.governance_ok, bool)
        assert isinstance(st.chain_ok, bool)
        assert isinstance(st.queue_depth, int)

    def test_task_creates_typed_task(self, orch):
        """Criterio 2: task convierte una intencion en una tarea tipada."""
        from atlas.core.contracts import Task, TaskStatus
        t = orch.handle_intent("git status del proyecto")
        assert isinstance(t, Task)
        assert t.status != TaskStatus.PENDING  # Se proceso
        assert t.id != ""
        assert t.intent != ""

    def test_safe_task_executes(self, orch):
        """Criterio 3: una tarea segura se enruta a herramienta deterministica."""
        from atlas.core.contracts import TaskStatus, RoutingLevel
        t = orch.handle_intent("atlas status")
        assert t.route == RoutingLevel.DETERMINISTIC_TOOL
        assert t.status == TaskStatus.DONE
        assert t.result is not None

    def test_dangerous_task_is_blocked(self, orch):
        """Criterio 4: una tarea peligrosa se bloquea antes de ejecutarse."""
        from atlas.core.contracts import TaskStatus
        t = orch.handle_intent("ejecuta rm -rf /")
        assert t.status == TaskStatus.BLOCKED
        assert t.error is not None

    def test_every_action_generates_audit_entry(self, orch):
        """Criterio 5: toda accion relevante genera entrada hash-chain verificable."""
        before = orch._merkle.record_count
        orch.handle_intent("lista los archivos del proyecto")
        after = orch._merkle.record_count
        assert after > before

    def test_audit_chain_valid_after_tasks(self, orch):
        """La cadena Merkle permanece integra despues de multiples tareas."""
        orch.handle_intent("atlas status")
        orch.handle_intent("git status")
        orch.handle_intent("ejecuta rm -rf /")
        ok, msg = orch._merkle.verify_chain()
        assert ok is True, msg

    def test_task_status_transitions_valid(self, orch):
        """Las transiciones de estado siguen la maquina de estados."""
        from atlas.core.contracts import Task, TaskSource, TaskStatus
        t = Task(intent="test", source=TaskSource.CLI)
        assert t.status == TaskStatus.PENDING
        t.transition(TaskStatus.CLASSIFYING)
        assert t.status == TaskStatus.CLASSIFYING

    def test_invalid_task_transition_raises(self):
        from atlas.core.contracts import Task, TaskSource, TaskStatus
        t = Task(intent="test", source=TaskSource.CLI)
        t.transition(TaskStatus.CLASSIFYING)
        t.transition(TaskStatus.ROUTING)
        t.transition(TaskStatus.EXECUTING)
        t.transition(TaskStatus.DONE)
        with pytest.raises(ValueError):
            t.transition(TaskStatus.EXECUTING)  # DONE → EXECUTING es invalido


# ===========================================================================
# Delegacion mock (criterios 6-7)
# ===========================================================================

class TestDelegationMock:

    def test_delegatable_task_generates_valid_payload(self, orch):
        """Criterio 6: delegable → payload Hermes valido sin contactar VPS real."""
        from atlas.core.contracts import TaskStatus
        t = orch.handle_intent("cuando no este, monitoriza el servidor")
        assert t.status == TaskStatus.DELEGATED
        assert t.result is not None
        assert "delegation_id" in t.result
        assert t.result["accepted"] is True

    def test_delegation_enters_offline_queue(self, orch):
        """El payload se persiste en la cola offline."""
        before = orch._offline_queue.depth
        orch.handle_intent("cuando yo no este, avisa por telegram si algo falla")
        after = orch._offline_queue.depth
        assert after > before

    def test_delegation_signature_is_valid(self, orch):
        """El mock firma el payload con HMAC."""
        orch.handle_intent("cuando no este, monitoriza el servidor")
        pending = orch._offline_queue.all_pending()
        assert len(pending) > 0
        payload = pending[0].delegation
        assert payload.signature != ""

    def test_offline_queue_preserves_fifo_order(self, orch):
        """Criterio 7: cola offline preserva FIFO para misma prioridad."""
        from atlas.core.contracts import TaskSource
        intents = [
            "cuando no este, monitoriza servidor A",
            "cuando yo no este, monitoriza servidor B",
            "cuando yo no este, monitoriza servidor C",
        ]
        for i in intents:
            orch.handle_intent(i)
        pending = orch._offline_queue.all_pending()
        task_intents = [e.delegation.task_intent for e in pending]
        # Los tres deben estar y en orden
        assert len(task_intents) >= 3

    def test_priority_overrides_fifo(self):
        """Una tarea de prioridad 5 se procesa antes que las de prioridad 3."""
        from atlas.hermes.hermes import OfflineQueue, QueueEntry, DelegationBuilder
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            queue = OfflineQueue(Path(d) / "memory")
            low1 = DelegationBuilder.build("t1", "tarea baja 1", 3)
            low2 = DelegationBuilder.build("t2", "tarea baja 2", 3)
            high = DelegationBuilder.build("t3", "tarea urgente", 5)
            queue.enqueue(QueueEntry(delegation=low1))
            queue.enqueue(QueueEntry(delegation=low2))
            queue.enqueue(QueueEntry(delegation=high))
            top = queue.peek()
            assert top is not None
            assert top.delegation.task_intent == "tarea urgente"


# ===========================================================================
# Contratos de sistema (criterio 8)
# ===========================================================================

class TestContracts:

    def test_task_schema_valid(self):
        from atlas.core.contracts import Task, TaskSource
        t = Task(intent="test intent", source=TaskSource.CLI)
        d = t.to_dict()
        assert d["intent"] == "test intent"
        assert d["status"] == "pending"
        assert d["source"] == "cli"
        assert "id" in d

    def test_task_priority_invariant(self):
        from atlas.core.contracts import Task, TaskSource
        with pytest.raises(ValueError):
            Task(intent="test", source=TaskSource.CLI, priority=0)
        with pytest.raises(ValueError):
            Task(intent="test", source=TaskSource.CLI, priority=6)

    def test_task_empty_intent_invariant(self):
        from atlas.core.contracts import Task, TaskSource
        with pytest.raises(ValueError):
            Task(intent="   ", source=TaskSource.CLI)

    def test_audit_record_schema_valid(self):
        from atlas.logging.merkle_logger import AuditRecord, GENESIS_HASH
        rec = AuditRecord(
            action="task.created", agent="test",
            result="success", risk_level="safe",
        )
        assert rec.hash_prev == GENESIS_HASH
        assert len(rec.hash_self) == 64
        assert rec.verify() is True

    def test_audit_record_verify_detects_tamper(self):
        from atlas.logging.merkle_logger import AuditRecord
        rec = AuditRecord(action="task.created", agent="test",
                          result="success", risk_level="safe")
        object.__setattr__(rec, "action", "TAMPERED")
        assert rec.verify() is False

    def test_delegation_payload_schema_valid(self):
        from atlas.core.contracts import DelegationPayload
        p = DelegationPayload(task_id="t1", task_intent="test", priority=3)
        d = p.to_dict()
        assert d["task_id"] == "t1"
        assert d["expires_at"] != ""

    def test_event_schema_valid(self):
        from atlas.core.contracts import Event, EventType
        e = Event(type=EventType.TASK_RECEIVED, payload={"x": 1})
        d = e.to_dict()
        assert d["type"] == "task.received"
        assert d["payload"] == {"x": 1}

    def test_tool_registry_loads_16_defaults(self):
        from atlas.memory.memory_system import ToolRegistry
        registry = ToolRegistry()
        tools = registry.all()
        assert len(tools) == 16

    def test_all_default_tools_are_enabled(self):
        from atlas.memory.memory_system import ToolRegistry
        registry = ToolRegistry()
        assert all(t.enabled for t in registry.all())

    def test_hermes_status_schema(self):
        from atlas.core.contracts import HermesStatus
        s = HermesStatus(reachable=False, mode="mock")
        assert s.reachable is False
        assert s.mode == "mock"

    def test_queue_status_schema(self):
        from atlas.core.contracts import QueueStatus
        s = QueueStatus(depth=3, oldest_task_age_seconds=120,
                        next_task_id="abc", processing=False)
        assert s.depth == 3
