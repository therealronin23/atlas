# PLAN DE IMPLEMENTACIÓN: Items 2 & 3

**Creado:** 25 de mayo de 2026  
**Items:** Hermes Webhook (12h) + ColdUpdate Auto-patch (24h)  
**Status:** Design & Architecture  

---

## ITEM 2: HERMES PUSH WEBHOOK (12h)

### 2.1 Problema actual

**OfflineMonitor** (src/atlas/core/offline_monitor.py):
- Polls `hermes.check_offline_fallback()` cada 60s (configurable)
- CPU waste para mucho polling
- Latency de 60s en promedio para detectar reconexión

### 2.2 Solución

Reemplazar polling con **event-driven webhook**:

```
Hermes-VPS
  ├─ Detecta cambio de estado (online/offline)
  ├─ Genera evento (OfflineEvent, OnlineEvent)
  └─ HTTP POST a Atlas webhook: /api/hermes/webhook
         ↓
      AtlasWebhookHandler
         ├─ Parse payload
         ├─ Validate HMAC signature (security)
         └─ Publish EventBus (SHADOW_ALERT o HERMES_RECONNECTED)
              ↓
            Subscriptores (TelegramBot, CLI, etc.)
```

### 2.3 Cambios necesarios

#### A. Eliminar OfflineMonitor polling (0.5h)

**archivo:** `src/atlas/core/orchestrator.py`

```python
# Ahora:
self._offline_monitor = OfflineMonitor(self.hermes, self._bus, poll_interval_seconds=60)
self._offline_monitor.start()

# Después (remove polling):
# self._offline_monitor.start()  # DEPRECATED
self._webhook_listener.start()  # NEW
```

#### B. Crear WebhookListener (2h)

**Nuevo archivo:** `src/atlas/interfaces/hermes_webhook.py`

```python
from fastapi import APIRouter, Request, HTTPException
from hmac import compare_digest
import hmac
import hashlib
from atlas.core.contracts import EventType
from atlas.core.event_bus import EventBus

class HermesWebhookHandler:
    def __init__(self, bus: EventBus, hmac_key: str):
        self._bus = bus
        self._hmac_key = hmac_key
        self.router = APIRouter(prefix="/api/hermes")
    
    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature from Hermes."""
        expected = hmac.new(
            self._hmac_key.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return compare_digest(expected, signature)
    
    @self.router.post("/webhook")
    async def webhook_event(self, request: Request):
        """
        Recibe eventos de Hermes-VPS.
        
        Payload esperado:
        {
            "event_type": "online" | "offline",
            "timestamp": "2026-05-25T10:30:45Z",
            "elapsed_minutes": 5,  # si offline
            "signature": "hmac-sha256-hex"
        }
        """
        # Parse
        try:
            body = await request.body()
            payload = json.loads(body)
        except:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Verify HMAC
        sig = payload.pop("signature")
        if not self._verify_signature(body, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Route event
        event_type = payload["event_type"]
        if event_type == "offline":
            self._bus.publish_type(EventType.SHADOW_ALERT, {
                "elapsed_minutes": payload.get("elapsed_minutes"),
                "source": "hermes_webhook",
            })
        elif event_type == "online":
            self._bus.publish_type(EventType.HERMES_RECONNECTED, {
                "source": "hermes_webhook",
                "note": "Hermes pushed online event — triggering offline queue sync",
            })
        
        return {"status": "received"}
```

#### C. Actualizar Hermes-VPS script (3h)

**archivo:** `scripts/install_hermes_vps.sh`

Agregar a la parte de Docker container setup:

```bash
# Add webhook callback to Docker env
docker run --detach \
  -e HERMES_WEBHOOK_URL="http://atlas-local:7331/api/hermes/webhook" \
  -e HERMES_WEBHOOK_HMAC_KEY="$HERMES_API_KEY" \
  -e HERMES_WEBHOOK_ENABLED=1 \
  ... rest of docker run
```

#### D. Agregar endpoint a Atlas FastAPI app (1h)

**archivo:** `src/atlas/interfaces/dashboard.py` (o nuevo `src/atlas/interfaces/service.py`)

```python
# En el router FastAPI principal:
from atlas.interfaces.hermes_webhook import HermesWebhookHandler

webhook_handler = HermesWebhookHandler(bus=orchestrator._bus, hmac_key=HERMES_API_KEY)
app.include_router(webhook_handler.router)

# Ahora: POST /api/hermes/webhook es ruteado
```

