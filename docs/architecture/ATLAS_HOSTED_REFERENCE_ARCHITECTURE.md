# Atlas Hosted Reference Architecture — RC2 candidate

Status: proposed by ADR-072. Target base: `d01d4b931fd7f02af81a32c63c889d35f574fcab`.

## Purpose

This architecture does not pretend Atlas is greenfield. It defines target
ownership boundaries for an existing system with working Orchestrator,
InferenceHub, EventBus, OsEventStore, PolicyEngine, GateEngine, three canonical
memory use cases, Mission Layer, Golden Route, ColdUpdate and multiple surfaces.

## Six layers

1. **Hosted Guardian**: proposed non-cognitive supervision, safe mode, update
   promotion and rollback.
2. **Trunk µCore**: minimal technical identities, handles, channels, leases,
   deadlines, cancellation, hard budgets and mandatory emission.
3. **Trunk System Services**: task/mission, event/evidence, policy/gates,
   runtime, secrets, models/resources, memory/knowledge and updates.
4. **Atlas Cognition**: planning, research, deliberation, agent coordination
   and domain intelligence. It cannot perform privileged effects directly.
5. **Providers**: model APIs, local models, MCP, ACP, connectors, tools,
   sandboxes and external services behind Atlas contracts.
6. **Surfaces**: CLI, web harness and final dedicated Linux/Android apps.

Complete Trunk means layers 2 and 3 together.

## Current-to-target convergence

| Current component | Current fact | Target |
|---|---|---|
| Orchestrator | Coordinates cognition and several operational concerns | Retain cognition; migrate durable task/runtime/provider ownership |
| EventBus + OsEventStore + transparency | Separate event/evidence authorities | Correlated Event/Evidence Plane with distinct records |
| PolicyEngine + legacy evaluator | Incremental dual path under ADR-062 | One Policy Service plus explicit compatibility adapter |
| GateEngine | Real human ticket lifecycle | Gate Service used by every gated effect |
| Sqlite/Kuzu/BlockMemory | Canonical by use case under ADR-057 | Coordinated Memory/Knowledge Fabric without premature fusion |
| InferenceHub | Real provider routing | Model Service behind Atlas contracts |
| ColdUpdate + GoldenRoute | Real self-construction path | Update Service supervised by Hosted Guardian |
| Web shell | Validation harness | Retain as harness; final UX is dedicated Linux/Android apps |

## Migration rule

For each authority:

1. Observe current callers and state.
2. Define the target contract.
3. Add an adapter around the current implementation.
4. Run shadow or comparison paths where meaningful.
5. Migrate consumers.
6. Retire the old authority.
7. Remove compatibility only after evidence and rollback exist.

No phase is authorized to delete historical sources or rewrite the entire
system merely to match this diagram.
