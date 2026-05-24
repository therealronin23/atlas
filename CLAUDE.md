# ATLAS CORE — Context for Claude Code

> This file is the first thing Claude Code reads at the start of every session.
> All component names here are technical and descriptive. Narrative aliases exist
> only in human-facing documentation, never in code or instructions to AI tools.

## What Atlas Is

Atlas is a sovereign local intelligence runtime. It is not a chatbot, not an LLM wrapper,
not a SaaS product. It coordinates free and local models to achieve frontier-level output
without paying for frontier APIs. Atlas decides. Hermes-VPS executes. All external
components serve Atlas, not the other way around.

## Project Status

- Gate A: SEALED — Vision, entities and principles locked.
- Gate B: COMPLETE — Local core functional.
- Gate C: COMPLETE — 147 tests passing + Hermes-VPS live on Hetzner CPX22 + Tailscale tunnel verified end-to-end.
  - C1 install_hermes_vps.sh: DONE + deployed (Hetzner CPX22, Ubuntu 26.04 LTS).
  - C2 Tailscale: DONE — tailnet `hermes-vps` ↔ `ronin-omen-by-hp-laptop`. `HERMES_BASE_URL` apunta a IP `100.x` interna.
  - C3 HermesRestAdapter: DONE. REST + HMAC-SHA256 + retry + OfflineQueue fallback. Smoke test contra el stub real PASS.
  - C4 Telegram bot: DONE (both sessions). Orchestrator↔bot via EventBus, approval flow with inline buttons, `OfflineMonitor`, `/pending`.
  - C5 cierre + tag v0.2-gate-c: DONE. Evidencia en `docs/gate_c_seal.md`.
- Gate D: COMPLETE — 368 tests passing + mypy verde + tag v0.3-gate-d.
  - Cableo Orchestrator integrando todas las piezas Gate D: DONE (opt-in).
    `Orchestrator.enable_gate_d_pipeline(inference_hub=...)` o env var
    `ATLAS_PIPELINE_GATE_D=1` activa la cadena completa:
    ghost-lookup -> hybrid-classify (rule+SLM con winner explícito en
    Merkle) -> route -> execute (LOCAL_SAFE via InferenceHub real con
    MemoryDistiller + PIISurrogate redact/restore) -> ghost-record ->
    timetravel-snapshot. 21 tests pipeline + 7 hybrid/B.
  - Smoke real end-to-end: `scripts/pipeline_smoke.py` corre 5 intents
    contra Groq + OpenRouter vivos. Evidencia: intent ambiguo "explicame
    Merkle tree" -> rule (0.6) -> SLM consulta Groq -> SLM wins -> LOCAL_SAFE
    via inference_hub.complete con respuesta de 337 tokens en 1.1s.
  - D1 InferenceHub real (LiteLLM): DONE. Modo auto/live/stub, fallback chain, cooldown rate-limit, clasificación de errores. Smoke real PASS contra Groq (llama-3.3-70b + qwen3-32b) y OpenRouter (nemotron-nano-12b + liquid-1.2b).
  - D2 SLM classifier (ADR-010): DONE. `src/atlas/router/slm_classifier.py` + 21 tests. Wrapper sobre InferenceHub con prompt estructurado, parseo robusto del JSON (tolera fences markdown y texto envolvente), modo auto/live/stub, cache opcional via GhostReplay. Pensado como complemento del rule-based — el cableo hibrido en el pipeline (regex primero, SLM si confidence baja) queda como follow-up.
  - D3 Capability tokens + AtlasExecutor (ADR-020): DONE. `src/atlas/security/{capabilities,executor}.py` + 31 tests + 5 integración Orchestrator. Issuer valida contra PermissionProfile/SSRFBridge, executor canaliza IO con audit log. Refactor del pipeline existente para enrutar via executor queda como follow-up.
  - D4 Memoria vectorial KuzuDB (ADR-008): DONE. `src/atlas/memory/{embeddings,vector_store}.py` + 34 tests + 7 integración. StubEmbedder (hash-based determinista) y LiteLLMEmbedder (auto/live/stub). KuzuVectorStore con schema Pattern/Failure/Evidence + REL tables. ErrorRegistry y ApprovedPatternStore aceptan vector_store opcional (mirror automático + `find_similar`).
  - MemoryDistiller (ADR-018): DONE. `src/atlas/memory/distiller.py` + 17 tests. Comprime contexto pre-LLM por relevancia (cosine sim contra el query) respetando budget de tokens. System chunks intocables, recent preservado, scorables filtrados. Hook con KuzuVectorStore via gather_relevant() y build_context() end-to-end. Cableo automatico al Orchestrator queda como follow-up.
  - D5 Time-Travel + Ghost Replay: DONE.
    - ADR-021 (Time-Travel): `src/atlas/core/{checkpoint,timetravel}.py` + 22 tests. Checkpoints inmutables encadenados por hash (`hash_self`, `hash_prev`, `verify_chain`). Persistencia JSON. `fork()` para counterfactuales. Cada save/fork log a Merkle.
    - ADR-022 (Ghost Replay): `src/atlas/core/ghost_replay.py` + 21 tests. Cache topológica con clave = SHA-256(intent, sensitivity, context_signature). TTL configurable, LRU automática por `max_entries`, `purge()` para presión de memoria. Stats hits/misses.
    - Integración con Orchestrator (interceptar handle_intent para lookup en GhostReplay antes de inferir, snapshot a TimeTravel en cada paso) queda como follow-up.
  - D6 PII Surrogate (ADR-023): DONE. `src/atlas/security/pii_surrogate.py` + 33 tests. Detección regex (email, DNI ES, IBAN, teléfono ES, IPv4/v6, API keys Groq/OpenRouter/Hermes) + sustitución determinista por surrogates que preservan formato (DNI con letra válida, IPv4 en TEST-NET-1, IPv6 en 2001:db8::/32). Salt via `ATLAS_PII_SALT`. Redact + restore roundtrip. Detección por SLM (nombres, ciudades) queda como follow-up v2.
  - D7 Cierre Gate D + tag v0.3-gate-d: DONE. Evidencia en `docs/gate_d_seal.md`.
