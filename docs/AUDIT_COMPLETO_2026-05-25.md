# AUDITORÍA COMPLETA — ATLAS CORE
**Fecha:** 25 de mayo de 2026  
**Versión:** v0.9.0  
**Estado:** Gates A–I COMPLETE + ADR-024/025 MVP  
**Auditor:** Codex + Explore subagent  

---

## PARTE 1: ¿QUÉ ES ATLAS?

### Definición ejecutiva

**Atlas Core es un runtime local soberano de inteligencia.** No es un chatbot. No es un wrapper de LLM. No es una SaaS.

Es un sistema de toma de decisiones autónomo que:
1. **Coordina modelos locales + APIs gratuitas** (Groq, OpenRouter, Together, Ollama local) para lograr comportamiento de frontier sin pagar por APIs frontier
2. **Decide soberanamente**: Gobernanza inmutable → permisos tipados → clasificación determinista → ejecución auditada
3. **Funciona 24/7** con seguridad de fortaleza (7 capas de defensa), auditoría forense (Merkle SHA-256), y observabilidad
4. **Delega inteligentemente**: Cuando la máquina local está crítica (>80°C, <512MB RAM), delega a Hermes-VPS (máquina remota en Hetzner con Tailscale)
5. **Requiere aprobación manual** vía CLI/Telegram/web antes de ejecutar acciones peligrosas (delete, git push, write, network)

### Filosofía arquitectónica

**"Atlas decides. Hermes executes. All external components serve Atlas, not the other way around."**

Tres componentes:
- **Atlas Core** (localhost): Toma de decisiones, governanza, validación, auditoría
- **Hermes-VPS** (Hetzner): Executor remoto para trabajos pesados cuando local no puede
- **Interfaces**: CLI, Telegram bot, Dashboard web, Voice STT/TTS, BrowserTool, EditorTool

### Flujo de ejecución (simplificado)

```
User Intent (CLI: "atlas task 'delete /tmp/cache'")
    ↓
[1] Constitution check (governance.json immutable)
    ↓ REJECT si coincide banned patterns: rm -rf, sudo, /etc, /root, /etc, ~/.ssh, ~/.gnupg
    ↓ PROCEED si no coincide
[2] Permission Profile check
    ↓ What sensitivity level? Can user even do this?
[3] Classifier (rule-based + optional SLM)
    ↓ DETERMINISTIC_TOOL (read) | LOCAL_SAFE (deterministic op) | REQUIRES_APPROVAL | DELEGATE_HERMES | BLOCKED
[4] Execute (if DETERMINISTIC_TOOL or LOCAL_SAFE)
    ├─ Issue capability token (pre-validated)
    ├─ Route through AtlasExecutor (typed IO)
    ├─ Sandbox (subprocess + resource limits: 512MB RAM, 30s CPU)
    └─ Log to MerkleLogger (SHA-256 chain, forensic)
[5] Approval queue (if REQUIRES_APPROVAL)
    ├─ Store pending con HMAC-SHA256
    ├─ Notificar Telegram con botones inline
    └─ Execute en approve_pending()
[6] Delegate (if DELEGATE_HERMES)
    ├─ Create signed payload
    ├─ Enqueue en OfflineQueue (persist JSON)
    └─ Retry en reconnect
```

---

## PARTE 2: EVALUACIÓN POR EJE

### 2.1. ARQUITECTURA (9/10)

**Fortalezas:**
- Gates A–I todas completadas y selladas (v0.2 → v0.8)
- ADRs documentadas y resueltas (024 Observability, 025 ColdUpdate)
- Pipeline integrado: Governance → Permissions → Classify → Execute → Audit
- Separation of concerns: Core, security, memory, routing, interfaces, tools
- Type safety: Pydantic frozen models, mypy strict, dataclass invariants
- Graceful degradation: KuzuDB, InferenceHub optional; fail silently

