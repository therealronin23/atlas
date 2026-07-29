# Permanent Programs — Atlas Definitive Candidate

Los programas P00–P12 son líneas permanentes de responsabilidad. Una ola puede
ordenar entregas entre programas, pero no los reemplaza ni convierte P00 en un
cajón para lo difícil de clasificar.

Los estados `current` siguientes son conservadores y se desarrollan en
`STATUS.md`; `target` describe la condición estable buscada.

## P00 — Canon and Governance

**Misión.** Mantener identidad documental, precedencia, decisiones, ownership,
promoción y trazabilidad sin fabricar una autoridad paralela.

**Alcance.** Registro de fuentes/decisiones/conflictos/supersesiones, ADR,
programas, gates, releases, Reality contractual y reglas de promoción. No
posee ejecución, memoria, producto ni protocolos.

**Current.** Constitución distribuida aceptada por ADR-067; ADR y protocolos
operativos reales; registros definitivos y gate CI añadidos por esta candidata.
El paquete R2.1 permanece como semilla propuesta.

**Target.** Una entrada humana, una entrada máquina y proyecciones coherentes;
cada claim enlaza fuente, decisión, implementación, prueba y runtime; ninguna
pieza se autopromociona.

**Componentes.** `ATLAS.md`, authority/decision/conflict registries,
PolicyDecision descriptors, Reality, gate/release registries y ledger.

**Contratos y decisiones.** ADR-067; `CTR-SOURCE-INDEPENDENCE`,
`CTR-LIVE-EVIDENCE`, `CTR-DEPENDENCY-DECISION`,
`CTR-GOVERNANCE-IMMUTABLE`, `CTR-CI-TRACKED-SURFACES`.

**Invariantes.** Scope antes que recencia; fuente primaria antes que copia;
estado actual y objetivo separados; aceptación reservada al operador.

**Dependencias.** Todos los programas publican evidencias y consumen
decisiones; P00 no adquiere su ownership operativo.

**Gates y tests.** `scripts/check_canon.py`, índice documental estricto,
parsing de registros, cobertura P00–P12, atomicidad ADR-076/077, revisión
adversarial y CI.

**Entregables.** Autoridad descubrible, registries, ADR lifecycle, plan,
status y lotes de decisión.

**Riesgos.** Nueva “quinta constitución”, duplicación de verdad, estado
inflado y burocracia sin enforcement.

**Rollback.** Las proyecciones pueden revertirse sin tocar las fuentes
constitucionales; los registros conservan el baseline y la procedencia.

**Finalización.** Nunca termina como programa. Una release está completa
cuando no tiene autoridad duplicada, conflicto oculto ni claim sin evidencia.

## P01 — Institutional Kernel

**Misión.** Encarnar identidad, roles institucionales y autoridad estable por
debajo de modelos, agentes y superficies.

**Alcance.** Policy authority, capability issuance, separación de roles,
identidad institucional y dueños únicos de estado. No planifica tareas ni
ejecuta herramientas.

**Current.** PolicyEngine, Decider, capability/authorization primitives y
governance kernel existen de forma distribuida. El boundary Task/Mission y
algunos owners siguen abiertos.

**Target.** Un núcleo pequeño donde Identity, Policy, Capability y Evidence
tengan interfaces tipadas, dueños únicos y ninguna dependencia de un proveedor
LLM.

**Componentes.** PolicyEngine, Decider contract, CapabilityIssuer/leases,
institutional identities y future µCore boundary.

**Contratos y decisiones.** ADR-040, ADR-062, ADR-063;
`CTR-HIGH-SENSITIVITY`, `CTR-PROTOCOL-GATEWAY`.

**Invariantes.** Cognition no concede permisos; las UIs no son autoridades;
una implementación de Decider no puede anular rule 4; un estado mutable tiene
un dueño.

**Dependencias.** P00 define decisiones; P03 consume Policy; P09 impone
seguridad; P10 autentica peers.

**Gates y tests.** Contract tests Allow/Deny/RequiresHuman, guard high,
revocación de leases, deny-by-default y pruebas de ownership sin doble
escritor.

**Entregables.** Mapa de autoridades, contratos de Policy/Capability y ADR
Mission/Task.

**Riesgos.** Orchestrator como god object, policy duplicada y permisos
inferidos por texto.

