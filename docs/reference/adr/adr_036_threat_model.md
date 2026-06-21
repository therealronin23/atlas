# ADR-036 — Modelo de amenazas y hoja de murallas defensivas

- Status: **Accepted** (2026-05-30)
- Plano completo: [`docs/plan_mcp_y_murallas_defensivas.md`](plan_mcp_y_murallas_defensivas.md)
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

### Hoja de murallas

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

## Consecuencias

- Cada muralla nueva referencia esta hoja y su prioridad.
- El orden es vinculante: la frontera P0 (037) precede al consumo real de MCP
  (035) y, sobre todo, a leer foros (auto-mantenimiento).

## Fuera de alcance

- Prompt engineering (otra conversación).
- Construir todas las murallas a la vez (sobreingeniería; se levantan por prioridad).

## Referencias

Ver [`docs/plan_mcp_y_murallas_defensivas.md`](plan_mcp_y_murallas_defensivas.md#referencias)
(CaMeL arXiv:2503.18813, arXiv:2601.17548, CoSAI, NSA CSI, CSA, Snyk).
