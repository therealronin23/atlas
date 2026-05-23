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
ADR-013b Computer-use: Playwright (browser) + xdotool (Linux GUI) + Xvfb. Deferred Gate F.
ADR-014  Layered isolation: Proxmox VE > LXC Atlas Core > Docker NORMAL / VM DEGRADED.
         NORMAL tier: subprocess isolated, --network none, 512MB RAM, 30s CPU.
         DEGRADED tier: VM + Snapshot + HITL Telegram confirmation.
ADR-016  InferenceHub backend: LiteLLM. Fallback chain: Groq > OpenRouter > Together > Gemini > L0.
ADR-017  Atlas-Hermes tunnel: Tailscale (WireGuard). Hermes IP only visible inside Tailscale network.

## Open ADRs

ADR-002  Local environment: Proxmox vs alternatives — Gate E (empirical decision on real hardware).
ADR-003  Voice module: Whisper + Piper — Gate E/E3.
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
ADR-010  SLM classifier model: Phi-4 vs Qwen-2.5-Coder — Gate D.
ADR-012  Memory sync Hermes <-> Atlas Core — Gate C to D (pull-on-reconnect default).
ADR-015  [Merged into ADR-014] Escalation protocol for DEGRADED/OMEGA tiers.

## Deferred to experiments (Gate D / E)

ADR-018  Memory Distiller.
         Objective: semantic compression of context before sending to inference model,
         reducing cost and latency for L1/L2 calls.
         Reference implementation: atlas-experiments/ouroboros/memory_distiller.py
         Target module: src/atlas/memory/distiller.py
         Activation: once InferenceHub real is operational, this becomes a mandatory
         pre-step before any L1 or L2 call.
         Status: DEFERRED to Gate D.

ADR-019  Statistical Validation Framework.
         Objective: evaluate router and InferenceHub performance using cross-validation
         with multiple seeds and statistical tests. Adapts the scientific trainer
         skeleton from the Omega project.
         Reference implementation: atlas-experiments/omega/atlas_omega_entrenamiento.py
         Target module: src/atlas/lab/evaluator.py
         Status: DEFERRED to Gate D / E.

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
         so any frame can be paused, inspected, mutated, and resumed. Enables
         counterfactual "what-if" experiments without restarting workflows.
         Inspired by LangGraph checkpoint API and agent-vcr.
         Implementation: extend Orchestrator with checkpoint serialization per
         significant logical step. Checkpoints stored in
         ~/atlas/memory/checkpoints/{task_id}/{step_id}.json with ACID guarantees.
         Branching: forking from a checkpoint creates a new task_id linked to
         parent. Git-backed: each checkpoint commit allows filesystem rollback
         beyond memory state.
         Target modules:
           src/atlas/core/checkpoint.py     (serialization + storage)
           src/atlas/core/timetravel.py     (resume + branching API)
         Status: DEFERRED to Gate D.

ADR-022  Ghost Replay caching.
         Objective: cache successful execution paths topologically. When the agent
         faces a semantically identical task or sub-tree previously resolved, skip
         the LLM inference call entirely and return the cached result.
         100% cost savings on repeated subtasks, zero latency.
         Cache key: hash of (task_intent, sensitivity, context_signature).
         Cache value: final result + path of intermediate decisions.
         Invalidation: TTL + manual purge command. The Ghost Replay layer is
         consulted BEFORE InferenceHub. Memory pressure (OperationalMode.DEGRADED)
         drops cache aggressively.
         Target module: src/atlas/core/ghost_replay.py
         Status: DEFERRED to Gate D.

ADR-023  PII Surrogate substitution with deterministic temperature=0.
         Objective: when Atlas processes user data containing PII (personal
         identifiers, names, addresses, financial data), substitute with
         synthetic surrogates BEFORE sending to any L1/L2 inference. Surrogates
         preserve semantic utility (a name stays a name, a city stays a city)
         unlike redaction (asterisks destroy context).
         Implementation: local SLM (Phi-4-mini or Qwen-2.5-3B) running with
         temperature=0.0 and fixed seed ensures the same input always produces
         the same surrogate (deterministic mapping). Maintains ontology coherence
         across multi-turn conversations.
         Reverse mapping stored locally only, never sent to external APIs.
         Target module: src/atlas/security/pii_surrogate.py
         Status: DEFERRED to Gate D.

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
