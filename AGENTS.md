# ATLAS CORE — Context for Codex

> This file is the first thing Codex reads at the start of every session.
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
- Gate D: COMPLETE — 368 tests passing + mypy verde + tag v0.3-gate-d. (509 total with Gate F complete)
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
  - MemoryDistiller (ADR-018): DONE. `src/atlas/memory/distiller.py` + 17 tests. Comprime contexto pre-LLM por relevancia (cosine sim contra el query) respetando budget de tokens. System chunks intocables, recent preservado, scorables filtrados. Hook con KuzuVectorStore via gather_relevant() + build_context(). Cableo en `enable_gate_d_pipeline()` con `ATLAS_MEMORY_VECTOR` (default on).
  - D5 Time-Travel + Ghost Replay: DONE.
    - ADR-021 (Time-Travel): `src/atlas/core/{checkpoint,timetravel}.py` + 22 tests. Checkpoints inmutables encadenados por hash (`hash_self`, `hash_prev`, `verify_chain`). Persistencia JSON. `fork()` para counterfactuales. Cada save/fork log a Merkle.
    - ADR-022 (Ghost Replay): `src/atlas/core/ghost_replay.py` + 21 tests. Cache topológica con clave = SHA-256(intent, sensitivity, context_signature). TTL configurable, LRU automática por `max_entries`, `purge()` para presión de memoria. Stats hits/misses.
    - Integración con Orchestrator (interceptar handle_intent para lookup en GhostReplay antes de inferir, snapshot a TimeTravel en cada paso) queda como follow-up.
  - D6 PII Surrogate (ADR-023): DONE. `src/atlas/security/pii_surrogate.py` + 38 tests. Detección regex + SLM NAME/CITY/ADDRESS via `InferenceHub` cuando Gate D activo (FU-6 DONE).
  - D7 Cierre Gate D + tag v0.3-gate-d: DONE. Evidencia en `docs/gate_d_seal.md`.
- Gate E: COMPLETE — ADR-002 sealed + E2 Dashboard + E3 Voice. 449 tests. tag v0.4-gate-e.
  - E2 Dashboard: DONE. `atlas dashboard` → localhost:7331. FastAPI+Jinja2, 6 páginas + JSON API.
    449 tests. `src/atlas/interfaces/dashboard.py` + `interfaces/templates/`.
  - E3 Voice: DONE. `atlas voice` → STT+TTS loop. faster-whisper+piper-tts como optional extras.
    `pip install 'atlas-core[voice]'` para modo real. Stub mode por defecto (sin hardware).
    `src/atlas/interfaces/voice.py`, 30 tests. ADR-003 sealed.
- Gate F: COMPLETE — Computer-use + Editor integration + Frontend. 509 tests + mypy verde. tag v0.5-gate-f.
- Gate G: COMPLETE — Operational readiness. Hermes-VPS restored/smoked, GitHub synced, CLI approvals persistent (HMAC v1 en `pending_approvals/`), Telegram authorized/smoked. `scripts/operational_smoke.py` + `docs/operational_runbook.md`. Suite: 534+ collected; 522+ core sin Playwright.     tag v0.6-gate-g. Auditoría: `docs/audit_2026-05-25.md`.
- Gate H: MVP COMPLETE (2026-05-25) — H1–H6 audited synthesis. `docs/gate_h_seal.md`, `scripts/gate_h_smoke.py`, `atlas gate-h`. tag `v0.7-gate-h`.
- Debt closure (2026-05-25): FU-6, H6 reuse gating, H5 policy tests, ADR-019, OPS browser marker, SEC verify. `docs/debt_closure_2026-05-25.md`. tag `v0.7.1-debt-closure`.
- Gate I: COMPLETE (2026-05-25) — `atlas serve`, `atlas health`, `/api/health`, `AtlasServiceRunner`, systemd unit. `docs/gate_i_seal.md`, `scripts/gate_i_smoke.py`. tag `v0.8-gate-i`. 550 core tests.
- Gate F details:
  - F1 BrowserTool scaffold: DONE. `src/atlas/tools/browser.py` + `tests/test_browser.py`.
    Pendiente antes de cierre: Merkle logging por accion browser y policy explicita para allowlist extra/local.
  - F2 EditorTool scaffold: DONE. `src/atlas/tools/editor.py` + `tests/test_editor.py`.
    Pendiente antes de cierre: read/write/apply_diff/run_task via PermissionProfile + AtlasExecutor + MerkleLogger.

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
│   ├── test_pii_surrogate.py           # 38 tests — Gate D/D6
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
ADR-013b Computer-use: RESOLVED Gate F (2026-05-25). Playwright BrowserTool,
EditorTool via AtlasExecutor, conservative VisionLoop, explicit Orchestrator
routing and approval states.
ADR-014  Layered isolation: Proxmox VE > LXC Atlas Core > Docker NORMAL / VM DEGRADED
ADR-016  InferenceHub: LiteLLM. Fallback chain: Groq>OpenRouter>Together>Gemini>L0
ADR-017  Tunnel: Tailscale (WireGuard)
ADR-020  Capability-based Security Tokens (resuelto Gate D/D3 con Capability* + AtlasExecutor)

