# ADR-036 — Modelo de amenazas y hoja de murallas defensivas

- Status: **Accepted** (2026-05-30)
- Plano completo: [`docs/plan_mcp_y_murallas_defensivas.md`](../../design/plan_mcp_y_murallas_defensivas.md)
- Depende de: ADR-031/032/033 (loop agéntico), ADR-034 (hardening de proceso)
- Habilita: ADR-037 (frontera de contenido no confiable), ADR-038 (gate de adopción)

## Contexto

Atlas va a consumir servidores MCP externos y, a futuro, leer foros/papers para
auto-mantenerse. Eso abre la superficie de ataque de todo el ecosistema agéntico,
que en 2025–2026 ya tiene víctimas reales:

- **>30 CVEs** (ene–feb 2026) contra servers/clients MCP; la peor `CVE-2025-6514`
  con CVSS **9.6** (RCE).
- Incidentes: exposición cross-tenant en Asana, inyección contra el GitHub MCP
  server, **RCE no autenticado en el MCP Inspector de Anthropic**, backdoor de
  Postmark (15 versiones limpias + 1 envenenada que filtraba emails).
- Estudios: Snyk ToxicSkills (36% de skills con fallos), y meta-análisis que mide
  **>78–85% de bypass** de las defensas SOTA bajo ataque adaptativo.

## Decisión

Adoptar un modelo de amenazas explícito y una **hoja de murallas priorizada**, en
vez de defensas ad-hoc. Principio rector: **defensa en profundidad + HITL en lo
irreversible**; no se persigue una "solución total" porque la evidencia la
prohíbe.

### Taxonomía de amenazas (consolidada de CoSAI/NSA/CSA)

1. Inyección de prompt / tool poisoning — instrucciones ocultas en datos, outputs
   o descripciones de tools.
2. Confused deputy — proxy MCP que obtiene autorización sin consentimiento.
3. Rug pull — tool aprobado una vez, no re-verificado, que cambia de conducta.
4. Tool squatting — tool malicioso con nombre similar al legítimo.
5. Robo de credenciales — desde env vars o logs.
6. SSRF — durante discovery de metadata OAuth.
7. Cadena de suministro — update envenenado.

### Hoja de murallas (estado original, 2026-05-30 — ver actualización abajo)

| Prioridad | Muralla | Estado | ADR |
|---|---|---|---|
| P0 | Frontera de contenido no confiable | 🟡 slice 1 hecho | 037 |
| P0 | Gate de adopción "Atlas Sentinel" | ⏳ | 038 |
| P1 | Manejo de secretos MCP (fuera de Merkle/logs/contexto) | ⏳ | 035 |
| P1 | Control de egress (allowlist + IOC) | ⏳ | 035/038 |
| P1 | Anclaje de la cadena Merkle | 🟡 parcial | 036 |
| P2 | Confused-deputy en el loop (namespacing auto-approve) | ⏳ | 035 |
| P2 | Integridad de la aprobación (atar OK a hash de acción) | ⏳ | 033/036 |
| P2 | Profundidad del sandbox (seccomp/namespaces) | 🟡 ADR-034 base | seccomp |
| Futuro | Integridad del validador de ColdUpdate | ⏳ | 036 |
| Futuro | Cadena de suministro del modelo | ⏳ | 036 |
| Futuro | Confianza inter-nodo (Flota) | ⏳ (hw) | fleet |
| Futuro | Post-quantum (ML-KEM/ML-DSA) | anotado | 036 |

## Actualización (2026-07-24) — esta tabla llevaba 8 semanas sin tocarse

Hallazgo de auditoría: esta hoja es el documento fundacional del "modelo de
amenazas" de Atlas, pero **nadie volvió a actualizarla cuando el trabajo se
movió a ADRs posteriores** (038, 040, 072, 073, 075) — quedó congelada en el
estado del día 1 mientras la mayoría de las murallas SÍ se construyeron.
Efecto práctico: cualquiera que lea esta tabla hoy para saber "¿qué tenemos
realmente?" recibe una foto de hace 8 semanas, no la realidad. Verificado
línea por línea contra código real (callers, no solo el nombre del ADR):