**Rollback.** Mantener APIs actuales detrás de adapters; ninguna migración
durable antes del ADR de ownership.

**Finalización.** Owners y boundaries aceptados; ningún protocolo, modelo o
UI puede mutar estado institucional fuera de contrato.

## P02 — Trunk and Context Control

**Misión.** Preparar contexto mínimo, reproducible y verificable para cada
trabajo.

**Alcance.** Grafo Kuzu/AST, freshness, blast radius, Trunk MCP,
ContextPacket/context packs y selección de fuentes. No decide verdad semántica
ni permisos.

**Current.** Grafo y Trunk tienen código y tests. El baseline fue observado
`FRESH`; la candidata requiere refresh tras sus commits. No hay registry de
context packs completo.

**Target.** Todo agente recibe un `ContextPacket` con objetivo, programa,
fuentes, símbolos, dependencias, tests, decisiones, sensibilidad, presupuesto
y freshness.

**Componentes.** ProjectGraph, graph freshness, KuzuVectorStore, Trunk
Aggregator/Server, trunk preflight y Context Compiler.

**Contratos y decisiones.** `CTR-STRUCTURAL-GRAPH`,
`CTR-GRAPHRAG-HYPOTHESIS`; graph-first de `AGENTS.md`.

**Invariantes.** Estructura y semántica no se mezclan; graph stale falla
cerrado para afirmaciones de blast radius; candidato no aparece conectado.

**Dependencias.** P00 para autoridad, P05 para fuentes/claims, P03/P06 para
consumo de context packs, P07 para gateway MCP.

**Gates y tests.** FRESH/DIRTY/STALE/SERVER_STALE, import graph, trunk smoke,
no ejecución durante preflight, límites de tamaño y reproducibilidad por hash.

**Entregables.** ContextPacket schema, compiler, context-pack registry y
freshness receipt por work order.

**Riesgos.** Contexto ilimitado, grafo viejo presentado como vivo y Trunk
convertido en owner de tareas.

**Rollback.** Caer a búsqueda local acotada y marcar `graph_unavailable`; no
usar edges semánticos como sustituto.

**Finalización.** Cada work order ejecutable tiene pack reproducible y el
grafo final coincide con el commit revisado.

## P03 — Cognition Runtime

**Misión.** Coordinar modelos y agentes reemplazables para razonar, planificar
y revisar sin concederles autoridad de efecto.

**Alcance.** InferenceHub, provider routing, Orchestrator, agentic loop,
TaskPersistence y Business Core cognition. Runtime de proceso pertenece a P09.

**Current.** Núcleo amplio, probado y wired; providers locales/stub están
disponibles. El Orchestrator concentra responsabilidades y el owner durable de
Task está abierto.

**Target.** Cognition produce planes y propuestas tipadas; Task Service,
Policy, Runtime y Evidence quedan separados; degradación térmica y de
proveedores es explícita.

**Componentes.** InferenceHub, Orchestrator, provider adapters, task state,
agent loop, planners/reviewers y sector engines.

**Contratos y decisiones.** ADR-016, ADR-031–040, ADR-061/062;
`CTR-THERMAL-DEGRADATION`, `CTR-HIGH-SENSITIVITY`.

**Invariantes.** Un modelo no ejecuta; timeout/cancelación pertenecen al
runtime; high no se permite autónomamente; proveedor externo es sustituible.

**Dependencias.** P01 Policy, P02 context, P04/P05 memory/knowledge, P09
runtime/evidence y P10 peer cognition.

**Gates y tests.** Routing, fallback, thermal modes, cancellation, task
persistence, agent loop, custom-Decider adversarial tests y provider-offline.

**Entregables.** ADR Mission/Task, interfaces Cognition→Policy→Runtime y
reducción progresiva del god object.

**Riesgos.** Mezcla de autoridad, Any silencioso en providers, loops sin límite
y contexto privado enviado fuera.

**Rollback.** Provider local/stub, task state actual y adapters compatibles;
no migrar persistencia sin doble lectura y reversión.

**Finalización.** Un plan no puede producir efecto fuera del seam gobernado y
cada proveedor puede retirarse sin perder identidad o memoria durable.

## P04 — Memory and Continuity

