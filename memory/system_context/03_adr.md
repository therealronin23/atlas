# Atlas — Architecture Decision Records (System Context 03)

## Sealed at Gate A

ADR-000  Atlas is the local sovereign. No external component has architectural authority.
ADR-004  First vertical: status + task over Atlas-Hermes contracts.
ADR-009  SKILL.md format: agentskills.io standard, native in Hermes Agent.

## Resolved at Gate C

ADR-001  Event Bus selection: in-process pub/sub (`src/atlas/core/event_bus.py`).
         Decision empirica: el bus tipado in-process resolvio el caso Orchestrator
         <-> TelegramBot <-> OfflineMonitor sin sumar dependencias. Redis/MQTT
         quedan disponibles si futuras topologias multi-proceso lo justifican.

## Resolved at Gate B

ADR-005  Permissions: AUTO / CONFIRM / APPROVE / BLOCKED with absolute blocked paths.
ADR-006  Workspace: ~/atlas/ — .ssh, .gnupg, /etc, /root always blocked.
ADR-007  Autonomy decision tree: Governance > Permission > Sensitivity > Classify > Execute.
ADR-011  Atlas->Hermes channel: REST HTTPS + HMAC-SHA256 + anti-replay timestamp.
         Tailscale tunnel in production (ADR-017).
ADR-013  Telegram auth: chat_id whitelist + optional passphrase for APPROVE-level tasks.
ADR-013b Computer-use: RESOLVED Gate F (2026-05-25).
         Decision: Playwright-backed BrowserTool, EditorTool via
         PermissionProfile + capability tokens + AtlasExecutor, conservative
         VisionLoop that proposes typed actions but does not run autonomous
         loops, and explicit Orchestrator routes for `browser`, `editor` and
         `vision` commands. Mutating actions require approval. Accepted
         implementation and verification live in docs/adr_013b_computer_use.md
         and docs/gate_f_seal.md.
ADR-014  Layered isolation: Proxmox VE > LXC Atlas Core > Docker NORMAL / VM DEGRADED.
         NORMAL tier: subprocess isolated, --network none, 512MB RAM, 30s CPU.
         DEGRADED tier: VM + Snapshot + HITL Telegram confirmation.
ADR-016  InferenceHub backend: LiteLLM. Fallback chain: Groq > OpenRouter > Together > Gemini > L0.
ADR-017  Atlas-Hermes tunnel: Tailscale (WireGuard). Hermes IP only visible inside Tailscale network.

## Resolved at Gate E

ADR-002  Local environment: bare metal + venv (RESOLVED Gate E, 2026-05-24).
         Decision: Proxmox rejected — i7-6700HQ (2015 laptop) + 15GB RAM insufficient for
         hypervisor overhead. Docker Engine unnecessary — Atlas runs perfectly in venv with
         LayeredIsolationSandbox handling process isolation from code. E1 (Proxmox) skipped.
         Gate E proceeds with E2 (dashboard) + E3 (voice) on bare metal Ubuntu.
ADR-003  Voice module: faster-whisper (STT) + piper-tts (TTS) — RESOLVED Gate E/E3 (2026-05-24).
         Decision: faster-whisper v1+ (CPU int8, modelo small, ~400ms en i7-6700HQ) para STT.
         piper-tts (neural TTS, ~150ms CPU) para TTS. sounddevice para audio I/O.
         Deps opcionales (pip install atlas-core[voice]). Hardware verificado: ALC295 OK.
         Activación manual (Enter) en modo NORMAL. Implementado: src/atlas/interfaces/voice.py.
         30 tests en stub mode (sin hardware). Modos: stub/real/auto.
## Resolved at Gate D