- Gate E: PENDING — Local environment (Proxmox decision) + Dashboard + Voice.
- Gate F: PENDING — Computer-use + Editor integration + Frontend.

## Project Structure

```
atlas-core/
├── src/atlas/
│   ├── core/
│   │   ├── contracts.py        # Task, Event, Tool, DelegationPayload, OperationalMode
│   │   ├── orchestrator.py     # Executive coordinator — runs the full pipeline
│   │   ├── event_bus.py        # Typed in-process event bus
│   │   ├── offline_monitor.py  # Polls hermes.check_offline_fallback() -> SHADOW_ALERT (Gate C/C4-s2)
│   │   ├── inference_hub.py    # Model router L-det->L0->L1->L2 + LiteLLM (Gate D/D1)
│   │   ├── checkpoint.py       # Hash-chained immutable checkpoints (ADR-021)
│   │   ├── timetravel.py       # TimeTravel facade: record/resume/fork (ADR-021)
│   │   └── ghost_replay.py     # Topological cache: TTL + LRU + purge (ADR-022)
│   ├── governance/
│   │   ├── governance_l0.py    # Immutable constitution — singleton, tamper-detection
│   │   └── permission_profile.py  # Folder map ADR-006, AUTO/CONFIRM/APPROVE levels
│   ├── router/
│   │   ├── classifier.py       # Deterministic rule-based router
│   │   └── slm_classifier.py   # SLM-based classifier via LiteLLM (ADR-010)
│   ├── security/
│   │   ├── ast_guard.py        # Static AST validation before execution (microseconds)
│   │   ├── capabilities.py     # Frozen Pydantic tokens (Read/Write/Network/Exec) + CapabilityIssuer (ADR-020)
│   │   ├── executor.py         # AtlasExecutor — IO con token tipado + audit log (ADR-020)
│   │   ├── pii_surrogate.py    # PII detection + surrogate substitution (ADR-023)
│   │   ├── sandbox.py          # Layered isolation: NORMAL (subprocess) / DEGRADED (stub)
│   │   └── ssrf_bridge.py      # Secure egress with domain allowlist
│   ├── logging/
│   │   └── merkle_logger.py    # Forensic SHA-256 append-only logger
│   ├── memory/
│   │   ├── memory_system.py    # SystemContextLoader, ErrorRegistry, ApprovedPatternStore,
│   │   │                       # ProviderMetricsStore, ToolRegistry
│   │   ├── embeddings.py       # StubEmbedder + LiteLLMEmbedder (Gate D/D4)
│   │   ├── vector_store.py     # KuzuVectorStore — schema + búsqueda semántica (ADR-008)
│   │   └── distiller.py        # MemoryDistiller — compresión semántica pre-LLM (ADR-018)
│   ├── hermes/
│   │   └── hermes.py           # HermesAdapter (abstract) + Mock + RestAdapter (Gate C)
│   │                           # + OfflineQueue + OfflineFallbackMode (Dead Man Switch)
│   ├── thermal/
│   │   └── watchdog.py         # ThermalWatchdog + OperationalMode (NORMAL/DEGRADED/OMEGA)
│   └── interfaces/
│       ├── cli.py                 # CLI: atlas status/task/tools/memory/audit
│       ├── telegram_bot.py        # Bot stdlib (Gate C/C4) — dispatcher + approval inline keyboard + EventBus hooks
│       └── orchestrator_ops.py    # OrchestratorOps: AtlasOps adapter over Orchestrator (Gate C/C4-s2)
├── tests/
│   ├── conftest.py                     # Aislamiento de API keys externas
│   ├── test_atlas_core.py              # 64 tests
│   ├── test_gemini_components.py       # 38 tests
│   ├── test_hermes_rest_adapter.py     # 11 tests — Gate C/C3
│   ├── test_telegram_bot.py            # 16 tests — Gate C/C4-s1
│   ├── test_telegram_orchestrator.py   # 18 tests — Gate C/C4-s2
│   ├── test_inference_hub_real.py      #  9 tests — Gate D/D1
│   ├── test_capabilities.py            # 31 tests — Gate D/D3
│   ├── test_orchestrator_executor.py   #  5 tests — Gate D/D3 (integración)
│   ├── test_embeddings.py              # 15 tests — Gate D/D4
│   ├── test_vector_store.py            # 19 tests — Gate D/D4
│   ├── test_memory_kuzu_integration.py #  7 tests — Gate D/D4
│   ├── test_distiller.py               # 17 tests — Gate D/MemoryDistiller
│   ├── test_pii_surrogate.py           # 33 tests — Gate D/D6
│   ├── test_timetravel.py              # 22 tests — Gate D/D5.A (ADR-021)
│   ├── test_ghost_replay.py            # 21 tests — Gate D/D5.B (ADR-022)
│   ├── test_slm_classifier.py          # 21 tests — Gate D/D2 (ADR-010)
│   └── test_orchestrator_pipeline_d.py # 14 tests — pipeline Gate D integrado
├── scripts/
│   ├── install_hermes_vps.sh   # Gate C/C1 — Docker + stub agent + systemd in a VPS
│   ├── hermes_smoke.py         # Gate C/C3 — adapter smoke test against real HERMES_BASE_URL
│   ├── inference_smoke.py      # Gate D/D1 — InferenceHub real contra Groq + OpenRouter
│   └── hermes_agent_stub/      # Gate C/C1 — stub HTTP server speaking the REST contract
├── config/
│   ├── governance.json         # Immutable constitution (NEVER modify via code)
│   └── permissions.yaml        # Folder map and permission levels
├── memory/system_context/      # DO NOT reference as "trinity_memo" in code
│   ├── 01_vision.md
│   ├── 02_rules.md
│   └── 03_adr.md
└── docs/
    ├── gate_c_seal.md          # Seal cierre Gate C (2026-05-23)
    ├── gate_d_seal.md          # Seal cierre Gate D (2026-05-24)
    └── USAGE.md                # Guía operacional (rama docs/readme-and-usage)
```