**Misión.** Preservar continuidad útil, privada, temporal y borrable entre
sesiones, proveedores y nodos.

**Alcance.** SQLite memory, BlockMemory, vector retrieval, distillation,
tenancy, cifrado, retención, crypto-shred y promoción hacia conocimiento.

**Current.** Stores y protecciones están implementados/probados; ADR-057
asigna autoridad por caso de uso. Las aperturas Kuzu de Atlas usan un perfil
por defecto explícito de 1 GiB de mapa máximo y 256 MiB de buffer, probado bajo Bwrap de
2 GiB; no existe aún un mapa final ni un pipeline universal de destilación
antes de compartir.

**Target.** Clases de memoria con owner, sensibilidad, tiempo, procedencia,
retención y promoción explícitos; privacidad demostrable y continuidad local.

**Componentes.** SqliteMemoryIndex, BlockMemory, distiller, vector stores,
keystore, tiers y continuity adapters.

**Contratos y decisiones.** ADR-030, ADR-044, ADR-057;
`CTR-PRIVATE-DISTILLATION`, contratos de tenancy y crypto-shred.

**Invariantes.** Memoria privada no entra cruda en grafos compartibles; borrar
incluye índices derivados; recall no convierte contenido en hecho.

**Dependencias.** P03 consume, P05 recibe promoción, P09 protege secretos y
recovery, P10 sincroniza solo bajo lease.

**Gates y tests.** Tenancy isolation, temporal queries, encryption, deletion,
shred, distillation provenance, cross-provider continuity y no-leak tests.

**Entregables.** ADR de ownership, promotion map, deletion receipt y
benchmarks de memoria relevantes.

**Riesgos.** Fuga privada, stores divergentes, duplicados sin autoridad y
recall persuasivo pero falso.

**Rollback.** Mantener ADR-057 por uso; desactivar promoción automática y
conservar export verificable antes de migración.

**Finalización.** Cada clase de memoria tiene dueño y lifecycle; toda
promoción/borrado es trazable y probado.

## P05 — Knowledge and Research

**Misión.** Convertir fuentes no confiables en claims verificables,
contradictorios y temporalmente situados.

**Alcance.** Research missions, source snapshots, verifier, KnowledgeBase,
semantic KG, Graphify/GraphRAG/Graphiti, vault export y OS events como
proyección.

**Current.** Research/ingest tienen código, tests, wiring y ticks observados
en el runtime original. Tres informes dirty se preservan como `RESEARCH`.
Semantic graph no es autoridad automática.

**Target.** Claim-level provenance, dedupe por contenido/URL, contradiction
sets, temporal KG y promoción gobernada desde memoria/investigación.

**Componentes.** MissionRunner, verifier, KnowledgeBase, knowledge trunk,
semantic graph pipeline, source ledger, vault/export y event bridge.

**Contratos y decisiones.** ADR-047–049, ADR-058;
`CTR-GRAPHRAG-HYPOTHESIS`, `CTR-SOURCE-INDEPENDENCE`,
`CTR-PRIVATE-DISTILLATION`.

**Invariantes.** Integridad de fuente no equivale a verdad; nada queda
“absorbido” con claims sin clasificar; estructura y semántica permanecen
separadas.

**Dependencias.** P02 estructura/contexto, P04 memoria, P07 adquisición, P09
vetting/evidence y P12 auditoría bilateral.

**Gates y tests.** Snapshot/hash, verifier PASS-only, dedupe, provenance,
contradiction, temporal queries, hostile-source handling y no-auto-promotion.

**Entregables.** Knowledge authority model, temporal KG benchmark y
distillation/promotion pipeline.

**Riesgos.** SEO/README como verdad, duplicados diarios, prompt injection y
grafo semántico con falsa certeza.

**Rollback.** Retener fuente y claim en cuarentena; retirar edges derivados
sin borrar la evidencia primaria.

**Finalización.** Cada claim aceptado puede explicarse, contradecirse,
revalidarse y retirarse sin corromper la fuente.

## P06 — Self-Build and Foundry

**Misión.** Mejorar Atlas mediante candidatos aislados, medidos, gobernados y
reversibles.

**Alcance.** Mission v0, Golden Route, Foundry/SelfBuildRunner, ColdUpdate,
AtlasCoder/ToolCoder, worktrees, gates y promoción. No posee aceptación.