ADR-008  Vector and graph memory: KuzuDB (embedded, C++, MIT license).
         Decision: KuzuDB chosen over ChromaDB/LanceDB/SQLite-vec for combining
         Cypher graph queries + native vector search + FTS5 in a single embedded
         engine. Multi-writer concurrent support enables future multi-agent
         topology without IPC overhead. Runs in-process (no network/server).
         Implementado Gate D/D4 (2026-05-24):
           src/atlas/memory/vector_store.py — KuzuVectorStore con schema
             (Pattern, Failure, Evidence) + REL tables (DERIVED_FROM,
             SUPPORTS, SIMILAR_TO). Cosine similarity calculada en Python
             sobre los vectores almacenados (suficiente hasta ~10k filas;
             HNSW extension de Kuzu queda como follow-up para escala mayor).
           src/atlas/memory/embeddings.py — Embedder protocol + StubEmbedder
             (hash-based determinista) + LiteLLMEmbedder (modo auto/live/stub
             coherente con InferenceHub).
           memory_system.py — ErrorRegistry y ApprovedPatternStore aceptan
             vector_store opcional. Backward compatible.
         Tests: test_vector_store.py (19), test_embeddings.py (15),
           test_memory_kuzu_integration.py (7).
         Status: RESOLVED (Gate D/D4).
ADR-010  SLM classifier.
         Decision Gate D/D2 (2026-05-24): NO fijar un unico SLM local
         por defecto. En su lugar, el SLMClassifier (src/atlas/router/
         slm_classifier.py) se apoya en el InferenceHub (LiteLLM, ADR-016)
         y funciona con cualquier modelo L1 disponible — Groq llama-3.3-70b
         es la opcion natural por latencia (~180ms) y la chain Groq ->
         OpenRouter -> Together -> Gemini absorbe fallos.
         El clasificador NO reemplaza al rule-based Classifier
         (router/classifier.py): es complemento. Patron previsto:
            1. Classifier (regex, microsegundos) corre primero.
            2. Si confidence < umbral o no match, SLMClassifier decide.
            3. GhostReplay (ADR-022) cachea decisiones para intent repetidos.
         Cableo hibrido en handle_intent queda como follow-up.
         Tests: tests/test_slm_classifier.py (21 tests) — modo stub
         determinista, modo live mockeado, parseo JSON robusto (fences,
         prosa envolvente, confidence clamp), cache via GhostReplay,
         fallbacks ante respuestas malformadas.
         Status: RESOLVED (Gate D/D2).
ADR-012  Memory sync Hermes <-> Atlas Core — Gate C to D (pull-on-reconnect default).
ADR-015  [Merged into ADR-014] Escalation protocol for DEGRADED/OMEGA tiers.

## Open / Deferred ADRs

ADR-019  Statistical Validation Framework.
         Objective: evaluate router and InferenceHub performance using cross-validation
         with multiple seeds and statistical tests. Adapts the scientific trainer
         skeleton from the Omega project.
         Reference implementation: atlas-experiments/omega/atlas_omega_entrenamiento.py
         Target module: src/atlas/lab/evaluator.py
         Status: DEFERRED to Gate G/J.

## Deferred to experiments (Gate D / E)

ADR-018  Memory Distiller.
         Objective: semantic compression of context before sending to inference model,
         reducing cost and latency for L1/L2 calls.
         Implementado Gate D (2026-05-24):
           src/atlas/memory/distiller.py — MemoryDistiller + Chunk + ChunkSource +
             DistillationResult. Estrategia v1 (sin LLM secundario):
               1) SYSTEM chunks se preservan siempre (axiomaticos).
               2) RECENT se conserva al final del contexto.
               3) Resto se ranquea por cosine similarity contra el query y se
                  admite mientras quepa en el budget de tokens (estimacion
                  conservadora: ceil(len/4)).
           Helpers: estimate_tokens, gather_relevant (puente con KuzuVectorStore
             para extraer Patterns/Failures/Evidence indexados), build_context
             (flujo end-to-end query -> string listo para inyectar).
         Cableo automatico al Orchestrator (interceptar handle_intent antes
         de cualquier L1/L2) queda como follow-up cuando el pipeline de
         inferencia este consumido por mas codigo del sistema.
         Tests: tests/test_distiller.py (17 tests).
         Status: RESOLVED (Gate D, distiller v1).


## Technical notes (permanent)