> README.md y docs/USAGE.md operacionales viven en rama `docs/readme-and-usage`
> con PR pendiente: https://github.com/therealronin23/atlas/pull/new/docs/readme-and-usage

## Naming Rules (CRITICAL)

Use only the technical names in code, comments, and all AI instructions.
Narrative aliases exist only in human documentation and must never appear in source files.

Technical name (USE THIS)        | Do NOT use in code
---------------------------------|---------------------------------
SystemContextLoader              | TrinityMemo
ErrorRegistry                    | FailureAtlas
ApprovedPatternStore             | PatternLibrary
ProviderMetricsStore             | PerformanceLedger
LayeredIsolationSandbox          | MatrioskaSandbox
OperationalMode.NORMAL           | TriageMode.ALFA
OperationalMode.DEGRADED         | TriageMode.OMEGA
OfflineFallbackMode              | ModoFantasma
(no class — it is a philosophy)  | Mythos

## Coding Rules (non-negotiable)

1. Every action with external effect goes through the Merkle Logger.
2. All generated Python code passes through AST Guard before execution.
3. governance.json is never modified by any agent or runtime instruction.
4. sensitivity="high" always forces REQUIRES_APPROVAL regardless of pattern.
5. OperationalMode.DEGRADED or OMEGA means no local LLM loading; L-det and Hermes only.
6. No new dependencies without explicit ADR or Gate-level approval.
7. Tests before every change. No untested code reaches main.
8. Before editing any file: show plan and proposed diff first.
9. On task completion: run relevant tests, make descriptive git commit, brief summary.

## Resolved ADRs (do not reopen without empirical evidence)