**Current.** Código y tests amplios; Golden Route v0 y ticks están wired.
`ValidationRunner` ejecuta ahora pytest/mypy de candidatos mediante Bwrap
read-only, sin red y sin entorno del host. La observación fresca fue un
preflight bloqueado, no una mejora exitosa. El perfil Kuzu de aplicación ya
evita los defaults virtuales del host y las rutas focales pasan con 2 GiB,
pero falta un receipt de la suite completa en un runner con límite físico
independiente; no se declara self-build exitoso. El perfil de pytest candidato
usa DNS público determinista únicamente cuando un test ya inyecta su fetcher:
no restaura red, no cambia `SSRFBridge` en runtime y no transforma esa ruta
focal en un build completo.

**Target.** Desde gap verificado hasta candidato, evaluación independiente,
aprobación, aplicación, recibo, aprendizaje y rollback; sin mutar el checkout
vivo.

**Componentes.** Mission, GoldenRouteSession, Foundry, SelfBuildRunner,
ColdUpdateManager, codegen, AST Guard y proposal ledger.

**Contratos y decisiones.** ADR-025, ADR-039, ADR-048, ADR-068/069;
`CTR-NO-SELF-PROMOTION`, `CTR-AST-GUARD`,
`CTR-GOLDEN-ROUTE-APPROVAL`.

**Invariantes.** Builder ≠ promoter; worktree ≠ process sandbox; validate-only
por defecto; el patch se limita a rutas permitidas, excluye
`config/governance.json` y conserva su digest desde propuesta hasta rollback;
tests y rollback antes de apply.

**Dependencias.** P00 decisiones, P02 context, P03 cognition, P07 supply
chain, P09 isolation/evaluation/recovery.

**Gates y tests.** Worktree isolation, AST Guard, targeted/full tests, mypy,
security audit, diff review, approval, atomic commit y rollback rehearsal.

**Entregables.** Work orders ejecutables, Candidate contract, evaluation
receipts y tasas de éxito/fallo honestas.

**Riesgos.** Auto-promoción, mutación del checkout vivo, prueba circular y
lección aprendida desde un fallo no diagnosticado.

**Rollback.** Worktree descartable, commit atómico, snapshot cuando aplique y
ColdUpdate validate-only.

**Finalización.** Una clase de cambio solo se automatiza después de evidencia
repetible, reviewer independiente y rollback probado.

## P07 — Integration and Protocols

**Misión.** Conectar capacidades sin transferirles autoridad del núcleo.

**Alcance.** Integration Fabric, MCP Registry/Trunk/client, ACP/A2A gateways,
connectors, PluginManifest, admission, materialización, activación y receipts.

**Current.** Rutas locales declarativas y vetting remoto A/B están
implementadas/probadas. MCP está configurado, no globalmente live. ACP no tiene
transporte fresco. Auto-adopción ejecutable C está rechazada.

**Target.** Gateways tipados, identidad/capability leases, vetting por
transporte, trials aislados, activación HITL y revocación uniforme.

**Componentes.** Integration Fabric, McpRegistry, trunk server/client,
PluginManifest, SupplyChainScanner, ReceiptBroker, Activator, ACP server y
connectors.

**Contratos y decisiones.** ADR-035, ADR-060, ADR-065, ADR-072–076;
`CTR-PROTOCOL-GATEWAY`, `CTR-MCP-NO-AUTO-ADOPT`,
`CTR-EXTERNAL-UNTRUSTED`.

**Invariantes.** Metadata clearance ≠ ejecución; stdio ≠ HTTP; permisos vacíos
por defecto; remoto ejecutable requiere humano; activación reversible.

**Dependencias.** P01 capability/policy, P02 context, P05 research, P09
scanner/runtime/evidence y P10 peers.

**Gates y tests.** Manifest strict, path/symlink/bounds, license/source,
stage1/2 cursor terminality, TrialGate, Decider/HITL, receipt, revoke y
unsupported transport.

**Entregables.** Registro fiable, connector contracts, ACP smoke real y
admission receipts.

**Riesgos.** Supply-chain, SSRF, shell injection, catálogo que confunde
`candidato` con instalado y protocolos convertidos en core.

**Rollback.** Disable/revoke adapter, restore manifest snapshot y conservar
receipt; nunca ejecutar lo no analizable.