| Prioridad | Muralla | Estado verificado hoy | Evidencia |
|---|---|---|---|
| P0 | Frontera de contenido no confiable | ✅ hecho | ADR-037 Accepted; I3 de ADR-075 lo extiende a MCP |
| P0 | Gate de adopción "Atlas Sentinel" | ✅ hecho, 6 capas | `sentinel_gate.py`, 3 callers reales (`registry.py`, `installer.py`, `orchestrator.py`); capas 5/6 activadas 2026-07-24 (commit `9b8164a`) |
| P1 | Manejo de secretos MCP | ✅ hecho | `env_passthrough` guarda solo NOMBRES, nunca valores (`mcp/config.py`); fail-fast pre-spawn si faltan secretos declarados |
| P1 | Control de egress (allowlist + IOC) | ✅ hecho | `SSRFBridge` (fan-in=18, el 5º módulo más importado del repo); suelo IOC de dominios sembrado 2026-07-24 (`giftshop.club`); IOC de **comandos** sigue vacío (asimetría anotada, defendible: no hay comando confirmado-malicioso que sembrar) |
| P1 | Anclaje de la cadena Merkle | 🟡 sigue parcial | sin cambio verificado esta pasada |
| P2 | Confused-deputy en el loop | ✅ hecho | namespacing `mcp__<server>__<tool>` real en `registry.py`/`trunk_aggregator.py` — un tool nunca hereda confianza de otro server |
| P2 | Integridad de la aprobación (atar OK a hash de acción) | ✅ hecho | `_consult_decider` devuelve `(verdict, action_hash)`; `register_undo(act_hash, ...)`; `decider.verdict` en Merkle incluye `action_hash` real (verificado contra 603 entradas reales del log) |
| P2 | Profundidad del sandbox | ✅ hecho con límites declarados | `BwrapJail` (`--unshare-all`); `ValidationRunner` es el caller efectivo de ColdUpdate, junto a `spawn_trial`, `lesson_runner`, `tool_coder`, `security/executor` y `security/sandbox` |
| Futuro | Integridad del validador de ColdUpdate | 🟡 parcial | pytest/mypy de candidato ya corren en Bwrap read-only/sin red/sin env host; la suite completa falla cerrada por defaults mmap de Kuzu, sin build exitoso declarado |
| Futuro | Cadena de suministro del modelo | 🟡 parcial | `maintenance_provider_smoke_tick` detecta modelos muertos/renombrados (no es supply-chain del modelo en sí, es liveness de proveedor) |
| Futuro | Confianza inter-nodo (Flota) | ⏳ sin cambio | depende de hardware, no priorizado |
| Futuro | Post-quantum | anotado, sin cambio | — |

**Hallazgo más importante de esta auditoría, que esta tabla NO captura porque
está fuera de su alcance original**: la mayoría de las murallas de arriba
están construidas y activas, pero `ATLAS_DECIDER=autonomous` (activo en
producción desde ≥2026-07-15, confirmado contra el entorno real del proceso
vivo) hace que la vía de "pedir aprobación humana" (`RequiresHuman`,
`Task.AWAITING_APPROVAL`, `EventType.APPROVAL_REQUIRED`) sea estructuralmente
inalcanzable — `AutonomousDecider` solo devuelve `Allow`/`Deny`, nunca
`RequiresHuman` (`decider.verdict` en Merkle: 603 entradas, 0 de tipo
"pending" desde mayo de 2026). Las murallas no fallan; el camino para que un
humano las revise cuando SÍ deberían escalar está apagado por configuración.
Ver ADR-077 (propuesto) para el diseño que cierra esto.

## Consecuencias

- Cada muralla nueva referencia esta hoja y su prioridad.
- El orden es vinculante: la frontera P0 (037) precede al consumo real de MCP
  (035) y, sobre todo, a leer foros (auto-mantenimiento).
- **Lección operativa**: una hoja de estado que nadie actualiza es peor que no
  tener hoja — da falsa confianza de que algo falta cuando ya existe (o
  viceversa). Revisar esta tabla debería ser parte del checklist de cualquier
  ADR de seguridad nuevo, no un ejercicio arqueológico ocasional.

## Fuera de alcance

- Prompt engineering (otra conversación).
- Construir todas las murallas a la vez (sobreingeniería; se levantan por prioridad).

## Referencias

Ver [`docs/plan_mcp_y_murallas_defensivas.md`](../../design/plan_mcp_y_murallas_defensivas.md#referencias)
(CaMeL arXiv:2503.18813, arXiv:2601.17548, CoSAI, NSA CSI, CSA, Snyk).
