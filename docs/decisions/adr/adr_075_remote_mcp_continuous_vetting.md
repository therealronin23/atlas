# ADR-075 — Ciclo continuo de vetting de MCPs remotos (scan-antes-de-aprobar)

- Estado: **Propuesto** (2026-07-24) — requiere aprobación del operador y cierre
  del hueco de la voz EU del Cónclave antes de pasar a Aceptado.
- Extiende (no reemplaza): **ADR-072** (supply-chain admission scan A1),
  **ADR-073** (PluginManifest v1 + A3 materializer/receipt/activator), **ADR-038**
  (SentinelGate), **ADR-055** (BwrapJail).
- Toca el invariante duro de ADR-073: *"local-only; remote sources and executable
  plugin types require a new ADR"*. Este ES ese ADR.

## Contexto

`scripts/mcp_seed_registry.py` sembró 2111 candidatos **remotos** del registro
oficial MCP (`docs/design/mcp_catalog_seeded.yaml`), todos `status: candidato`.
El operador pidió un ciclo continuo que los convierta en aptos para uso.

Infra ya existente y madura (verificada por grep, no asumida):
- `SpawnTrial` + `BwrapJail` — probe en sandbox `--unshare-all`, sin red, uid nobody.
- `SentinelGate` (ADR-038), 6 capas: TOFU anti rug-pull, IOC/coherencia de comando,
  tiering credencial fail-closed, coherencia desc↔schema, `vet_call` egress runtime,
  `revet_all` periódico.
- `supply_chain.py` (A1) — escaneo de admisión metadata-only.
- `plugin_admission`/`plugin_materializer`/`plugin_receipt_broker`/`plugin_activator`
  (A3) — staged → receipt Merkle → HITL vía Decider → activación reversible.

## Por qué la propuesta original del operador se rechaza

El operador propuso: *"convertir TODOS los candidatos en aptos → descargar →
luego analizar código malicioso"*. Eso es **aprobar-luego-escanear**, y descargar/
aprobar 2111 servers de terceros antes de analizarlos es el vector exacto del
backdoor de Postmark ya presente en el IOC de Sentinel (`giftshop.club`).
"Convertir TODOS en aptos" anula el triaje. Se invierte a **escanear-antes-de-aprobar**.

## Gaps reales de Sentinel (SOTA, no intuición)

Contra OWASP MCP Top-10 2025 (MCP03 Tool Poisoning), `mcp-scan` (Invariant Labs)
y `MCP-Scanner` (eSentire): Sentinel cubre bien rug-pull (TOFU) y egress IOC, pero
**no detecta tool-poisoning/prompt-injection en descripciones** ni **analiza el
código fuente** del server. Ambos son obligatorios para fuentes remotas ejecutables.

## Corrección del Cónclave (2026-07-24, 2/3 linajes vivos)

Trío `deliberation_council` sobre el pipeline propuesto. Mistral 🇪🇺 no disponible
(hueco EU, ver ADR-074); Gemini 🇺🇸 + GLM 🇨🇳 convergieron independientemente en
una objeción **MAJOR** sustantiva (diversidad estricta 3 no alcanzada → veredicto
formal UNKNOWN, pero la objeción se acata):

> **Falacia de composición:** el pipeline usaba `BwrapJail` (aislamiento de **red**)
> como si mitigara un ataque **semántico** (tool-poisoning). No lo hace. Un MCP
> ofuscado que pasa el escaneo de metadatos entra al sandbox; la red aislada no
> impide que el LLM de Atlas sea víctima de prompt-injection vía las descripciones
> de tools — el LLM actúa como **canal encubierto** sin necesitar egress de red.

Correcciones incorporadas: análisis estático del **código fuente** obligatorio y
**antes** de cualquier ejecución (I2); el LLM vivo **nunca** lee descripciones de
terceros sin sanitizar (I3). El sandbox de red es necesario-pero-no-suficiente.

## Decisión — invariantes no negociables

- **I1 · scan-antes-de-aprobar.** Ningún candidato es `apto` sin pasar las etapas
  1–4. "Convertir TODOS en aptos" queda prohibido explícitamente.
- **I2 · análisis de código fuente obligatorio antes de ejecutar.** Ningún código
  remoto se ejecuta (ni en sandbox) sin pasar análisis estático de su fuente.
- **I3 · el LLM vivo nunca lee descripciones de terceros sin sanitizar.** El
  escaneo de inyección corre en un hub PLANO aislado, no en el orquestador vivo.