- MerkleLogger format: flat record with fields id, action, agent, result,
  risk_level, payload, hash_prev, hash_self, timestamp. No wrapper data:{}.
- RoutingLevel: use DETERMINISTIC_TOOL (not L_DET). Alias available for compat.
- sensitivity="high" always forces REQUIRES_APPROVAL before the classifier.
- OperationalMode thresholds: <70C NORMAL, 70-79C DEGRADED, >=80C OMEGA.
- SSRFBridge applies to Atlas Core only. Hermes-VPS has its own egress model.
- OfflineFallbackMode activates if Atlas Core has not pinged Hermes in 15 minutes.
- Narrative naming is reserved for human documentation only. All code uses
  technical names exclusively (see CLAUDE.md naming table).

ADR-020  Capability-based Security Tokens.
         Tokens inmutables (Pydantic frozen=True) que encapsulan permiso
         pre-validado para acciones concretas. CapabilityIssuer emite tokens
         tras consultar PermissionProfile (ADR-006) y SSRFBridge.
         AtlasExecutor acepta SOLO tokens tipados (Read/Write/Network/Exec),
         hace el IO real y registra cada accion en MerkleLogger.
         AST Guard sigue activo como backstop cuando la capability transporta
         codigo Python ejecutable.
         Modulos implementados:
           src/atlas/security/capabilities.py  (token definitions + Issuer)
           src/atlas/security/executor.py      (AtlasExecutor)
         Tests: tests/test_capabilities.py (31 tests).
         Cableado en Orchestrator via properties .executor y .capability_issuer.
         Migracion del pipeline existente (Orchestrator y Hermes) para enrutar
         IO via AtlasExecutor queda como follow-up tras D4.
         Status: RESOLVED (Gate D/D3, 2026-05-23).

## Gate F concepts (not yet ADRs — require Gate D completion first)

eBPF  (Extended Berkeley Packet Filter): compile syscall restrictions directly into
      the Linux kernel (WSL2/native). Intercepts sys_connect, sys_execve at silicon
      level. Zero latency overhead, unhackable from user space. Designated as the
      final physical security layer when Atlas reaches full autonomy. Gate F.

ColdUpdateManager  (formerly OuroborosUpdate): cold mutation protocol for Atlas
      self-improvement. Process: hibernate > snapshot > generate N+1 in isolation >
      benchmark against deterministic test suite > HITL approval > atomic swap.
      Rollback: restore from snapshot if regression detected. Gate F.


## New ADRs (formalized from chat sessions, May 2026)

ADR-021  Time-Travel Debugging with checkpoints and branching.
         Objective: persist agent execution as a continuous thread of checkpoints
         so any frame can be paused, inspected, mutated, and resumed.
         Implementado Gate D/D5.A (2026-05-24):
           src/atlas/core/checkpoint.py — Checkpoint dataclass + CheckpointStore.
             Persistencia JSON en <base>/<task_id>/<step_id>.json. Cada
             checkpoint lleva hash_prev del paso anterior (GENESIS_HASH si es
             el primero) y hash_self computado sobre la forma canonica del
             registro. verify_chain(task_id) detecta tampering. fork(from_task,
             from_step) clona estado a un nuevo task como punto de partida.
           src/atlas/core/timetravel.py — TimeTravel facade. new_task crea
             task + step "start". record_step persiste estado intermedio.
             resume_from devuelve el state del checkpoint. fork crea rama
             counterfactual. list_history (HistoryEntry resumido), list_tasks,
             verify_chain. Cada save/fork queda registrado en MerkleLogger
             con accion timetravel.task_started / .checkpoint / .fork.
         Tests: tests/test_timetravel.py (22 tests).
         Integracion automatica en Orchestrator (snapshot por cada accion de
         handle_intent) queda como follow-up tras el cableo de D3/D4/Distiller.
         Status: RESOLVED (Gate D/D5.A).

