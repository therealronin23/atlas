# Atlas Absorption Master Plan

**Source material:** distilled from `grok.md`.
**Status:** planning document, not a Gate seal.
**Rule:** absorb patterns, not uncontrolled dependencies.

`grok.md` is a raw research dump. It should not be committed as canonical
documentation: it contains exported chat UI, obsolete status, repeated advice,
and personal metadata. This file is the cleaned plan.

## Strategy

Atlas should study external projects as references, then reimplement only the
parts that fit the existing architecture:

- Governance L0 stays above every imported idea.
- External-effect actions go through capability tokens and AtlasExecutor.
- Security-sensitive execution goes through AST Guard and sandbox policy.
- Important actions are logged through MerkleLogger.
- New dependencies require explicit ADR or Gate-level approval.
- No runtime dependency on Anthropic/Codex/OpenAI APIs.

## Categories

| Category | References | Atlas target | Gate | Current stance |
|---|---|---|---|---|
| Orchestration and reasoning | LangGraph, AutoGen, CrewAI, MetaGPT | Orchestrator graph patterns, conditional routing, HITL checkpoints | F/G | Study patterns; avoid LangChain lock-in |
| Tool execution and computer-use | Open Interpreter, Playwright, Aider | BrowserTool, EditorTool, visual loop, code execution | F | Highest immediate value; hardening first |
| Inference serving and optimization | vLLM, TensorRT-LLM, BentoML/OpenLLM, Outlines, llama.cpp | InferenceHub backends, structured output, metrics | D/FU | Optional backends after Gate F hardening |
| Interfaces and UX | Aiogram, FastAPI+HTMX, Whisper.cpp, Piper, Gradio | Telegram, dashboard, voice, CLI/API UX | E/F | Incremental UX; keep localhost/Tailscale |
| Environment and deployment | Proxmox, LXC, Docker Compose, Podman, NixOS | reproducible deploy, isolation, backup | F/G | Bare metal is current; deployment plan for production |
| Self-improvement | Aider, Letta, Open Interpreter, ColdUpdateManager | cold update protocol, HITL, rollback | F/G | Do not self-patch; design ADR first |
| Observability and maintenance | Prometheus, Grafana, OpenTelemetry, Loki, Netdata | metrics, tracing, alerting, audit export | F/G | Start small; avoid monitoring sprawl |

## Project Absorption Matrix

| Project | Absorb | Do not absorb | First useful deliverable |
|---|---|---|---|
| Hermes Agent | skill system patterns, Telegram UX, queue/fallback, long-running agent lessons | weak governance, direct execution, loose logging | `SkillRegistry` design note after Gate F hardening |
| Letta | block memory, archival memory, relevance/recency ranking, context management | conversational-agent assumptions, weak audit/security | `memory/block_memory.py` proposal |
| Open Interpreter | visual loop, tool UX, streaming action trace, confirmation patterns | permissive code execution, direct shell/file access | secure visual loop proposal |
| KERI/ACDC | key-event receipts, witness concepts, offline verification, key rotation ideas | full SSI stack, blockchain-like complexity | ADR-024 logging v2 |
| BentoML/OpenLLM | provider health checks, routing metrics, circuit breakers, serving observability | production platform overhead, Kubernetes assumptions | InferenceHub metrics/circuit-breaker backlog |
| LangGraph | graph-shaped execution, conditional edges, checkpoint patterns | LangChain dependency footprint | Orchestrator StateGraph design sketch |
| Aider | repo editing workflow, patch review, git discipline | autonomous merge/push without HITL | ColdUpdateManager validation workflow |

## Priority Order

1. **Gate F hardening**: BrowserTool and EditorTool become auditable, permissioned tools.
2. **ADR-013b update**: formalize computer-use boundaries before visual loop.
3. **Visual loop MVP**: screenshot -> VLM/stub -> proposed action -> approval.
4. **ADR-024**: logging/observability v2, including MicroLedger/TelemetryBus/WAL.
5. **ADR-025**: ColdUpdateManager, with no hot self-modification.
6. **InferenceHub improvements**: health metrics, structured output, optional local backends.
7. **Deployment/production profile**: Docker/Proxmox/Tailscale/backup docs.

## Non-Goals

- No full forks copied into `src/atlas/`.
- No self-AST patching.
- No direct command execution outside AtlasExecutor.
- No public network exposure of dashboards or agents by default.
- No large framework dependency unless an ADR justifies it empirically.

