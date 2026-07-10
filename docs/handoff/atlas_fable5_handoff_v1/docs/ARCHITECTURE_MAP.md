# Atlas OS — Architecture Map

## Definición

Atlas OS es un entorno cognitivo soberano que transforma intención, memoria, herramientas, agentes, datos, procesos, decisiones y cuentas conectadas en un sistema operativo vivo, auditable y extensible.

## Macroarquitectura

```text
Atlas OS
├─ Cognitive Kernel
│  ├─ Intent interpretation
│  ├─ Context assembly
│  ├─ World state reasoning
│  └─ Territory routing
│
├─ Event Kernel
│  ├─ AtlasEvent schema
│  ├─ Event store
│  ├─ Event reducer
│  ├─ Replay
│  └─ Projections
│
├─ Memory OS
│  ├─ Episodic Memory
│  ├─ Semantic Memory
│  ├─ Procedural Memory
│  ├─ Failure Memory
│  ├─ Identity Memory
│  ├─ Project Memory
│  ├─ Trust Memory
│  ├─ Conflict Memory
│  └─ Forgetting Engine
│
├─ Execution Kernel
│  ├─ Plan generation
│  ├─ Plan critique
│  ├─ Capability selection
│  ├─ Step execution
│  ├─ Observation
│  ├─ Validation
│  ├─ Replanning
│  └─ Artifact generation
│
├─ Governance Kernel
│  ├─ Gates
│  ├─ Policy DSL
│  ├─ Permission Matrix
│  ├─ Risk classifier
│  ├─ Human approval
│  ├─ Capability tokens
│  ├─ Audit log
│  └─ Incident simulation
│
├─ Capability Fabric
│  ├─ Native tools
│  ├─ MCP tools
│  ├─ CLI tools
│  ├─ External APIs
│  ├─ Local services
│  ├─ Model providers
│  └─ Health/risk scoring
│
├─ Integration Fabric
│  ├─ Connected accounts
│  ├─ OAuth/API credentials
│  ├─ External AI accounts
│  ├─ Messaging connectors
│  ├─ Files/docs connectors
│  ├─ Communication channels
│  └─ Sync jobs
│
├─ Agent Society Layer
│  ├─ Agent identity
│  ├─ Roles
│  ├─ Authority scopes
│  ├─ Handoffs
│  ├─ Deliberation
│  ├─ Dissent preservation
│  └─ Escalation
│
├─ Visual Representation Layer
│  ├─ Living Knowledge Graph
│  ├─ Execution Pipeline
│  ├─ Timeline
│  ├─ Memory Vault
│  ├─ Visual Orchestrator
│  ├─ Control Center
│  └─ Developer Console
│
└─ Improvement Radar
   ├─ SOTA registry
   ├─ Product/repo/paper dissection
   ├─ Primitive extraction
   ├─ Limitation analysis
   ├─ Atlas reinterpretation
   └─ Superiority tests
```

## Regla

La UI no es la arquitectura. La UI representa los eventos, el estado, la memoria, las capacidades y el gobierno de Atlas.