## Open ADRs

ADR-002  RESOLVED Gate E (2026-05-24): bare metal + venv. E1 (Proxmox) skipped.
ADR-003  RESOLVED Gate E/E3 (2026-05-24): faster-whisper + piper-tts. Optional extras [voice].
ADR-012  Memory sync between Hermes and Atlas Core — Gate E
ADR-019  Statistical Validation Framework — Gate E

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

cd ~/proyectos/atlas-core && source .venv/bin/activate
PYTHONPATH=src python -m pytest tests/ -q  # core 550 (excluye marker computer_use por defecto)
PYTHONPATH=src python scripts/operational_smoke.py   # on-host: Hermes + CLI approval + Telegram
PYTHONPATH=src python -m pytest tests/ -k "thermal" # filtered
MYPYPATH=src python -m mypy src/atlas/              # type check (debe pasar verde)

# Smoke real end-to-end del pipeline Gate D contra infra viva
set -a && source ~/proyectos/atlas-core/.env && set +a
PYTHONPATH=src python scripts/pipeline_smoke.py     # 5 intents, output estructurado
PYTHONPATH=src python scripts/inference_smoke.py    # ping por proveedor LLM
PYTHONPATH=src python scripts/hermes_smoke.py       # REST + HMAC contra Hermes-VPS

## Environment Variables

ATLAS_HOME              ~/atlas/                    Workspace root
PYTHONPATH              ~/proyectos/atlas-core/src  Module resolution
GROQ_API_KEY            Gate D            InferenceHub real
OPENROUTER_API_KEY      Gate D            InferenceHub real
TELEGRAM_BOT_TOKEN      Gate C            Bot token
TELEGRAM_CHAT_ID        Gate C            Authorized chat ID
HERMES_BASE_URL         Gate C            VPS endpoint (Tailscale: 100.108.132.116:8443)
HERMES_API_KEY          Gate C            Shared HMAC secret
ATLAS_PIPELINE_GATE_D   Gate D            `1` activa pipeline al arrancar Orchestrator
ATLAS_MEMORY_VECTOR     Gate D            `1` (default) Kuzu con Gate D; `0` desactiva
ATLAS_PENDING_HMAC_KEY  Gate G            Firma pending approvals; fallback HERMES_API_KEY
TAILSCALE_AUTH_KEY      Gate C            Tailscale setup

All env vars live in ~/proyectos/atlas-core/.env (NOT committed). Load with:
  set -a && source ~/proyectos/atlas-core/.env && set +a

## How to Resume (any AI tool: Codex, Cline, Cursor)

1. Activate venv: cd ~/proyectos/atlas-core && source .venv/bin/activate
2. Load env:      set -a && source .env && set +a
3. Verify green:  pytest --ignore=test_browser.py -q  (expect 522+ core; 534+ con browser)
4. Read this file (AGENTS.md) — it is the single source of truth.
5. The ~/.Codex/memory/ files are Codex-specific. Cline/Cursor must rely on this file only.

Current state at session start: Gate I COMPLETE (2026-05-25).
Suite core 550 green (pytest default excluye `computer_use`/Playwright); Gates A–I sellados.
`atlas serve` para 24/7; `atlas health` y `GET /api/health` para supervision.
Next logical work: ADR-025 ColdUpdateManager, ADR-024 observability v2, fleet/Atlas Box.

## Gate D Follow-ups (NON-blocking for Gate E, ordered by effort)

These are known debts. Pick any or skip to Gate E. All have explicit file refs.

