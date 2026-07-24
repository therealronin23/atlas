# ADR-075 — Ciclo continuo de vetting de MCPs remotos (scan-antes-de-aprobar)

- Estado: **Aceptado** (2026-07-24, aprobación explícita del operador). El hueco
  de la voz EU del Cónclave (Mistral, ver ADR-074) sigue **sin cerrar** — la
  aprobación del operador es autoridad final y satisface la condición humana;
  el hueco EU queda como deuda de infraestructura registrada aparte (no bloquea
  este ADR, pero tampoco se da por resuelto). Etapa 1 (pre-screen estático,
  read-only) ya construida y corrida sobre los 2111 candidatos reales. Etapas
  2–6 (fetch/probe/admisión/activación) siguen sin construir; requieren su
  propio trabajo de ingeniería antes de tocar código o red de terceros.
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

## Autocrítica (auditoría 2026-07-24) — el pipeline original asumía algo falso

Al releer este ADR con ojo crítico (pedido explícito del operador: "haz una
auditoría del 075 y corrígelo"), la distribución real del catálogo lo contradice:

```
grep -oE "transport: \w+" mcp_catalog_seeded.yaml | sort | uniq -c
   1869 transport: http     (88.5%)
    228 transport: stdio    (10.8%)
```

`transport: http` viene del campo `remotes` del esquema del registro oficial
(`_transport_of()`, `registry_seed.py`) — por diseño, es un servicio **alojado
remotamente**, no un paquete descargable. `install` sale **siempre `""`**, incluso
para los `stdio` (el seeder nunca lo capturó — gap menor aparte, no bloqueante).

El pipeline original (I2: análisis de fuente obligatorio; I4: sandbox sin red)
asumía implícitamente que TODO candidato es un paquete local fetchable — cierto
solo para el 10.8%. Para el 88.5% restante **no existe código fuente que analizar**
ni tiene sentido "probar en sandbox sin red" un servidor cuyo único punto de
contacto ES la red. I2/I4 tal como estaban habrían bloqueado el 88.5% del catálogo
por un requisito inaplicable, o (peor) alguien los habría relajado en silencio para
"que pase algo". Corregido abajo con dos pistas explícitas.

## Decisión — invariantes no negociables

- **I1 · scan-antes-de-aprobar.** Ningún candidato es `apto` sin pasar su pista
  (stdio o remoto). "Convertir TODOS en aptos" queda prohibido explícitamente.
- **I2 · análisis de código fuente obligatorio antes de ejecutar CÓDIGO LOCAL**
  (pista stdio, 228 candidatos). No aplica a la pista remota — ahí no hay fuente;
  ver I2-R.
- **I2-R · para la pista remota (http, 1869 candidatos): admisión basada 100% en
  comportamiento observado + IOC, nunca en "hemos visto el código".** Riesgo
  residual reconocido, no oculto (ver Consecuencias).
- **I3 · el LLM vivo nunca lee descripciones de terceros sin sanitizar.** El
  escaneo de inyección corre en un hub PLANO aislado, no en el orquestador vivo.
  Aplica a AMBAS pistas (la inyección vive en `purpose`/tool descriptions, sea
  local o remoto).
- **I4 · pista stdio: fetch+probe network-isolated** (`--unshare-all`, sin red).
  **Pista remota: egress gated de un único endpoint**, allowlist estricta al
  dominio declarado en `source`, vía la misma capa IOC/dominio de SentinelGate
  (`vet_command`) — nunca red sin restricción. No son el mismo mecanismo; no
  confundir "sin red" (stdio) con "red restringida a 1 dominio" (remoto).
- **I5 · admisión HITL por lotes** vía el Decider A3 + receipt Merkle; activación
  reversible (A3.3). Cero auto-adopción de tipos remotos ejecutables.
- **I6 · fail-closed** en todo: lo no-analizable/no-fetchable/ambiguo se rechaza y
  se registra en `pending_review`. Para la pista remota, "no-analizable" es la
  norma, no la excepción — I6 es la defensa primaria ahí, no un backstop.
- **I7 · adopt-real-not-shell.** Las capas nuevas (inyección + fuente) envuelven
  herramientas reales (`mcp-scan`/`MCP-Scanner`/Semgrep-class) diseccionadas en un
  jail, no un cascarón reimplementado.

## Pipeline por etapas (reusa la infra existente; dos pistas desde la etapa 2)

0. **Seed** (hecho) — 2111 candidatos, metadata-only, sin descarga ni ejecución.
1. **Pre-screen estático (read-only, sin descarga)** sobre la metadata ya en
   catálogo: A1 + heurística nueva de tool-poisoning/inyección en descripciones
   (keyword + semántico + juez LLM opcional, en hub plano — I3). Barato, cubre los
   2111 (ambas pistas, mismo chequeo — la inyección no distingue transporte).
   Salida: score de riesgo + triaje + **routing por transporte** a la pista 2A/2B.
2. **Bifurcación por transporte:**
   - **2A — pista stdio (228):** fetch a cuarentena sin ejecución → análisis
     estático de código (Semgrep-class + A1 sobre el código real, I2).
   - **2B — pista remota (1869):** NO hay fetch de fuente. Se registra el
     endpoint (`source`) y pasa directo a probe conductual con egress de
     un-solo-dominio (I4 remoto).
3. **Probe conductual en sandbox:**
   - **2A→3:** `SpawnTrial`/`BwrapJail`, sin red — valida conformidad de
     protocolo, captura defs para TOFU.
   - **2B→3:** llamada de protocolo real al endpoint remoto (egress
     allowlisted a ese dominio, nada más) — mismo objetivo (conformidad +
     defs TOFU), sin sandbox de proceso porque no hay proceso local que aislar.
   Ambas pistas: descripciones pasan por SentinelGate + escaneo de inyección
   **antes** de tocar cualquier LLM (I3).
4. **Score + admisión SentinelGate:** 6 capas + la capa nueva de inyección →
   veredicto. Para 2B, el veredicto pesa más en comportamiento/IOC (I2-R) que
   en las capas ausentes por falta de fuente.
5. **Aprobación HITL por lotes** vía Decider A3 + receipt Merkle; activación
   reversible (A3.3). Nunca auto-aprobación masiva.
6. **Re-vet continuo** (`revet_all` + `maintenance_*_tick`): re-escaneo periódico;
   drift de rug-pull → auto-revoca + `pending_review`. Para la pista remota, el
   re-vet es la defensa de mayor peso a largo plazo (un servidor remoto puede
   cambiar de comportamiento del lado del servidor sin ningún "update" visible
   localmente — motivo de más para no relajar la cadencia de `revet_all` en 2B).

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
  sobre los 2111, que produce el triaje + el routing 2A/2B por transporte, sin
  descargar ni ejecutar nada.
- **Gateado a la aceptación de este ADR:** etapas 2–6 en ambas pistas (fetch 2A,
  probe remoto 2B, ejecución en sandbox, admisión, activación). No se descarga
  fuente ni se contacta ningún endpoint remoto hasta que el operador acepte este
  ADR y se cierre (o se acepte el hueco de) la voz EU del Cónclave.

## Consecuencias

- Primera vez que Atlas ingiere fuentes MCP remotas — bajo scan-antes-de-aprobar,
  no aprobar-luego-scan. El coste computacional del análisis de fuente (I2) es real
  pero solo sobre el 10.8% (`stdio`) que pasa la etapa 1.
- **Riesgo residual estructural (no un detalle menor): el 88.5% del catálogo
  (`http`) nunca podrá pasar por análisis de código fuente, por diseño del
  transporte, no por falta de esfuerzo.** La admisión de esa pista depende
  enteramente de comportamiento observado + IOC + re-vet continuo (I2-R/I6) —
  un techo de confianza más bajo que la pista stdio, permanente, no algo que un
  futuro ciclo "arregle". El operador debe decidir con esto en mente si algún
  sector de la pista remota (p.ej. `credential`-tier) merece un listón más alto
  que "pasó el scan" — no cerrado en este ADR, registrado para su decisión.
- Riesgo residual honesto: el juez de inyección es una llamada LLM con su tasa de
  error; fail-closed (I6). El hueco EU del trío queda como deuda de infra que este
  ADR no cierra pero registra (task de seguimiento abierta).