ADR-000  Atlas is the local sovereign. No external component has architectural authority.
ADR-001  Event Bus: in-process pub/sub (resuelto durante Gate C/C4-s2).
ADR-004  First vertical: status + task over Atlas-Hermes contracts.
ADR-005  Permissions: AUTO / CONFIRM / APPROVE / BLOCKED
ADR-006  Workspace ~/atlas/ — .ssh, .gnupg, /etc, /root always blocked
ADR-007  Autonomy: Governance > Permission > Sensitivity > Classify > Execute
ADR-008  Vector + graph memory: KuzuDB (resuelto Gate D/D4 con vector_store.py)
ADR-018  Memory Distiller (resuelto Gate D con distiller.py, compresión pre-LLM)
ADR-021  Time-Travel Debugging (resuelto Gate D/D5.A con checkpoint.py + timetravel.py)
ADR-022  Ghost Replay caching (resuelto Gate D/D5.B con ghost_replay.py)
ADR-023  PII Surrogate (resuelto Gate D/D6 con pii_surrogate.py)
ADR-010  SLM classifier (resuelto Gate D/D2 con slm_classifier.py)
ADR-009  SKILL.md format: agentskills.io standard
ADR-011  Atlas->Hermes: REST HTTPS + HMAC-SHA256. Tailscale tunnel in production
ADR-013  Telegram auth: chat_id whitelist
ADR-013b Computer-use: Playwright + xdotool + Xvfb. Diferido a Gate F.
ADR-014  Layered isolation: Proxmox VE > LXC Atlas Core > Docker NORMAL / VM DEGRADED
ADR-016  InferenceHub: LiteLLM. Fallback chain: Groq>OpenRouter>Together>Gemini>L0
ADR-017  Tunnel: Tailscale (WireGuard)
ADR-020  Capability-based Security Tokens (resuelto Gate D/D3 con Capability* + AtlasExecutor)

## Open ADRs

ADR-002  Local environment Proxmox vs alternatives — Gate E
ADR-003  Voice module timing — Gate E/E3
ADR-012  Memory sync between Hermes and Atlas Core — Gate D
ADR-019  Statistical Validation Framework — Gate D/E

## Architectural Vocabulary

FOCALE control loops  Reactive (ms) / Deliberative (s) / Reflexive (h).
                       See memory/system_context/03_adr.md for mapping to existing components.

## Critical Thresholds

TEMP_NORMAL_THRESHOLD       = 70.0    # Below: NORMAL operational mode
TEMP_DEGRADED_THRESHOLD     = 80.0    # 70-79C: DEGRADED, no heavy LLMs
TEMP_OMEGA_THRESHOLD        = 90.0    # 80C+: full OMEGA restrictions
RAM_DEGRADED_THRESHOLD_MB   = 1024    # Below 1GB free: consider DEGRADED
OFFLINE_FALLBACK_TIMEOUT_MIN = 15     # No ping timeout: OfflineFallbackMode

## Running Tests

cd ~/atlas-core && source .venv/bin/activate
PYTHONPATH=src python -m pytest tests/ -q           # full suite (368 tests)
PYTHONPATH=src python -m pytest tests/ -k "thermal" # filtered
MYPYPATH=src python -m mypy src/atlas/              # type check (debe pasar verde)

# Smoke real end-to-end del pipeline Gate D contra infra viva
set -a && source .env && set +a
PYTHONPATH=src python scripts/pipeline_smoke.py     # 5 intents, output estructurado
PYTHONPATH=src python scripts/inference_smoke.py    # ping por proveedor LLM
PYTHONPATH=src python scripts/hermes_smoke.py       # REST + HMAC contra Hermes-VPS

## Environment Variables

ATLAS_HOME              ~/atlas/          Workspace root
PYTHONPATH              ~/atlas-core/src  Module resolution
GROQ_API_KEY            Gate D            InferenceHub real
OPENROUTER_API_KEY      Gate D            InferenceHub real
TELEGRAM_BOT_TOKEN      Gate C            Bot token
TELEGRAM_CHAT_ID        Gate C            Authorized chat ID
HERMES_BASE_URL         Gate C            VPS endpoint
HERMES_API_KEY          Gate C            Shared HMAC secret
TAILSCALE_AUTH_KEY      Gate C            Tailscale setup

## What to NEVER do

- Connect to Anthropic/Claude API as a runtime dependency of Atlas.
- Modify governance.json from code or agent instructions.
- Skip the AST Guard to simplify anything.
- Add features without mapping them to a Gate or ADR.
- Merge untested code.
- Use narrative names in code: use only the technical names from the naming table above.