| # | Task | File | Effort |
|---|------|------|--------|
| FU-1 | Wire AtlasExecutor into handle_intent (replace raw IO) | `core/orchestrator.py` | DONE (commit bfbd5e4) |
| FU-2 | ADR-012 memory sync Hermes↔Atlas: on-reconnect pull from OfflineQueue | `hermes/hermes.py`, `core/orchestrator.py` | DONE (merge + tests verdes) |
| FU-3 | Suppress LiteLLM startup warnings | `core/inference_hub.py` | DONE (commit 64c878b) |
| FU-4 | InferenceHub L0 real: Ollama HTTP client | `core/inference_hub.py` | DONE (commit c0e2733) |
| FU-5 | SLMClassifier prompt via MemoryDistiller | `router/slm_classifier.py` + `memory/distiller.py` | DONE (commit 35d906f) |
| FU-6 | PIISurrogate: wire InferenceHub en Orchestrator Gate D + hardening SLM live | `security/pii_surrogate.py`, `core/orchestrator.py` | DONE (debt closure 2026-05-25) |

FU-3 is cosmetic and trivial. FU-1 is highest-value correctness fix.

## Gate F — COMPLETE

F1/F2/F3 MVP hardening plus explicit Orchestrator routing are tested locally
and smoked on the real host (suite 509/509 green):

- F1 BrowserTool: Playwright navigation, fill, click, extract and screenshots;
  Merkle logging for browser actions is implemented.
- F2 EditorTool: editor detection, open_project, read/write, apply_diff and
  run_task; read/write/apply_diff/run_task now route through
  PermissionProfile + AtlasExecutor and command execution no longer uses
  public `shell=True`.
- F3 VisionLoop MVP: screenshot -> deterministic/stub description ->
  typed ProposedAction; mutating actions require approval and are not executed.
- Orchestrator Gate F routing: explicit `browser`, `editor` and `vision`
  commands route through approval states; mutating browser/editor actions wait
  in `AWAITING_APPROVAL` until `approve_pending`.
- Real-host smoke: editor read/write/run, browser navigate/screenshot/extract,
  vision propose, Merkle verify, and Ollama L0 (`qwen2.5:0.5b`) passed.

Canonical planning docs:

- `docs/gate_f_plan.md` — Gate F scope, hardening order and acceptance criteria.
- `docs/gate_f_seal.md` — Gate F close evidence.
- `docs/adr_013b_computer_use.md` — resolved computer-use ADR.
- `docs/absorption_master_plan.md` — cleaned absorption/forking strategy distilled from `grok.md`.
- `docs/gate_f_real_world_readiness.md` — host readiness checklist distilled from Gemini notes.
- `docs/gate_g_operational_readiness.md` — current Gate G operational status.
- `docs/gate_g_seal.md` — Gate G close evidence.
- `docs/atlas_box_architecture.md` — Atlas Box hardware/topology concept.
- `docs/fleet_security_plan.md` — future distributed-node security plan.
- `docs/product_strategy_notes.md` — non-legal product/positioning notes.
- `docs/gate_h_resilience_plan.md` — future software synthesis and adaptive resilience plan.
- `docs/adr_024_observability_logging_v2.md` — proposed observability/logging v2.
- `docs/adr_025_cold_update_manager.md` — proposed cold self-improvement protocol.

Gate F close checklist:

1. BrowserTool logs every external action to MerkleLogger. DONE.
2. BrowserTool has explicit approval policy for extra allowlist/local URLs. DONE via `allow_private_network=True`.
3. EditorTool read/write/apply_diff/run_task go through PermissionProfile + AtlasExecutor. DONE.
4. EditorTool command execution removes raw `shell=True` from the public path. DONE.
5. Gate F optional dependencies are represented in packaging/docs. DONE for `computer-use`.
6. Full suite + mypy pass after hardening. DONE (509 tests, 44 source files).
7. Orchestrator routing and approval states for Browser/Editor/VisionLoop. DONE for explicit commands.
8. Real host smoke + ADR-013b/seal. DONE.

## What to NEVER do

- Connect to Anthropic/Codex API as a runtime dependency of Atlas.
- Modify governance.json from code or agent instructions.
- Skip the AST Guard to simplify anything.
- Add features without mapping them to a Gate or ADR.
- Merge untested code.
- Use narrative names in code: use only the technical names from the naming table above.
- Edit AGENTS.md without running tests first (test count must match).