#### E. Actualizar contracts (0.5h)

**archivo:** `src/atlas/core/contracts.py`

Agregar enum si no existe:

```python
class EventType(Enum):
    # ... existing
    HERMES_WEBHOOK_RECEIVED = "hermes_webhook_received"
    HERMES_ONLINE_CONFIRMED = "hermes_online_confirmed"
```

### 2.4 Testing (2h)

**Nuevo archivo:** `tests/test_hermes_webhook.py`

```python
import pytest
import json
import hmac
import hashlib
from fastapi.testclient import TestClient
from atlas.interfaces.hermes_webhook import HermesWebhookHandler
from atlas.core.event_bus import EventBus

@pytest.fixture
def webhook_handler():
    bus = EventBus()
    return HermesWebhookHandler(bus, hmac_key="test-secret")

def test_webhook_offline_event(webhook_handler):
    payload = {
        "event_type": "offline",
        "timestamp": "2026-05-25T10:30:45Z",
        "elapsed_minutes": 5,
    }
    body = json.dumps(payload).encode()
    sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    payload["signature"] = sig
    
    # Test request
    client = TestClient(...)  # Mock FastAPI app
    response = client.post("/api/hermes/webhook", json=payload)
    assert response.status_code == 200
    # Verify event published to bus
    # ...

def test_webhook_invalid_signature(webhook_handler):
    payload = {"event_type": "offline", "signature": "invalid"}
    response = client.post("/api/hermes/webhook", json=payload)
    assert response.status_code == 401
```

### 2.5 Deployment checklist

- [ ] Remove OfflineMonitor.start() from orchestrator
- [ ] Add HermesWebhookHandler to FastAPI app
- [ ] Update install_hermes_vps.sh with env vars
- [ ] Add HERMES_WEBHOOK_URL + HERMES_WEBHOOK_HMAC_KEY to .env
- [ ] Run tests
- [ ] Deploy to Hermes-VPS (new container image)
- [ ] Verify webhook POST is received
- [ ] Verify event bus publishes correctly
- [ ] Remove OfflineMonitor references from docs
- [ ] Tag: `v0.9.1-hermes-webhook`

---

## ITEM 3: COLDUPDATE AUTO-PATCH (24h)

### 3.1 Problema actual

**SelfAuditLoop** genera candidatos (findings + recommendations) pero NO genera parches.  
**ColdUpdateManager** espera parches manuales (origin="manual").

### 3.2 Solución

Wire SelfAuditLoop → auto-patch generation:

```
SelfAuditCycle.run()
  ├─ Observa repo (git status, test failures, security alerts)
  ├─ Genera findings + candidates
  └─ Para cada candidate:
       ├─ Genera patch (git diff o archivo .patch)
       ├─ Crea ColdUpdateProposal(origin="self_audit")
       └─ Aguarda HITL approval (keep humans in loop)
```

### 3.3 Cambios necesarios

#### A. Crear PatchGenerator (6h)

**Nuevo archivo:** `src/atlas/core/patch_generator.py`