**Finalización.** Una integración puede instalarse, probarse, activarse,
revocarse y auditarse sin adquirir ownership institucional.

## P08 — Product OS and UI/UX

**Misión.** Hacer gobernable y comprensible Atlas mediante superficies
dedicadas que proyectan el núcleo.

**Alcance.** Prime, Linux/Android apps, Universal Bar, Presence Engine, Liquid
Workbenches, Coding/Research, Business, Security y Operations surfaces.

**Current.** `atlas-shell` es arnés; NebulaGraph/fixture, LivingGraph huérfano,
Universal Bar simulado y Mission Console parcial. ADR-078 acepta Atlas
Engineering Workbench y la línea CodeOSS/VSCodium como host desktop, con Void
como donante de capacidades y Zed como donante ACP/de patrones; todavía no
están importados ni wired en esta candidata. ADR-071 mantiene Android como
proyección dedicada posterior. El bridge 7341 está implementado y probado,
pero sus POST mutantes contradicen el boundary read-only de ADR-058/071;
`ADC-WO-107` requiere decisión del operador.

**Target.** Atlas Engineering Workbench como primer producto dedicado,
local-first y accesible, con intención, revisión/diagnóstico, explicación,
aprobación, evidencia y recuperación; proyección Android dedicada y surfaces
sin estado autoritativo propio.

**Componentes.** Prime, EngineeringFinding/review plane, host
CodeOSS/VSCodium, capacidades seleccionadas de Void, adaptador/patrones ACP de
Zed, Universal Bar, Presence Engine, Liquid UI, proyección Android, Atlas API
bridge y validation harness.

**Contratos y decisiones.** ADR-058/059/066/068/071/078;
`CTR-UI-PROJECTION`.

**Invariantes.** Harness ≠ producto; fixture ≠ live data; aprobación antes de
efecto; una superficie no amplía autoridad del núcleo; sin deep fork
irreversible sin ADR y coste medido.

**Dependencias.** P01 authority, P02 context, P03 Mission/Task, P04/P05
continuity/knowledge, P09 approval/recovery y P11 substrate.

**Gates y tests.** Exact Node build/audit, accessibility, API contract,
fixture provenance, visual acceptance, offline mode, approval and recovery
journeys.

**Entregables.** Corte 1 de findings/revisión/diagnóstico, corte 2 integral del
Workbench desktop, puentes Atlas, design system, proyección Android y
deprecación explícita del harness cuando corresponda.

**Riesgos.** Optimizar el arnés equivocado, estado duplicado, snapshot viejo
presentado como vivo, incompatibilidad de licencias/upstream y un fork
Frankenstein sin boundaries ni estrategia de actualización.

**Rollback.** Mantener el arnés y adapters; superficies nuevas se habilitan
por release sin migrar autoridad.

**Finalización.** El operador acepta una experiencia end-to-end del Workbench
y, por separado, la proyección Android; ningún fixture, donor o prototipo
conserva el label de producto.

## P09 — Security, Evaluation, Operations and Recovery

**Misión.** Mantener Atlas seguro, medible, operable y recuperable aun cuando
modelos, herramientas o proveedores fallen.

**Alcance.** Authorization, Policy enforcement, GateEngine, AST/supply-chain,
sandbox/runtime, Security Council, Shadow/Drift, evaluation, observability,
health, audit, snapshots y rollback.

**Current.** Múltiples mecanismos reales y probados; Merkle verificó la base.
Security Council está opt-in/configurado en el proceso original pero sin acción
fresca completa. Esta candidata aplica el guard high después de todo Decider y
hace fail-closed los errores, snapshots inválidos y drift de Sentinel, revocando
el transporte MCP afectado durante la vida del proceso. `EngineeringFinding` v1
aporta schema, journal append-only, deduplicación, adaptación de self-audit,
revisión determinista sobre `UniversalVerifier` y diagnóstico de un
`ValidationReport` capturado mediante un `RootCauseClassifier` inyectado. La
clasificación preserva `UNKNOWN`, no guarda salida cruda ni texto libre del
clasificador y no ejecuta reparación.
El publisher opt-in de findings/reviews obtiene primero un receipt Merkle y sólo
después emite metadata mínima al `EventBus`; no está inyectado en runtime ni
rutea al Orchestrator. `EngineeringReviewBaselineStore` selecciona una base
aceptada sólo tras `PASS`, reviewer real y referencia de aceptación explícita;
conserva lifecycle previo. `EngineeringIncrementalReviewPreparer` verifica
ancestry y lee el delta entre objetos Git con external diff/textconv desactivados,
sin ejecutar el candidato; `EngineeringIncrementalReviewRunner` entrega ese
request al coordinador existente sólo si todavía requiere revisión. El
normalizador incremental correlaciona sólo `dedupe_key` opacas e idénticas y
expone `NOT_REOBSERVED` sin cambiar lifecycle ni inferir una resolución. Aún
falta integrar las hipótesis de grafo/historial/memoria, wiring
gobernado, Orchestrator y superficie de producto.

