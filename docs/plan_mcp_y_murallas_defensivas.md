# Plan Maestro — Cliente MCP, Murallas Defensivas y Auto-Mantenimiento

- Status: **Draft / planificación** (2026-05-30)
- Autor: sesión de diseño Atlas (Tomás + Claude)
- Alcance: consolidar TODO lo discutido en la sesión sobre (1) Atlas como cliente
  MCP, (2) gate de adopción "Atlas Sentinel", (3) frontera de contenido no
  confiable, (4) threat model / murallas, (5) agente de auto-mantenimiento.
- Enriquecido con literatura profesional (papers arXiv + guías de industria +
  marcos CoSAI/NSA/CSA). Ver [Referencias](#referencias).
- Documentos hijo a crear: `adr_035_mcp_client.md`, `adr_036_threat_model.md`,
  `adr_037_untrusted_content_boundary.md`, `adr_038_atlas_sentinel_gate.md`.

> **Este doc es el plano. Las murallas se levantan por prioridad de amenaza real,
> no todas a la vez.** Escribir el mapa es barato y evita olvidar; construir
> especulativamente contra ataques que no existen es la trampa de sobreingeniería.

---

## 0. Principios rectores (anclados en evidencia)

1. **Defensa en profundidad, no balas de plata.** Un meta-análisis de 78 estudios
   (2021–2026) encuentra que las defensas SOTA contra inyección de prompt se
   evaden con **>85% de éxito** bajo ataque adaptativo; el paper de asistentes de
   código (arXiv:2601.17548) mide que la mayoría logran **<50% de mitigación** y
   se bypassean al **>78%** con optimización adaptativa. **Conclusión dura: no
   existe "la solución a todos los problemas".** Capas + HITL en lo peligroso es
   la postura realista.
2. **Descubrir autónomo / adoptar con humano.** El agente puede investigar,
   comparar y *proponer*; **instalar/ejecutar/actualizar código de fuentes no
   confiables pasa SIEMPRE por ColdUpdate + HITL.** Es la línea que hace viable
   el auto-mantenimiento en vez de auto-suicidio (cadena de suministro).
3. **Stdlib primero (regla 6).** El camino por defecto es stdlib; las deps
   (p.ej. SDK `mcp`, post-quantum) son extensiones opt-in detrás de interfaz.
4. **Aprender el *diseño* de los punteros, no su producto.** Microsoft Sentinel
   MCP es SaaS cloud-locked: **no hay nada que forkear**. Lo aprovechable es su
   gramática de diseño documentada (ver §6).
5. **Esto NO es prompt engineering.** Se mantiene fuera del plan deliberadamente
   para no perder foco; es otra conversación.
6. **Reusar lo ya endurecido.** Atlas ya tiene AST Guard, sandbox + hardening
   (ADR-034), Merkle, ColdUpdate, PermissionProfile, HITL Telegram. Las murallas
   se construyen *encima* de estas primitivas, no de cero.

---

## 1. ADR-035 — Atlas como cliente MCP (consumo autónomo)

### Objetivo
Que Atlas (y por extensión Hermes vía el bridge twin) se conecte a servidores MCP
externos (Google Calendar, n8n, …), exponga sus tools al loop agéntico, y el
modelo **decida solo cuándo usarlas leyendo la descripción** — el mismo mecanismo
que ya usa para git/editor/skills.

### Arquitectura
```
servidores MCP ──initialize→tools/list──> McpRegistry
   (Calendar, n8n)                            │
                                     convierte a _agentic_tool_specs()
                                     nombre: mcp__<server>__<tool>
                                              │
   el modelo elige por descripción ◄──────────┘  (selección autónoma)
              │
   tools/call ──> _dispatch_agentic_tool ──> read: inline
                          │                  mutate: SUSPENDE → HITL (ADR-032/033)
                          └── cada llamada AUDITADA en Merkle (params + hash result)
```

### Decisiones
| # | Tema | Elección | Razón / evidencia |
|---|------|----------|-------------------|
| 1 | Transporte | stdio JSON-RPC, stdlib (`subprocess`+`json`), tras interfaz `McpTransport` | Regla 6; cubre Calendar/n8n; SDK drop-in futuro |
| 2 | Híbrido | "hybrid-ready": `StdioTransport` ahora; `SdkTransport` (dep `mcp` **opcional**, lazy) como hueco documentado | Mejor de ambos sin dead code; SDK solo si aparece un server HTTP/SSE |
| 3 | Descubrimiento | `tools/list` al arranque **+ registro dinámico** (✅ `add_server`/`remove_server` en caliente, vetados por el gate) | El registro dinámico es materia prima del agente de auto-mantenimiento (§5) |
| 4 | Selección autónoma | Vía *description engineering* (lección Sentinel §6.2); sin routing nuevo | Confirmado por Sentinel: "security-optimized descriptions help models pick" |
| 5 | Riesgo | **Mutate/HITL por defecto**; allowlist marca cuáles son `read` (inline) | Tiered HITL del paper: silent reads / confirmed writes+net |
| 6 | Colecciones | Agrupar tools en *colecciones de capacidad* con permiso por colección | Lección Sentinel §6.1; least-privilege |
| 7 | Secretos | Env por server desde config NO commiteada; **nunca** al Merkle/contexto/logs | Mitiga "credential theft from env vars or logs" (CoSAI/NSA) |
| 8 | Egress | Servers fuera del sandbox (necesitan red) → **allowlist de egress** (no blocklist) + blocklist IOC | Paper §capability scoping: "allow-listed egress rather than block-lists" |
| 9 | Auth | Preparar OAuth 2.1 con **separación de audiencia de token** para servers que lo requieran (Calendar) | Spec MCP jun-2025; evita "token passthrough abuse" / confused deputy |
| 10 | Twin | Atlas posee el cliente; Hermes consume vía bridge existente | Una fuente de verdad |

### Entregables
- `src/atlas/mcp/transport.py` — `McpTransport` (interfaz) + `StdioTransport` (stdlib)
- `src/atlas/mcp/registry.py` — `McpRegistry` (config, spawn, specs, dispatch, registro dinámico)
- `mcp_servers.json` (config; secretos fuera de git)
- Integración `orchestrator.py`: specs MCP en `_agentic_tool_specs()`; dispatch
  `mcp__*`; riesgo alimenta `_AGENTIC_MUTATING_TOOLS` dinámicamente
- Tests: server MCP de juguete stdlib (echo, sin red/secretos) para E2E transporte
  + cableado; registry/risk/dispatch; namespacing anti-colisión
- **E2E primero: Google Calendar** (leer agenda = inline; crear evento = HITL)

---

## 2. ADR-036 — Threat model y hoja de murallas

### Contexto duro (por qué importa ya)
- Ene–feb 2026: **>30 CVEs** contra servers/clients MCP; la peor `CVE-2025-6514`
  con **CVSS 9.6** (RCE).
- Incidentes reales 2025: exposición cross-tenant en Asana, inyección contra el
  GitHub MCP server, **RCE no autenticado en el propio MCP Inspector de Anthropic**,
  backdoor de Postmark (15 versiones limpias + 1 envenenada).
- Marcos de referencia: **CoSAI** (12 categorías, ~40 amenazas), guía **NSA**,
  **Cloud Security Alliance** agentic MCP.

### Taxonomía de amenazas MCP (consolidada)
1. **Inyección de prompt / tool poisoning** — instrucciones ocultas en datos,
   outputs de tools o descripciones que el modelo lee y el usuario no.
2. **Confused deputy** — proxy MCP a API de terceros obtiene authz sin consentimiento.
3. **Rug pull** — el registro de un tool se aprueba una vez y no se re-verifica;
   cambia de comportamiento tras desplegarse.
4. **Tool squatting** — tool malicioso con nombre similar al legítimo.
5. **Robo de credenciales** — desde env vars o logs.
6. **SSRF** — durante discovery de metadata OAuth.
7. **Cadena de suministro** — update envenenado (Postmark).

### Murallas priorizadas (de Atlas)
| Prioridad | Muralla | Amenaza | Estado | ADR |
|---|---|---|---|---|
| **P0** | Frontera de contenido no confiable | Inyección indirecta (resultados de tools/archivos/**foros** re-entran al contexto) | ❌ | 037 |
| **P0** | Gate de adopción (Atlas Sentinel) | Supply chain skills/MCP (Postmark, ToxicSkills 36%) | 🟢 slice 1 (identidad+IOC+tiering, fail-closed) | 038 |
| **P1** | Manejo de secretos MCP | Robo desde env/logs/Merkle | ❌ | 035 |
| **P1** | Control de egress (allowlist + IOC) | Exfiltración por server fuera de sandbox | ❌ | 035/038 |
| **P1** | Anclaje cadena Merkle | Atlas comprometido reescribe su auditoría | 🟡 parcial | 036 |
| **P2** | Confused-deputy en el loop | Colisión de nombres con allowlist auto-approve | ❌ | 035 |
| **P2** | Integridad de la aprobación | Modelo redacta OK inocente para acción mala; atar OK a hash de la acción | ❌ | 033/036 |
| **P2** | Profundidad del sandbox | seccomp/namespaces | 🟡 ADR-034 base | 035→seccomp |
| **Futuro** | Integridad validador ColdUpdate | Update que desactiva su rollback o envenena sus tests | ❌ | 036 |
| **Futuro** | Cadena de suministro del modelo | Weights/endpoint envenenados al cambiar de modelo | ❌ | 036 |
| **Futuro** | Confianza inter-nodo (Flota) | Auth mutua, contención de blast-radius | ❌ (hw) | fleet |
| **Futuro** | Post-quantum readiness | ML-KEM / ML-DSA para firmas/cifrado a largo plazo | ❌ | 036 (anotado) |

---

## 3. ADR-038 — Gate de adopción "Atlas Sentinel"

Internaliza la tesis de `claude-mcp-sentinel` ("skills y MCP no son confiables por
defecto") en las primitivas de Atlas. **No instalamos su código** (es un hook de
Claude Code y sería, irónicamente, otra decisión de cadena de suministro); robamos
el concepto y lo construimos nativo y **fail-closed para adopción**.

| Capa | Qué hace | Reusa | Evidencia |
|---|---|---|---|
| Identidad criptográfica de tool | Firma + versión inmutable del tool definition | Merkle | Paper §1 "cryptographic tool identity" (anti squatting/rug-pull) |
| Integridad de fuente | Diff contra fuente canónica antes de adoptar | Merkle | soy-rafa v1 |
| Análisis de coherencia | ¿lo que el tool *dice* coincide con lo que *pide* (paths/endpoints/permisos)? | AST Guard ext. | soy-rafa v1; "coherence" |
| Re-verificación (anti rug-pull) | Re-vetar en cada update (snapshot + diff) | ColdUpdate | "registrations approved once, not re-verified" |
| Blocklist IOC + egress | Dominios/comandos malos antes de cada `tools/call` | dispatch hook | mcp-scan; IOC library |
| HITL escalonado | silent reads / logged writes / **confirmed** shell+net / **blocked** credenciales | ADR-032/033 | Paper §6 "tiered approval" |

Postura: **si no se puede vetar, no se adopta** (al revés que el fail-open de un
hook que no debe romper Claude Code; aquí la adopción es la operación peligrosa).

---

## 4. ADR-037 — Frontera de contenido no confiable (muralla P0, la maestra)

**Es la pieza que desbloquea el auto-mantenimiento.** Hoy los resultados de tools
(archivos, git, respuestas MCP, y mañana **texto de foros**) vuelven al contexto
del modelo sin etiqueta de confianza → inyección indirecta.

### Diseño (anclado en CaMeL arXiv:2503.18813 + 3 patrones estándar 2026)
1. **Separación datos/control (CaMeL).** Tratar la inyección como problema de
   **arquitectura**, no de prompt. Estructura: un flujo de *control* confiable
   (la tarea/sistema) separado de un flujo de *datos* no confiable.
2. **Dual-LLM cuando aplique.** LLM de control (estructura/decisión, ve el system
   prompt) vs LLM de procesamiento (digiere contenido no confiable, **sin** acceso
   a system prompt ni a tools sensibles). El contenido hostil nunca toca el control.
3. **Etiquetado de procedencia (taint/provenance).** Todo dato que entra se marca
   `trusted | untrusted` con su origen; los outputs heredan el taint de sus inputs
   (paper §"provenance tracking, outputs tagged to input dependencies").
4. **Política de tools post-ingesta.** Tras consumir contenido no confiable,
   ciertas tools (mutantes/red/credenciales) **no se pueden invocar sin
   confirmación extra**. (Patrón estándar #2.)
5. **Saneo + límites tipados.** Strip de patrones de inyección + usar bloques de
   mensaje *tipados* (Anthropic/OpenAI) como frontera a nivel protocolo, no
   delimitadores de texto. (Patrón estándar #1 y #3.)
6. **Capability binding.** Cada invocación LLM atada a un set limitado de tools;
   rechazar tool-calls no definidos desde contextos no confiables.

> Honestidad: incluso CaMeL/firewalls se degradan bajo ataque adaptativo. Por eso
> esta muralla **no sustituye** al HITL del gate de adopción ni al egress; las tres
> P0/P1 operan juntas. Defensa en profundidad.

---

## 5. Agente de auto-mantenimiento (chat siguiente — cimentado aquí)

Visión: Atlas se mantiene solo — lee foros/papers/APIs, descubre los mejores MCP,
y propone actualizaciones. **Línea infranqueable (§0.2):** descubrir/proponer
autónomo; adoptar/ejecutar vía ColdUpdate + HITL.

Flujo correcto:
```
investiga (foros/papers/registries) ──[contenido NO confiable → muralla P0]──>
compara y redacta PROPUESTA (server X v2.1, diff desde tu versión, riesgos) ──>
Telegram (botón) ──> gate Atlas Sentinel (vet) ──> ColdUpdate (worktree+tests) ──>
swap solo si pasa. Autónomo en lo cognitivo, humano en el gatillo.
```
Dependencias: requiere **P0 (037)** + **gate (038)** + **registro dinámico MCP
(035 dec.3)** ya en su sitio. Por eso ese agente es el *último* hito, no el primero.

---

## 6. Lecciones de diseño robadas a Microsoft Sentinel MCP

(Ingeniería inversa del *diseño documentado*; no hay código que forkear.)
1. **Colecciones, no lista plana.** Tools agrupadas por escenario con endpoint y
   scope propios → adoptar "colecciones de capacidad" con permiso por colección.
2. **La descripción es artefacto de primera clase.** "Security-optimized
   descriptions help AI models pick the right tools" → *description engineering*
   como ingeniería, no comentario.
3. **Herencia de permisos.** Los tools corren con los permisos del que llama
   (least-privilege) → `PermissionProfile` gatea por colección.
4. **Tools deterministas pre-horneadas** (desde queries guardadas) → acotar el
   radio de explosión vs acceso abierto.
5. **Transparencia (Application Card).** Manifiesto de cómo se usa IA → Atlas
   auto-genera un manifiesto de capacidades auditado.

---

## 7. Secuencia y dependencias

```
Fase 1 (cimientos):   ADR-036 threat model (este doc → ADR formal)   [plano]
Fase 2 (P0 maestra):  ADR-037 frontera contenido no confiable
Fase 3 (consumo):     ADR-035 cliente MCP (stdio + registry + E2E Calendar)
                      └─ trae P1 secretos + egress
Fase 4 (P0 adopción): ADR-038 gate Atlas Sentinel
Fase 5 (P2):          confused-deputy, integridad de aprobación, seccomp
Fase 6 (visión):      agente de auto-mantenimiento  [requiere 037+038+035]
Futuro/bloqueado:     modelo supply-chain, flota inter-nodo (hw), post-quantum
```
Razón del orden: la frontera P0 (037) debe existir **antes** de consumir MCP de
verdad y muchísimo antes de leer foros. Construir el cliente MCP sin la frontera
sería abrir la puerta antes de tener muros.

---

## 8. Riesgos honestos y no-objetivos

- **No-objetivo:** "solución a todos los problemas". La evidencia (>78–85% bypass
  adaptativo) lo prohíbe. El objetivo es subir el coste del ataque + HITL en lo
  irreversible.
- **No-objetivo:** prompt engineering (fuera de alcance, otra conversación).
- **No-objetivo:** forkear Sentinel (es SaaS; imposible).
- **No-objetivo:** instalar herramientas de terceros (soy-rafa) crudas — se
  reimplementa el concepto nativo.
- **Riesgo residual:** el validador de ColdUpdate y los tests están *dentro* del
  límite de confianza; un update suficientemente sofisticado podría envenenarlos
  (muralla "Futuro"). Mitigación parcial: HITL + diff humano en updates de alto
  riesgo.
- **Deuda aceptada:** seccomp queda como ADR aparte (dep/kernel); post-quantum
  solo anotado.

---

## Referencias

Papers:
- Debenedetti et al., *Defeating Prompt Injections by Design* (CaMeL), arXiv:2503.18813
- *Prompt Injection Attacks on Agentic Coding Assistants: Skills, Tools, and
  Protocol Ecosystems*, arXiv:2601.17548
- *CausalArmor: Indirect Prompt Injection Guardrails via Causal Attribution*, arXiv:2602.07918
- *Indirect Prompt Injections: Are Firewalls All You Need?*, arXiv:2510.05244

Industria / marcos:
- Model Context Protocol — Security Best Practices (modelcontextprotocol.io)
- NSA — Model Context Protocol Security (CSI_MCP_SECURITY)
- Cloud Security Alliance — Agentic MCP Security Best Practices v1
- CoSAI / Coalition for Secure AI — Practical Guide to MCP Security
- Red Hat — MCP: understanding security risks and controls
- SOC Prime — MCP Security Risks & Mitigations
- Snyk — ToxicSkills 2025 (36% skills con fallos)
- The Hacker News — First Malicious MCP Server (Postmark, sep-2025)