```python
"""
Auto-generate patches for self-audit candidates.

No hot code execution. All patches stored as .patch files awaiting HITL review.
"""

from pathlib import Path
import subprocess
import tempfile
from dataclasses import dataclass

@dataclass
class GeneratedPatch:
    id: str
    candidate_id: str
    filename: str  # e.g., "fix_docstring_orchestrator.patch"
    content: str   # unified diff format
    before_hash: str  # git tree hash before patch
    after_hash: str   # git tree hash after patch (simulated)
    risk_level: str   # low | medium | high | critical

class PatchGenerator:
    """Generate git patches from SelfAuditCandidate recommendations."""
    
    ALLOWED_CATEGORIES = (
        "docstring_missing",      # Add docstrings
        "exception_handler",      # Replace broad `except Exception`
        "test_missing",          # Add test coverage
        "performance_hint",      # Optimize hot path
        "security_lint",         # Fix lint findings
    )
    
    def __init__(self, repo_root: Path):
        self._root = repo_root.resolve()
    
    def generate_for_candidate(self, candidate: SelfAuditCandidate) -> GeneratedPatch | None:
        """
        Attempt to auto-generate patch for candidate.
        
        Returns None if patch cannot be safely auto-generated
        (e.g., requires complex refactor).
        """
        category = candidate.category
        if category not in self.ALLOWED_CATEGORIES:
            return None  # Skip, requires manual review
        
        if category == "docstring_missing":
            return self._generate_docstring_patch(candidate)
        elif category == "exception_handler":
            return self._generate_exception_handler_patch(candidate)
        elif category == "test_missing":
            return self._generate_test_patch(candidate)
        elif category == "performance_hint":
            return None  # Too risky, requires manual
        elif category == "security_lint":
            return self._generate_lint_fix_patch(candidate)
        
        return None
    
    def _generate_docstring_patch(self, candidate: SelfAuditCandidate) -> GeneratedPatch:
        """
        Generate patch to add docstrings to function.
        
        Uses AST + LLM (if available) to suggest docstrings.
        Falls back to simple template.
        """
        file_path = Path(candidate.detail["file"])
        line_no = candidate.detail["line"]
        
        # Read file
        content = (self._root / file_path).read_text()
        lines = content.split('\n')
        
        # Insert simple docstring template
        indent = len(lines[line_no]) - len(lines[line_no].lstrip())
        docstring = f'{" " * indent}    """TODO: Add docstring."""'
        lines.insert(line_no + 1, docstring)
        
        new_content = '\n'.join(lines)
        
        # Generate diff
        diff = self._generate_diff(file_path, content, new_content)
        
        return GeneratedPatch(
            id=uuid.uuid4().hex[:8],
            candidate_id=candidate.id,
            filename=f"add_docstring_{file_path.stem}.patch",
            content=diff,
            before_hash=git_tree_hash_before,
            after_hash=git_tree_hash_after,
            risk_level="low",
        )
    
    def _generate_exception_handler_patch(self, candidate: SelfAuditCandidate) -> GeneratedPatch:
        """
        Replace `except Exception: pass` with specific exception types.
        
        Requires LLM assistance or manual mapping (fallback: manual review).
        """
        # For MVP, skip (requires complex AST rewrite)
        return None
    
    def _generate_test_patch(self, candidate: SelfAuditCandidate) -> GeneratedPatch:
        """
        Generate test stub for untested function.
        
        Uses function signature to create test template.
        """
        # For MVP: generate pytest template
        function_name = candidate.detail["function"]
        file_path = candidate.detail["file"]
        
        test_stub = f"""
def test_{function_name}_basic():
    \"\"\"TODO: Implement test for {function_name}.\"\"\"
    pytest.skip("Test not yet implemented")
"""
        
        # Write to tests/ directory
        test_file = self._root / "tests" / f"test_{file_path.stem}_generated.py"
        test_file.write_text(test_stub)
        
        # Create patch
        diff = self._generate_diff(
            test_file.relative_to(self._root),
            "",
            test_stub
        )
        
        return GeneratedPatch(
            id=uuid.uuid4().hex[:8],
            candidate_id=candidate.id,
            filename=f"add_test_{function_name}.patch",
            content=diff,
            risk_level="low",
        )
    
    def _generate_lint_fix_patch(self, candidate: SelfAuditCandidate) -> GeneratedPatch:
        """
        Generate patch for lint/format fixes (safe auto-fix).
        
        E.g., missing imports, unused variables, style fixes.
        """
        # Use autopep8 or ruff to auto-fix
        file_path = self._root / candidate.detail["file"]
        
        # Get current content
        original = file_path.read_text()
        
        # Apply auto-fix
        result = subprocess.run(
            ["ruff", "check", "--fix", str(file_path)],
            capture_output=True,
        )
        
        if result.returncode != 0:
            return None  # Auto-fix failed
        
        # Read fixed content
        fixed = file_path.read_text()
        
        # Restore original (don't apply yet)
        file_path.write_text(original)
        
        # Generate diff
        diff = self._generate_diff(
            file_path.relative_to(self._root),
            original,
            fixed
        )
        
        return GeneratedPatch(
            id=uuid.uuid4().hex[:8],
            candidate_id=candidate.id,
            filename=f"lint_fix_{file_path.stem}.patch",
            content=diff,
            risk_level="low",
        )
    
    def _generate_diff(self, file_path: Path, before: str, after: str) -> str:
        """Generate unified diff."""
        import difflib
        
        before_lines = before.split('\n')
        after_lines = after.split('\n')
        
        diff = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm=''
        )
        
        return '\n'.join(diff)
```

#### B. Wire PatchGenerator into SelfAuditLoop (4h)