`EngineeringReproductionRunner` reutiliza `WorktreeManager` y `BwrapJail` para
un único target pytest validado sobre un commit inmutable. El worktree debe
pertenecer al mismo repositorio, es read-only dentro del jail sin red y el
intento se registra en Merkle antes de ejecutar; sin receipt final no promueve
el resultado. Sólo entonces puede convertir la captura en el `ValidationReport`
en memoria que consume diagnóstico; no aplica patches ni persiste salida de test.

**Target.** Defensa por capas, secretos dedicados, aislamiento por riesgo,
evaluación independiente, SLO/telemetría y recuperación no-LLM.

**Componentes.** Authorization, LayeredIsolationSandbox, executors,
GateEngine, Sentinel, Security Council, ShadowRouter, DriftTripwire, Merkle,
Reality/doctor/health y recovery manager.

**Contratos y decisiones.** ADR-036–040, ADR-047/048, ADR-053–056,
ADR-062/063, ADR-072/074/075/077; todos los `CTR-*` de seguridad.

**Invariantes.** Fail-closed; high humano/deny; generated code bajo AST Guard;
third-party reversible; telemetry del veredicto final; secretos no se
archivan.

**Dependencias.** Transversal; P01 concede autoridad, P03 propone, P06/P07
generan candidatos, P11 proporciona aislamiento.

**Gates y tests.** Red team, bypass custom Decider, sandbox real, timeout,
secret scan, supply chain, shadow drift, Merkle verify, restore drill,
dependency audit y clasificación de regresiones.

**Entregables.** Security boundary ADRs, evaluation plane, secrets authority,
SLOs, recovery runbooks y receipts verificables.

**Riesgos.** Wrapper de seguridad sin enforcement, `overall=ok` inflado,
unblock no autenticado y rollback que depende del servicio caído.

**Rollback.** Deny/safe mode, aislamiento mínimo, snapshot, adapter disable y
procedimiento determinista local.

**Finalización.** Una release no tiene BLOCKING; MAJOR resolubles están
corregidos; efectos y rollback se verifican independientemente.

## P10 — Hermes and Distributed Atlas

**Misión.** Extender Atlas a pares y nodos sin diluir identidad, permisos ni
evidencia.

**Alcance.** Hermes, Kanban/atlas-twin, Telegram/VPS, node identity,
heartbeats, pairing, federation, capability advertisement y revocación.

**Current.** Hermes Kanban está implementado/probado; runtime fresco fue
mock/no configurado. NodeIdentity está probado pero no wired. Despliegues y
heartbeats anteriores son historia.

**Target.** Pares autenticados que proponen, anuncian capacidades y reciben
leases acotados; Atlas mantiene Policy, Execution y Evidence.

**Componentes.** Hermes adapter, KanbanBridge, twin skill, NodeIdentity,
SignedHeartbeat, pairing/federation control plane y notifications.

**Contratos y decisiones.** ADR-026/028/070; `CTR-HERMES-PROPOSES`,
`CTR-AUDITABLE-EFFECT`.

**Invariantes.** Hermes propone, Atlas decide; sin deep fork; desconexión no
rompe el núcleo; ningún heartbeat histórico prueba liveness actual.

**Dependencias.** P01 identity/capabilities, P03 cognition, P07 protocols, P09
security/evidence y P11 networking/substrate.

**Gates y tests.** Authenticated pairing, replay/expiry, least privilege,
proposal-only, provider failure, disconnect, Telegram receipt y rollback.