**Gaps:**
- Sandbox OMEGA (Proxmox VM snapshot pre-exec) aún stubbed; solo subprocess (NORMAL)
- Escalabilidad limitada a ~10k patrones (KuzuVectorStore O(n) cosine sim)
- Clasificador SLM optional/opt-in; no siempre activado
- Sin federación multi-nodo (flota, Atlas Box) — documentado pero no implementado

**Recomendación:** Nada urgente. El diseño es sólido. Próximo: optimizar KuzuVectorStore con HNSW + implementar webhook Hermes (eliminar polling OfflineMonitor).

---

### 2.2. SEGURIDAD (8/10)

**7 capas de defensa:**

| Capa | Mecanismo | Tiempo | Bypass |
|------|-----------|--------|--------|
| L1: Constitución | governance.json inmutable, tamper-detected | N/A | No |
| L2: Permisos | PermissionProfile (folder map + sensitivity) | <1ms | Solo aprobación manual |
| L3: Clasificación | Rule-based + optional SLM | 1-100ms | Permiso override solo |
| L4: AST Guard | Static analysis pre-exec | <10µs | No llamado para herramientas deterministas |
| L5: Capabilities | Frozen tokens, pre-validated | N/A | Executor siempre verifica |
| L6: Executor | Typed IO, audit log | <1ms | N/A (gatekeeper final) |
| L7: Sandbox | Resource limits (RAM, CPU, tiempo) | 1-10ms | Solo para subprocess |