**archivo:** `src/atlas/core/self_audit.py`

```python
from atlas.core.patch_generator import PatchGenerator, GeneratedPatch

class SelfAuditLoop:
    def __init__(self, ..., patch_generator: PatchGenerator | None = None):
        self._patch_gen = patch_generator or PatchGenerator(repo_root)
    
    def run_cycle(self, ...):
        cycle = SelfAuditCycle(...)
        
        # ... existing: observe, diagnose, find ...
        
        # NEW: Generate patches for candidates
        for candidate in cycle.candidates:
            if candidate.status == "open":  # Not yet actioned
                patch = self._patch_gen.generate_for_candidate(candidate)
                if patch:
                    candidate.patch_path = self._store_patch(patch)
                    self._merkle.log(
                        action="auto_patch_generated",
                        candidate_id=candidate.id,
                        patch_path=candidate.patch_path,
                        risk=patch.risk_level,
                    )
        
        return cycle
    
    def _store_patch(self, patch: GeneratedPatch) -> str:
        """Store patch file, return path relative to repo root."""
        patches_dir = self._root / ".atlas-patches"
        patches_dir.mkdir(exist_ok=True)
        
        patch_file = patches_dir / patch.filename
        patch_file.write_text(patch.content)
        
        return str(patch_file.relative_to(self._root))
```

#### C. Create ColdUpdateProposal from patch (3h)

**archivo:** `src/atlas/core/cold_update_manager.py`

```python
def create_proposal_from_audit_patch(
    self,
    patch: GeneratedPatch,
    candidate_id: str,
    intent: str,
) -> ColdUpdateProposal:
    """
    Create a ColdUpdateProposal from auto-generated patch.
    
    Proposal awaits HITL approval before validation + apply.
    """
    proposal = ColdUpdateProposal(
        id=str(uuid.uuid4()),
        intent=intent,
        status="proposed",
        worktree_path="",  # Will create on validate
        patch_path=patch.filename,
        base_ref="main",
        origin="self_audit",
        risk=patch.risk_level,
        evidence={
            "candidate_id": candidate_id,
            "patch_id": patch.id,
            "auto_generated": True,
        }
    )
    self._proposals[proposal.id] = proposal
    self._save()
    
    self._merkle.log(
        action="proposal_created_from_audit",
        proposal_id=proposal.id,
        origin="self_audit",
        risk=patch.risk_level,
    )
    
    return proposal
```

#### D. CLI integration (2h)

**archivo:** `src/atlas/interfaces/cli.py`

```python
@atlas_cli.group()
def update() -> None:
    """Manage cold updates."""
    pass

@update.command()
def audit_candidates():
    """Show candidates from last self-audit cycle."""
    runner = SelfAuditRunner(...)
    cycle = runner.get_latest_cycle()
    
    for candidate in cycle.candidates:
        if candidate.patch_path:
            click.echo(
                f"✓ {candidate.id}: {candidate.title} "
                f"(patch: {candidate.patch_path})"
            )
        else:
            click.echo(
                f"✗ {candidate.id}: {candidate.title} "
                f"(manual review needed)"
            )

@update.command()
@click.argument("proposal_id")
def approve_audit_patch(proposal_id: str):
    """Approve auto-generated patch from self-audit."""
    manager = ColdUpdateManager(...)
    proposal = manager.get_proposal(proposal_id)
    
    if proposal.origin != "self_audit":
        raise click.ClickException("Not an auto-patch proposal")
    
    proposal.status = "approved"
    manager._save()
    
    click.echo(f"✓ Approved proposal {proposal_id}")
    click.echo(f"  Run: atlas update apply {proposal_id}")
```

#### E. Notification (2h)

**archivo:** `src/atlas/interfaces/telegram_bot.py`

```python
async def on_audit_patch_ready(self, event: dict):
    """Notify user when self-audit generates a patch."""
    proposal_id = event["proposal_id"]
    risk = event["risk"]
    intent = event["intent"]
    
    emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "⛔"}
    
    text = f"""{emoji[risk]} Auto-patch ready: {intent}
    
ID: {proposal_id}
Risk: {risk}

Review: atlas update audit-candidates
Approve: atlas update approve {proposal_id}
Apply: atlas update apply {proposal_id}
"""
    
    await self.send_message(self.chat_id, text)
```

### 3.4 Testing (4h)

**Nuevo archivo:** `tests/test_patch_generator.py`

