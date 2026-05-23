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
- Gate D: IN PROGRESS — 187 tests passing + mypy verde.
  - D1 InferenceHub real (LiteLLM): DONE. Modo auto/live/stub, fallback chain, cooldown rate-limit, clasificación de errores. Smoke real PASS contra Groq (llama-3.3-70b + qwen3-32b) y OpenRouter (nemotron-nano-12b + liquid-1.2b).
  - D2 SLM classifier (reemplazar rule-based): PENDING — ADR-010 abierto.
  - D3 Capability tokens + AtlasExecutor (ADR-020): DONE. `src/atlas/security/{capabilities,executor}.py` + 31 tests. Issuer valida contra PermissionProfile/SSRFBridge, executor canaliza IO con audit log. Refactor del pipeline existente para enrutar via executor queda como follow-up.
  - D4 Memoria vectorial KuzuDB: PENDING — ADR-008 (decisión tomada, código no escrito).
  - D5 Time-Travel Debugging + Ghost Replay: PENDING — ADR-021, ADR-022.
  - D6 PII Surrogate (temperature=0): PENDING — ADR-023.
  - D7 Cierre Gate D + tag v0.3-gate-d: PENDING.
  - MemoryDistiller: PENDING — ADR-018, depende de D4.
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
│   │   └── inference_hub.py    # Model router L-det->L0->L1->L2 (stub in v0.1)
│   ├── governance/
│   │   ├── governance_l0.py    # Immutable constitution — singleton, tamper-detection
│   │   └── permission_profile.py  # Folder map ADR-006, AUTO/CONFIRM/APPROVE levels
│   ├── router/
│   │   └── classifier.py       # Deterministic rule-based router
│   ├── security/
│   │   ├── ast_guard.py        # Static AST validation before execution (microseconds)
│   │   ├── capabilities.py     # Frozen Pydantic tokens (Read/Write/Network/Exec) + CapabilityIssuer (ADR-020)
│   │   ├── executor.py         # AtlasExecutor — IO con token tipado + audit log (ADR-020)
│   │   ├── sandbox.py          # Layered isolation: NORMAL (subprocess) / DEGRADED (stub)
│   │   └── ssrf_bridge.py      # Secure egress with domain allowlist
│   ├── logging/
│   │   └── merkle_logger.py    # Forensic SHA-256 append-only logger
│   ├── memory/
│   │   └── memory_system.py    # SystemContextLoader, ErrorRegistry, ApprovedPatternStore,
│   │                           # ProviderMetricsStore, ToolRegistry
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
│   └── test_capabilities.py            # 31 tests — Gate D/D3
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
    └── gate_c_seal.md          # Seal cierre Gate C (2026-05-23)
```

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
ADR-008  Vector + graph memory: KuzuDB (decisión tomada; código pendiente Gate D/D4)
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
ADR-010  SLM classifier model selection — Gate D/D2
ADR-012  Memory sync between Hermes and Atlas Core — Gate D
ADR-018  Memory Distiller — Gate D (deferred, depende D4)
ADR-019  Statistical Validation Framework — Gate D/E
ADR-021  Time-Travel Debugging with checkpoints and branching — Gate D/D5
ADR-022  Ghost Replay caching for cost/latency reduction — Gate D/D5
ADR-023  PII Surrogate substitution with temperature=0 — Gate D/D6

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
PYTHONPATH=src python -m pytest tests/ -q           # full suite (187 tests)
PYTHONPATH=src python -m pytest tests/ -k "thermal" # filtered
MYPYPATH=src python -m mypy src/atlas/              # type check (debe pasar verde)

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