ADR-022  Ghost Replay caching.
         Objective: cache successful execution paths topologically. Skip LLM
         inference when a semantically identical task is repeated.
         Implementado Gate D/D5.B (2026-05-24):
           src/atlas/core/ghost_replay.py — GhostReplay + GhostEntry +
             compute_cache_key. Cache key = SHA-256(intent | sensitivity |
             context_signature) sobre separador 0x1F (unit separator).
             Storage: <base>/<hash[:2]>/<hash>.json para distribuir en
             subdirectorios. Politicas v1:
               - TTL absoluto por entrada (default 24h, configurable).
               - LRU por tamano via max_entries (default 10000, evict mas
                 antiguo por last_accessed cuando se supera).
               - purge(reason) para drop total (pensado para
                 OperationalMode.DEGRADED).
               - expire() borra solo entradas caducadas.
             stats() devuelve hits/misses/evictions/expired/entries.
             Thread-safe via lock de grano grueso.
         Tests: tests/test_ghost_replay.py (21 tests) — cache key determinista,
         lookup/record/hit/miss, TTL expiration y casos limite (ttl=0 no
         expira), purge total, LRU eviction, tolerancia a JSON corruptos.
         Integracion en el pipeline (consultar antes de InferenceHub.infer y
         record() tras inferencias exitosas) queda como follow-up.
         Status: RESOLVED (Gate D/D5.B).

ADR-023  PII Surrogate substitution with deterministic temperature=0.
         Objective: when Atlas processes user data containing PII (personal
         identifiers, names, addresses, financial data), substitute with
         synthetic surrogates BEFORE sending to any L1/L2 inference. Surrogates
         preserve semantic utility (a name stays a name, a city stays a city)
         unlike redaction (asterisks destroy context).
         Implementado Gate D/D6 (2026-05-24) — v1 sin SLM (determinismo
         puro):
           src/atlas/security/pii_surrogate.py — PIISurrogate + PIIType +
             PIIMatch + RedactionResult. Deteccion regex para EMAIL,
             PHONE_ES (+34 prefix opcional), DNI (8 digits + checksum
             letter), IBAN, IPV4/IPV6, y keys de proveedor (Groq /
             OpenRouter / Hermes). Sustitucion determinista via
             SHA-256(salt|tipo|original) + pools curados que preservan
             formato (DNI con letra valida, IPv4 en TEST-NET-1 192.0.2/24,
             IPv6 en 2001:db8::/32, telefonos con prefijo +34). Mismo
             salt + mismo original -> mismo surrogate (coherencia ontologica
             multi-turn). Salt configurable via ATLAS_PII_SALT.
         Reverse mapping vive solo en RedactionResult.mapping (en memoria);
         no se persiste por defecto.
         v2 follow-up: detector basado en SLM (Phi-4-mini / Qwen-2.5-3B)
         con temperature=0 y seed fijo para nombres, ciudades y otros
         PII semanticos que el regex no captura. ADR-023 original menciona
         esto como nucleo; aqui esta diferido a v2 porque requiere modelo
         local y no es bloqueante para Gate D.
         Tests: tests/test_pii_surrogate.py (33 tests) — deteccion por tipo,
         determinismo, formato valido de surrogates, redact+restore roundtrip,
         configurabilidad y edge cases.
         Status: RESOLVED v1 (Gate D/D6). v2-SLM diferido sin bloquear.

## Architectural vocabulary (no code, naming convention)

FOCALE control loops  Formal taxonomy for the three nested control loops
                       Atlas already has implicitly:
                       - Reactive loop  (ms-scale): hardware/kernel emergencies,
                         OperationalMode.OMEGA transitions, abort/kill paths.
                         Implemented in: ThermalWatchdog, GovernanceL0.
                       - Deliberative loop (s-scale): task classification, routing,
                         tool selection, capability validation.
                         Implemented in: Orchestrator, Classifier, InferenceHub.
                       - Reflexive loop (h-scale): self-evaluation, pattern
                         consolidation, performance metrics, cold updates.
                         Implemented in: ProviderMetricsStore, ApprovedPatternStore,
                         (Gate F) ColdUpdateManager.
                       Use this vocabulary when documenting cross-cutting concerns.