```python
import pytest
from atlas.core.patch_generator import PatchGenerator, SelfAuditCandidate

@pytest.fixture
def generator(tmp_path):
    return PatchGenerator(tmp_path)

def test_generate_docstring_patch(generator, tmp_path):
    """Test generating docstring patch."""
    # Create dummy file
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    file = src_dir / "module.py"
    file.write_text("""
def my_function(x):
    return x * 2
""")
    
    candidate = SelfAuditCandidate(
        id="cand-1",
        title="Add docstring to my_function",
        risk="low",
        status="open",
        category="docstring_missing",
        detail={"file": "src/module.py", "line": 1},
        rationale="Function lacks documentation",
    )
    
    patch = generator.generate_for_candidate(candidate)
    assert patch is not None
    assert "docstring" in patch.content
    assert patch.risk_level == "low"

def test_generate_test_patch(generator, tmp_path):
    """Test generating test stub."""
    candidate = SelfAuditCandidate(
        id="cand-2",
        category="test_missing",
        detail={"file": "module.py", "function": "process_data"},
        ...
    )
    
    patch = generator.generate_for_candidate(candidate)
    assert patch is not None
    assert "def test_process_data" in patch.content
```

**Nuevo archivo:** `tests/test_cold_update_audit_integration.py`

```python
def test_self_audit_generates_proposal(self):
    """Test full workflow: audit → patch → proposal."""
    audit_loop = SelfAuditLoop(patch_generator=...)
    cycle = audit_loop.run_cycle()
    
    assert len(cycle.candidates) > 0
    
    # Candidate with patch
    c = [c for c in cycle.candidates if c.patch_path][0]
    assert c.patch_path is not None
    
    # Create proposal from patch
    manager = ColdUpdateManager(...)
    proposal = manager.create_proposal_from_audit_patch(
        patch=...,
        candidate_id=c.id,
        intent=c.title,
    )
    
    assert proposal.status == "proposed"
    assert proposal.origin == "self_audit"
    
    # Approve
    manager.approve_proposal(proposal.id)
    assert proposal.status == "approved"
```

### 3.5 Deployment checklist

- [ ] Crear PatchGenerator + tests
- [ ] Wire PatchGenerator into SelfAuditLoop
- [ ] Update ColdUpdateManager.create_proposal_from_audit_patch()
- [ ] Add CLI commands: `atlas update audit-candidates`, `atlas update approve`
- [ ] Add TelegramBot notification hook
- [ ] Run full test suite
- [ ] Smoke test: Run self-audit cycle, verify patch generated, approve, apply
- [ ] Document in `docs/self_audit_workflow.md`
- [ ] Tag: `v0.9.2-auto-patch-coldupdate`

---

## ROADMAP (36h total)

| Item | Est. | Status | Blocker |
|------|------|--------|---------|
| **1. Prometheus docs** | 2h | ✅ DONE | None |
| **2. Hermes webhook** | 12h | 📋 DESIGN | Need Hermes-VPS image update |
| **3. ColdUpdate auto-patch** | 24h | 📋 DESIGN | PatchGenerator tests |

### Week order:

- **Now-Week1:** Prometheus setup doc + deploy (✅ DONE)
- **Week1-2:** Hermes webhook (implement + test + deploy)
- **Week2-4:** ColdUpdate auto-patch (implement + test + integrate)
- **Week4:** Integration test full workflow
- **Week5:** Tag v0.9.3 (all three items complete)

---

## SUCCESS CRITERIA

### Item 2 (Hermes webhook)
- [ ] OfflineMonitor polling removed
- [ ] Webhook endpoint receives POST from Hermes
- [ ] HMAC signature verified
- [ ] Event bus publishes SHADOW_ALERT / HERMES_RECONNECTED
- [ ] Latency: ~1s (instead of 60s polling)
- [ ] Tests: 100% coverage for webhook handler

### Item 3 (ColdUpdate auto-patch)
- [ ] PatchGenerator creates patches for low-risk candidates
- [ ] SelfAuditLoop triggers patch generation automatically
- [ ] ColdUpdateProposal created with origin="self_audit"
- [ ] CLI: `atlas update audit-candidates`, `atlas update approve`
- [ ] Telegram notifications on patch ready
- [ ] Tests: Full integration test (audit → patch → propose → approve → apply)

---

**Next:** Start implementation week of 26 May (Hermes webhook first, then auto-patch).