**Protección contra:**
- ✅ Escalada de privilegios (sudo, chmod blocked by governance)
- ✅ Path traversal (patterns AST Guard, heuristics)
- ✅ Code injection (eval/exec/compile blocked)
- ✅ Acceso no autorizado (PermissionProfile + AtlasExecutor)
- ✅ SSRF (SSRFBridge domain allowlist)
- ✅ Exfiltración PII (PIISurrogate redaction pre-LLM)
- ✅ Governance tampering (MerkleLogger verify_chain)
- ✅ Ataques offline (OfflineMonitor + Dead Man's Switch)
- ✅ Ataques replay (Ghost Replay cache key = hash(intent, sensitivity, context_signature))

**Gaps:**
- ⚠️ Sandbox escape: NORMAL subprocess only; OMEGA Proxmox stubbed
- ⚠️ Timing attacks: No crypto constante-tiempo (hashlib estándar)
- ⚠️ Supply chain: LiteLLM no verificado (depende de pip + git integrity)
- ⚠️ PII v1 regex only: Misses semantic PII (nombres, direcciones) — v2 deferred

**Recomendación:** Implementar PII v2 (SLM-based). Luego: Proxmox OMEGA real. Security posture es fuerte; gaps son post-MVP.

---

### 2.3. CALIDAD / TESTS (9/10)

**Cobertura:**
- **554 core tests** (+ 25 browser deselected by default = 579 total)
- **37 archivos de test**
- **61 source files** mypy-clean
- **Distribución:**
  - Gobernanza + Seguridad: 140+ tests ✅
  - Memoria + Routing: 100+ tests ✅
  - Integración + Operaciones: 100+ tests ✅
  - Computer-use (browser/editor/vision): 25 tests ✅
  - Observability: 20+ tests ✅

**Patrones buenos:**
- Frozen Pydantic models para immutability
- Dataclass invariants en __post_init__
- Mocks para componentes externos (HermesRestAdapter, InferenceHub)
- Fixtures en conftest.py con aislamiento
- Workspace isolation para keys externas

**Áreas de mejora:**
- Exception handling ocasionalmente broad (`except Exception: pass` en sandbox.py:175, thermal/watchdog.py)
- Docstrings sparse relativo a complejidad (especialmente orchestrator.py, distiller.py)
- Algunos tests sin docstring; integration test flow no siempre claro

**Recomendación:** Agregar docstrings a módulos high-complexity. Reemplazar broad exception catches con tipos específicos.

---

### 2.4. INFRAESTRUCTURA / CI-CD (8/10)

**Lo que hay:**
- `.github/workflows/ci.yml` activo
- Pytest con markers: `computer_use` para tests Playwright
- mypy strict mode
- Smoke scripts: `scripts/gate_h_smoke.py`, `scripts/gate_i_smoke.py`, `scripts/operational_smoke.py`
- Hermes-VPS desplegado en Hetzner CPX22 (Ubuntu 26.04)
- Tailscale tunnel end-to-end verificado

**Lo que falta:**
- ⚠️ Hermes push webhook: Aún polling (OfflineMonitor cada 30s) vs. event-driven
- ⚠️ Auto-deployment: No automated rollout de ColdUpdate patches
- ⚠️ Rollback: ColdUpdate aplicable pero no rollback automático

**Recomendación:** P1 = Hermes webhook (eliminar polling). P2 = Auto-deployment con rollback guard.

---

### 2.5. OPERACIONES (9/10)

**Lo que funciona:**
- `atlas serve` (Gate I): Long-lived process con health endpoint + Prometheus
- `atlas health`: Status snapshot
- `atlas update propose|validate|approve|apply`: ColdUpdate workflow
- `atlas self-audit run|status|proposals|report|stop`: 24h audit loops
- Dashboard: `localhost:7331` (FastAPI + Jinja2)
- Telegram bot: Approval flow con inline buttons
- CLI: `atlas status`, `atlas task`, `atlas tools`, `atlas memory`, `atlas audit`
- Observability: TelemetryBus, MicroLedger, OperationalWAL, `/api/observability`

**Lo que es manual:**
- ⚠️ ColdUpdate patch intake (no auto-generación de parches)
- ⚠️ OperationalWAL retention policy (docs mínimas)
- ⚠️ Prometheus setup en producción (falta guía ops)

**Recomendación:** Documentar Prometheus setup. Luego: auto-generación de parches desde SelfAuditLoop candidates.

---

### 2.6. OBSERVABILIDAD (8/10)

**ADR-024 Implementado:**
- TelemetryBus: Event emitter para observability hooks
- MicroLedger: Metrics compacto (tool calls, provider latency, pattern hits)
- OperationalWAL: High-volume trace (rotado, redacta secret keys)
- Prometheus exporter: `/metrics` endpoint (opt-in via env var)
- Dashboard: `/api/observability` JSON API

**Lo que falta:**
- ⚠️ WAL retention policy: No auto-cleanup
- ⚠️ Prometheus dashboard: Métricas existen pero dashboard Grafana no documentado
- ⚠️ Alerting: Sin rules de alertas predefinidas

**Recomendación:** P2 = Documentar Prometheus + dashboard Grafana. P3 = Alerting rules.

---

### 2.7. AUTO-MEJORA (7/10)

**ADR-025 ColdUpdateManager Implementado:**
- Worktree aislado para patches
- Validación de patches (syntax + static checks + integration tests)
- HITL approval requerida (no autonomous)
- Rollback guard

**Lo que falta:**
- ⚠️ Generación automática de parches: ColdUpdate acepta patches manuales solo
- ⚠️ SelfAuditLoop candidates → patch generation: Deferred
- ⚠️ GitHub PR automation: No auto-PR con patch proposals

**Recomendación:** P1 = Auto-generación de parches desde SelfAuditLoop + auto-PR workflow.

---

## PARTE 3: ARQUITECTURA DETALLADA

### 3.1. Componentes principales

**Core (src/atlas/core/)**
- `orchestrator.py` (2000+ lines): Motor ejecutivo principal
- `contracts.py`: Task, Event, DelegationPayload (Pydantic dataclasses)
- `event_bus.py`: Pub/sub tipado in-process
- `inference_hub.py`: Router multi-proveedor (Groq, OpenRouter, Together, Gemini, Ollama)
- `ghost_replay.py`: Cache topológica (TTL + LRU)
- `timetravel.py`: Checkpoints inmutables (debugging)
- `cold_update_manager.py`: Patch intake, validation, HITL apply
- `self_audit.py`: 24h audit loops fríos
- `environment_sensor.py`: Thermal + RAM monitoring
- `offline_monitor.py`: Hermes health polling (Dead Man's Switch)

**Security (src/atlas/security/)**
- `ast_guard.py`: Static analysis pre-exec
- `capabilities.py`: Frozen tokens (Read/Write/Network/Exec)
- `executor.py`: Typed IO + audit log
- `sandbox.py`: Subprocess + resource limits (512MB RAM, 30s CPU)
- `pii_surrogate.py`: Regex detection + surrogates
- `ssrf_bridge.py`: Domain allowlist

**Memory (src/atlas/memory/)**
- `embeddings.py`: StubEmbedder (deterministic hash) + LiteLLMEmbedder
- `vector_store.py`: KuzuDB (10k patterns limit, O(n) cosine sim)
- `distiller.py`: Context compression pre-LLM
- `memory_system.py`: SystemContextLoader, ErrorRegistry, ApprovedPatternStore

**Routing (src/atlas/router/)**
- `classifier.py`: Rule-based (regex + keywords)
- `slm_classifier.py`: SLM-based (optional, via InferenceHub)

**Logging (src/atlas/logging/)**
- `merkle_logger.py`: Append-only SHA-256 chain
- `operational_wal.py`: High-volume trace
- `microledger.py`: Compact metrics
- `telemetry_bus.py`: Event emitter

**Interfaces**
- `cli.py`: CLI commands
- `dashboard.py`: FastAPI + Jinja2 web UI
- `telegram_bot.py`: Telegram approval bot
- `voice.py`: STT/TTS (faster-whisper + piper)

**Tools**
- `browser.py`: Playwright (Gate F)
- `editor.py`: File operations (Gate F)
- `vision_loop.py`: Screenshot → proposal (Gate F)

---

### 3.2. Flujo de decisión (Orchestrator.handle_intent)

```python
1. Governance L0 check (immutable constitution)
   ├─ BLOCKED patterns? → REJECT (rm -rf, sudo, /etc, /root, ~/.ssh, ~/.gnupg)
   └─ PROCEED

2. Permission Profile check
   ├─ User clearance? Folder writable? Sensitivity level?
   └─ PROCEED o DENIED

3. Classifier (rule-based first)
   ├─ Governance rules: confidence 0.0-1.0
   ├─ Tool patterns: DETERMINISTIC, DANGEROUS, DELEGATION
   └─ Route decision (+ confidence)

4. SLM Classifier (optional, si confidence < threshold)
   ├─ Consult InferenceHub con prompt estructurado
   ├─ Parse JSON robusto (tolera markdown)
   └─ Winner-take-all (SLM vs rule, logged to Merkle)

5. Route decision → DETERMINISTIC_TOOL | LOCAL_SAFE | REQUIRES_APPROVAL | DELEGATE_HERMES | BLOCKED

6. Execute (DETERMINISTIC o LOCAL_SAFE)
   ├─ CapabilityIssuer emite token
   ├─ AtlasExecutor typed IO
   ├─ LayeredIsolationSandbox (subprocess + limits)
   └─ MerkleLogger audit

7. Queue (REQUIRES_APPROVAL)
   ├─ Serialize + HMAC-SHA256
   ├─ Notify Telegram
   └─ Wait para approve_pending()

8. Delegate (DELEGATE_HERMES)
   ├─ Create DelegationPayload
   ├─ OfflineQueue persist
   ├─ HermesRestAdapter retry
   └─ OfflineMonitor health check

Task.status: PENDING → CLASSIFYING → ROUTING → (AWAITING_APPROVAL | EXECUTING | DELEGATED) → (DONE | FAILED | BLOCKED)
```

---

### 3.3. Modos operacionales

```
OperationalMode (thermal + RAM aware):

  NORMAL
  ├─ <70°C y >1GB free
  ├─ Full capability: todos los modelos, sin restricciones
  └─ Desktop/laptop default

  DEGRADED
  ├─ 70-79°C ó <1GB free
  ├─ LLM pause: herramientas locales solo
  ├─ Critical functions: read, git status, explain
  └─ Reduce heat/memory footprint

  OMEGA
  ├─ ≥80°C ó <512MB free
  ├─ Dead Man's Switch: L-det only, delegate to Hermes
  ├─ Local inference paused
  └─ Enterprise machines / 24/7 ops
```

---

## PARTE 4: ANÁLISIS DE DEPENDENCIAS

### Dependencias core (pyproject.toml)

```toml
dependencies = [
    "click>=8.1",                   # CLI framework
    "rich>=13.0",                   # TUI formatting
    "fastapi>=0.110",               # Dashboard HTTP
    "uvicorn[standard]>=0.29",      # ASGI runner
    "pydantic>=2.6",                # Data validation (frozen models)
    "pyyaml>=6.0",                  # Config parsing
    "cryptography>=42.0",           # HMAC, signatures
    "litellm>=1.49",                # Multi-provider LLM abstraction
    "kuzu>=0.11",                   # Vector DB (embedded)
]

optional-dependencies = {
    "dev": ["pytest>=8.0", "pytest-asyncio>=0.23", "httpx>=0.27", "mypy>=1.9"],
    "voice": ["faster-whisper>=1.0", "piper-tts>=1.0", "sounddevice>=0.4"],
    "computer-use": ["playwright>=1.45"],
}
```

**Análisis de riesgo:**

| Dep | Riesgo | Mitigación |
|-----|--------|-----------|
| **litellm** | Provider API drift | Fallback chain (Groq→OpenRouter→…) |
| **kuzu** | Embedded DB stability | Graceful degradation si falla |
| **fastapi** | Minor API changes | Pinned en CI |
| **pydantic** | Major v2 compat | Strict validation gates |
| **cryptography** | (ninguno) | Standard lib, stable |
| **playwright** | Optional extra | Solo si `[computer-use]` instalado |

**No known security vulnerabilities** as of 2026-05-25.

---

## PARTE 5: DEBILIDADES Y CUELLOS DE BOTELLA

### 5.1. Performance

| Componente | Operación | Latencia | Límite |
|-----------|-----------|----------|--------|
| Orchestrator | handle_intent() pipeline | 100-500ms | Lineal a # reglas classifier |
| AST Guard | Code validation | <10µs | Constante |
| MemoryDistiller | Context compression | 10-100ms | O(n) chunks × m evals |
| KuzuVectorStore | Similarity search | 50-200ms | O(n) cosine; sin HNSW |
| InferenceHub | LLM call | 1-30s | Network bound |
| Ghost Replay | Cache hit/miss | <5ms | O(1) hash lookup |
| MerkleLogger | Append + hash | <1ms | O(1) append; O(n) verify_chain |
| Sandbox | subprocess exec | 100-5000ms | Spawn overhead |

**Cuellos principales:**
1. **KuzuVectorStore**: O(n) cosine sim without HNSW → 50-200ms para 10k patterns
2. **SLM Classifier**: Optional LLM call → 1-5s si invocado (rule-based by default)
3. **Merkle verify_chain()**: O(n) SHA-256 verification en startup (current behavior)
4. **PII regex**: Compiled per redaction pass; no caching

### 5.2. Escalabilidad

- **Vector store**: Max ~10k patterns (practical limit before cosine sim becomes slow)
- **Ghost Replay**: Max 10k entries (configurable LRU evicts)
- **Merkle logger**: Rotates at 50MB; no auto-archival → manual cleanup needed
- **Classifier rules**: O(n) evaluation; no trie/AC automaton optimization
- **No federación**: Multi-nodo (Atlas Box) no soportada aún

### 5.3. Gaps operacionales

| Item | Prioridad | Esfuerzo | Impacto |
|------|-----------|----------|--------|
| Hermes push webhook | P1 | Medium | Elimina polling OfflineMonitor |
| ColdUpdate auto-patch generation | P1 | High | Cierra self-audit loop |
| KuzuVectorStore HNSW | P2 | High | Scale >10k patterns |
| PII v2 (SLM detection) | P2 | Medium | Semantic PII (nombres, direcciones) |
| Memory sync ADR-012 | P2 | Medium | Bidirectional Hermes ↔ Atlas |
| Prometheus dashboard + WAL retention | P2 | Low | ADR-024 operacional |
| Sandbox OMEGA real (Proxmox) | P3 | High | True VM isolation |
| Flota / Atlas Box | P3 | Very high | Multi-nodo federation |

---

## PARTE 6: RECOMENDACIONES PRIORIZADAS

### 🔴 CRÍTICO (hacer primero)

**1. Documentar Prometheus en producción (2-3 horas)**
- Guide para `atlas serve` con `ATLAS_PROMETHEUS=1`
- Scrape config de ejemplo (prometheus.yml)
- Alerting rules básicas (CPU, memory, Merkle verify failures)
- **Impact:** ADR-024 operacionalizable
- **File:** Crear `docs/prometheus_setup.md`

**2. Reemplazar exception handlers broad (4 horas)**
- `sandbox.py:175` → specific exception types
- `thermal/watchdog.py` → similar
- **Impact:** Debuggability, error recovery
- **Files:** `src/atlas/security/sandbox.py`, `src/atlas/thermal/watchdog.py`

### 🟠 ALTO (próximas 1-2 semanas)

**3. Hermes push webhook (12-16 horas)**
- Reemplazar OfflineMonitor polling (cada 30s) con event-driven
- Hermes-VPS webhook → Atlas notificación
- Drop polling; switch a async listener
- **Impact:** Reduce latency + CPU (polling every 30s)
- **Files:** `src/atlas/hermes/hermes.py`, `src/atlas/core/orchestrator.py`, `scripts/install_hermes_vps.sh`
- **Blocker:** Hermes-VPS webhook handler

**4. Ghost Replay TTL lazy cleanup (2-3 horas)**
- Check TTL en hit/miss path (no solo en purge())
- Evict stale entries automáticamente
- **Impact:** Memory efficiency
- **Files:** `src/atlas/core/ghost_replay.py`

**5. Agregar docstrings high-complexity (6-8 horas)**
- `orchestrator.py`: handle_intent(), classify pathway
- `distiller.py`: compression algorithm
- `vector_store.py`: KuzuDB schema + similarity search
- **Impact:** Maintainability
- **Files:** `src/atlas/core/orchestrator.py`, `src/atlas/memory/distiller.py`, `src/atlas/memory/vector_store.py`

### 🟡 MEDIO (1-2 meses)

**6. ColdUpdate autonomous patch generation (24-32 horas)**
- Wire SelfAuditLoop candidates → auto-patch generation
- Validation + HITL approval (keep)
- Auto-PR al GitHub (opcional)
- **Impact:** Close self-audit loop
- **Files:** `src/atlas/core/cold_update_manager.py`, `src/atlas/core/self_audit.py`, GitHub Actions

**7. KuzuVectorStore HNSW extension (16-24 horas)**
- Migrate from O(n) cosine → O(log n) HNSW
- Kuzu HNSW support incoming; prepare bridge
- **Impact:** Scale to 100k+ patterns
- **Files:** `src/atlas/memory/vector_store.py`

**8. PII Surrogate v2 (SLM-based) (12-16 horas)**
- Semantic NAME/CITY/ADDRESS detection via InferenceHub
- Fallback to regex v1 si SLM falla
- **Impact:** Reduce PII exfiltration risk
- **Files:** `src/atlas/security/pii_surrogate.py`

### 🟢 FUTURO (post-MVP)

**9. Memory sync ADR-012 (8-12 horas)**
- Bidirectional context mirror Hermes ↔ Atlas
- Sync on reconnect
- **Files:** `src/atlas/hermes/hermes.py`, `src/atlas/core/orchestrator.py`

**10. Flota / Atlas Box (40-60 horas)**
- Distributed Merkle logging
- Multi-node governance
- **Files:** New `src/atlas/fleet/` module

**11. Sandbox OMEGA real — Proxmox integration (32-40 horas)**
- VM snapshot before exec
- Rollback on error
- **Files:** `src/atlas/security/sandbox.py`

---

## PARTE 7: PLAN DE ACCIÓN (PRÓXIMOS 30 DÍAS)

### Week 1 (25-31 mayo)
- [ ] Document Prometheus setup (2-3h)
- [ ] Replace broad exception handlers (4h)
- [ ] Add docstrings to orchestrator, distiller, vector_store (6-8h)
- [ ] Ghost Replay TTL lazy cleanup (2-3h)
- **Total:** ~14-18h

### Week 2-3 (1-14 junio)
- [ ] Hermes push webhook (12-16h) — requires Hermes-VPS webhook handler
- [ ] Start ColdUpdate auto-patch generation design (4-6h)
- **Total:** ~18-22h

### Week 4+ (15 junio+)
- [ ] Implement ColdUpdate auto-patch (16-24h)
- [ ] KuzuVectorStore HNSW bridge (16-24h)
- [ ] PII v2 SLM detection (12-16h)

---

## PARTE 8: CONCLUSIÓN

### Veredicto final

✅ **Atlas Core está listo para operación local soberana 24/7** con gobernanza inmutable, seguridad de fortaleza, auditoría forense y resiliencia operacional.

✅ **Gates A–I sealed, 554+ tests passing, mypy clean, deployed in production (Hetzner).**

✅ **Arquitectura sólida**: separation of concerns, graceful degradation, type safety, comprehensive test coverage.

⚠️ **Gaps primarios = escala operacional (Prometheus retention, WAL policy) + auto-mejora (ColdUpdate auto-patch generation).**

⚠️ **Próximas wins de alto valor:**
1. **Hermes webhook** (elimina polling)
2. **ColdUpdate autonomous patch generation** (cierra self-audit loop)
3. **Prometheus documentation** (ADR-024 completo)
4. **KuzuVectorStore HNSW** (scale >10k patterns)

### Recomendación ejecutiva

**Para las próximas 4 semanas:**
1. Documentar Prometheus (2-3 horas) → ADR-024 operacionalizable
2. Hermes webhook (12-16 horas) → Reduce polling CPU
3. ColdUpdate auto-patch (24-32 horas) → Close self-audit loop
4. KuzuVectorStore HNSW (16-24 horas) → Scale

**Status:** Production-ready. Post-MVP improvements = scaling + autonomous self-repair.

---

## APÉNDICE: Comandos de verificación

```bash
cd ~/proyectos/atlas-core && source .venv/bin/activate

# Verificación core
PYTHONPATH=src pytest tests/ -q --ignore=tests/test_browser.py
MYPYPATH=src mypy src/atlas/

# Smoke tests
python scripts/gate_h_smoke.py
python scripts/gate_i_smoke.py
python scripts/operational_smoke.py

# Health check
atlas health

# Self-audit
atlas self-audit run --hours 1 --profile quick --max-cycles 1

# Dashboard
atlas dashboard  # → localhost:7331

# Service
atlas serve     # → :7331 + /api/health + /metrics (if ATLAS_PROMETHEUS=1)
```

---

**Auditoría completada:** 25 de mayo de 2026  
**Siguiente revisión recomendada:** 15 de junio de 2026 (post-week-1 actions)