**Entregables.** ADR de federation, control plane, live smoke autorizado y
runbook de revocación.

**Riesgos.** Credenciales externas, autoridad implícita, nodo comprometido y
declarar vivo un VPS inaccesible.

**Rollback.** Revocar lease/par, deshabilitar canal y volver a mock/local sin
perder receipts.

**Finalización.** Un par real pasa pairing, propuesta, decisión Atlas,
auditoría, timeout y desconexión bajo una prueba fechada.

## P11 — Hosted and Native Substrate

**Misión.** Proveer un sustrato local desplegable hoy y una ruta Native solo
cuando su necesidad esté demostrada.

**Alcance.** Hosted Linux, packaging/services, hardware/resource control,
containers/sandboxes y futura investigación seL4/Genode/NT/WASM.

**Current.** Linux Hosted ejecuta Atlas. Native es `RESEARCH/PARKED`; Wave 5
está bloqueada. La “Ola 5” de benchmarks del 2026-07-23 es otra cosa.

**Target.** Hosted robusto, portable y recuperable; Native acotado a una
amenaza/limitación medida con API Runtime↔Prime estable.

**Componentes.** Host services, process/runtime isolation, packaging,
resource/thermal controls y candidatos Native.

**Contratos y decisiones.** `CTR-WAVE5-NATIVE-GATE`,
`CTR-THERMAL-DEGRADATION`.

**Invariantes.** Hosted antes de Native; no kernel rewrite por entusiasmo;
portabilidad, amenaza, coste, migración y rollback antes de commit.

**Dependencias.** P08 Product, P09 runtime/security/recovery y P10 networking.

**Gates y tests.** Hosted limitation benchmark, threat model, hardware matrix,
portability, resource budget, migration rehearsal y operator authorization.

**Entregables.** Hosted deployment contract, Runtime↔Prime API, benchmark
evidence y, solo si se aprueba, un Native spike aislado.

**Riesgos.** Compromiso irreversible de plataforma, desvío de recursos y
seguridad teórica peor que Hosted probado.

**Rollback.** Hosted sigue siendo ruta primaria; todo spike Native es
descartable y no migra estado durable sin rehearsal.

**Finalización.** Hosted satisface el producto; Native solo adquiere un
milestone cuando todos los gates de Wave 5 están aceptados.

## P12 — Membrane, Osmosis and Bilateral Audit

**Misión.** Diseccionar sistemas externos y Atlas de forma bilateral para
asimilar capacidades útiles sin clonar ni importar autoridad.

**Alcance.** OSM lifecycle, trust/compliance/provenance filters, adversarial
comparison, osmosis, membrane promotion y guarantee profiles.

**Current.** OSM-000 define vocabulario; OSMs tienen estados absorbido,
difusión o membrana. ADR-074 promueve una fase de OSM-042. No existe una
decisión general de enforcement.

**Target.** Pipeline fuente→disección→claim→comparación→experimento→decisión→
promoción/retirada, con auditoría en ambas direcciones y garantías explícitas.

**Componentes.** OSM registry/corpus, comparison harnesses, provenance/trust
filters, bilateral audit y futuro enforcement adapter.

**Contratos y decisiones.** OSM-000, ADR-053/054/074;
`CTR-EXTERNAL-UNTRUSTED`, `CTR-GRAPHRAG-HYPOTHESIS`.

**Invariantes.** Research no auto-promueve; una fase promovida no absorbe todo
el programa; “inspirado por” no significa adoptado; enforcement no puede tener
bypass oculto.

**Dependencias.** P00 promoción, P05 conocimiento, P07 admission y P09
seguridad/evaluación.

**Gates y tests.** Provenance, license, independent reproduction, comparative
metric, hostile input, bypass/fail-closed y rollback del filtro.

**Entregables.** OSM disposition registry, operator guarantee decision,
comparison reports y promotions enlazadas a ADR.

**Riesgos.** Clonación, autoridad por novedad, garantía inflada y research
convertido en bloqueo productivo.

**Rollback.** Retirar adapter/promoción conservando evidencia y devolver el
OSM a investigación visible.

**Finalización.** Cada adopción externa explica qué se tomó, qué se rechazó,
qué mejora Atlas, cómo se mide y cómo se desactiva.