- **I4 · fetch y probe network-isolated** (`--unshare-all`) **y** egress-IOC gated
  (`vet_call`). El aislamiento de red se empareja siempre con I2/I3, nunca solo.
- **I5 · admisión HITL por lotes** vía el Decider A3 + receipt Merkle; activación
  reversible (A3.3). Cero auto-adopción de tipos remotos ejecutables.
- **I6 · fail-closed** en todo: lo no-analizable/no-fetchable/ambiguo se rechaza y
  se registra en `pending_review`.
- **I7 · adopt-real-not-shell.** Las capas nuevas (inyección + fuente) envuelven
  herramientas reales (`mcp-scan`/`MCP-Scanner`/Semgrep-class) diseccionadas en un
  jail, no un cascarón reimplementado.

## Pipeline por etapas (reusa la infra existente)

0. **Seed** (hecho) — 2111 candidatos, metadata-only, sin descarga ni ejecución.
1. **Pre-screen estático (read-only, sin descarga)** sobre la metadata ya en
   catálogo: A1 + heurística nueva de tool-poisoning/inyección en descripciones
   (keyword + semántico + juez LLM opcional, en hub plano — I3). Barato, cubre los
   2111. Salida: score de riesgo + triaje.
2. **Fetch + análisis de fuente (antes de ejecutar — I2)** para los que pasan la 1:
   descarga a cuarentena sin ejecución, análisis estático de código (Semgrep-class
   + A1 sobre el código real). Fetch con egress controlado.
3. **Probe conductual en sandbox** (`SpawnTrial`/`BwrapJail`, sin red): valida
   conformidad de protocolo y captura defs para snapshot TOFU. Las descripciones
   pasan por SentinelGate + escaneo de inyección **antes** de tocar cualquier LLM (I3).
4. **Score + admisión SentinelGate:** 6 capas + la capa nueva de inyección → veredicto.
5. **Aprobación HITL por lotes** vía Decider A3 + receipt Merkle; activación
   reversible (A3.3). Nunca auto-aprobación masiva.
6. **Re-vet continuo** (`revet_all` + `maintenance_*_tick`): re-escaneo periódico;
   drift de rug-pull → auto-revoca + `pending_review`.

## "Aprobar lo que tenemos ya" (aclaración del operador, 2026-07-24)

El operador aclaró que su intención es **escanear lo que tenemos y aprobar los que
pasen** (scan-antes-de-aprobar, no aprobar-luego-scan), y en el futuro, cuando un
MCP se actualice, re-analizar lo descargado y re-barrer el tronco entero. Esto
encaja con este ADR. Con una precisión no negociable sobre qué significa "aprobar":

- Los 2111 candidatos hoy son **solo metadata** del registro (no descargados). El
  único "aprobar" honesto para una entrada no-descargada es promover
  `candidato → metadata-cleared` (elegible para fetch) tras pasar la etapa 1 —
  **nunca** `apto-ejecutar`, que exige ver el código (etapas 2–4).
- "Aprobar TODOS" = aprobar todos **los que pasan el scan**. El scan debe poder
  rechazar (I1/I6); un IOC confirmado (`giftshop.club`) o una descripción con
  payload de inyección no se promueve.
- El ciclo futuro del operador (actualización → re-analizar lo descargado →
  aprobar para ejecutar → re-barrer el tronco periódicamente) **es** exactamente
  las etapas 2–6 + el re-vet continuo de este ADR.

## Qué se construye ya (seguro, reversible) vs qué queda gateado

- **Ahora (read-only, no toca el invariante):** etapa 1 — el pre-screen estático
  sobre los 2111, que produce el triaje sin descargar ni ejecutar nada.
- **Gateado a la aceptación de este ADR:** etapas 2–6 (fetch, ejecución en sandbox,
  admisión, activación). No se descarga ni ejecuta ningún server remoto hasta que
  el operador acepte este ADR y se cierre (o se acepte el hueco de) la voz EU del Cónclave.

## Consecuencias

- Primera vez que Atlas ingiere fuentes MCP remotas — bajo scan-antes-de-aprobar,
  no aprobar-luego-scan. El coste computacional del análisis de fuente (I2) es real
  pero solo sobre los que pasan la etapa 1, no los 2111.
- Riesgo residual honesto: el juez de inyección es una llamada LLM con su tasa de
  error; fail-closed (I6). El hueco EU del trío queda como deuda de infra que este
  ADR no cierra pero registra.
