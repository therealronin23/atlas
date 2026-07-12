# Research 03 — Workflow Canvas

Atlas must have its own Workflow Canvas.

n8n contributes operational primitives: canvas, nodes, triggers, credentials, executions, debug, templates, workflow history, source control, webhooks and integrations.

LangGraph contributes runtime primitives: stateful execution, persistence, HITL, time travel/debug and long-running agents.

Decision:

```text
LangGraph = adapter/runtime opcional.
Atlas Event Kernel = fuente canónica.
Atlas Workflow Spec = contrato propio.
```

Workflow architecture:

```text
Workflow Canvas → Atlas Workflow Spec → Risk & Capability Analysis → Dry Run → Gates → Execution Plan → Event Kernel → Runtime Adapter → Audit Replay + Memory Writes
```
