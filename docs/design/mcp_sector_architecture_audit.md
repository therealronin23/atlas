# Auditoría + premortem — arquitectura "MCP-de-sector autocontenido" (2026-06-21)

Antes de construir C. Objetivo: maximizar idea/concepto/diseño/clasificación/orden y **no retroceder**.
Estado vivo en `WORK_LEDGER.md`; el porqué/lecciones, aquí y en memoria.

## 1. El concepto a auditar (reformulado del usuario)

```
TRONCO (1 conexión, lazy por sector)
 └─ MCP-de-sector (NUESTRO, autocontenido)
     ├─ tools · skills(servidos) · APIs · resources/prompts
     └─ sub-MCPs (internos + externos)
```
Cada sector = un MCP propio que **empaqueta** lo suyo y **frontea** más MCP. El modelo accede "de una",
sin descargar lo nuestro. Externos = conexión (su binario debe existir).

## 2. Auditoría por dimensión (qué está bien / qué falla)

- **Concepto** ✅ fuerte: "una conexión, todo clasificado, acceso inmediato" es la tesis cross-play.
  ⚠️ riesgo: "todo dentro de cada sector" puede reintroducir el kitchen-sink DENTRO del sector.
- **Encaje con el protocolo MCP** ⚠️ el punto frágil:
  - Un *skill* de Claude Code (SKILL.md) NO es objeto MCP. Mapea a `prompt`/`resource`, PERO el soporte
    de `prompts` en clientes es desigual (no garantizado que el modelo los vea/use como un skill real).
    → **hay que SPIKE-arlo antes de diseñar encima** (riesgo #1 del premortem).
  - `tools` y `resources` sí son sólidos y portables.
- **Arquitectura** ⚠️ "un proceso por sector" tiene coste: N procesos + spawns anidados (tronco→sector→
  sub-MCP) = latencia, handshakes frágiles, debug difícil. Alternativa: **sectores LÓGICOS** (namespaces)
  dentro de menos procesos + spawn perezoso de externos. Misma UX, menos modos de fallo.
- **Clasificación** ⚠️ el esquema actual es 1 sector por entrada; la realidad es multi-sector (un tool
  sirve a varios). → sector = VISTA (tags), no carpeta exclusiva.
- **Seguridad** ✅ tenemos el moat (SentinelGate + Merkle) que los agregadores externos no tienen.
  ⚠️ traer MCP externos = superficie de supply-chain (código no confiable, secretos, breaking changes).
- **Honestidad / anti-vapor** ⚠️ crear N scaffolds de sector vacíos viola `wire-before-claim`.
  → un sector-MCP solo nace cuando tiene ≥1 miembro real verificado.
- **Portabilidad / cross-play** ✅ bundles por sector son portables; ⚠️ la config crece (mitiga: tronco
  único dirigido por catálogo, no 14 entradas en el cliente).
- **Fuente de verdad** ⚠️ si copiamos el texto de un skill dentro de un sector-MCP, se DUPLICA y diverge.
  → derivar/referenciar desde una sola fuente (catálogo + origen), no copiar a mano.

## 3. Premortem (es diciembre 2026 y el proyecto fracasó — ¿por qué?)

| # | Modo de fallo | Sev | Mitigación |
|---|---|---|---|
| 1 | **skills-como-prompts no funcionó** en el cliente (el modelo no los ve/usa) → "acceso sin descarga" nunca se materializó | ALTA | SPIKE de `prompts`/`resources` en Claude Code ANTES; fallback = tool `get_skill(name)` que DEVUELVE el texto (funciona siempre) |
| 2 | **explosión de procesos / latencia** (tronco→N sectores→sub-MCPs) | ALTA | sectores LÓGICOS en pocos procesos + spawn perezoso de externos al primer uso + idle cleanup |
| 3 | **vuelve el kitchen-sink dentro del sector** | MED-ALTA | descubrimiento lazy estricto a 2 niveles; cap de tools por vista |
| 4 | **deriva de contenido** (copias de skills divergen del original) | MED | referenciar/derivar de una sola fuente + provenance + versión |
| 5 | **la clasificación pelea con la realidad** (multi-sector) | MED | tags multi-sector; sector = vista, no hogar exclusivo |
| 6 | **supply-chain de MCP externos** (código no confiable, secretos) | ALTA | SentinelGate veta pre-spawn (ya lo tenemos); prove-it antes de `verificado`; pin de versión; sin secretos en catálogo |
| 7 | **punto único de fallo / debug anidado** | MED | aislamiento por hijo (ya: un server caído no tumba al resto) + audit Merkle + health checks |
| 8 | **carga de mantenimiento / vapor** (scaffolds vacíos) | MED | sector-MCP nace solo con ≥1 miembro real |
| 9 | **sobre-ingeniería** para mono-usuario local | MED | construir el mínimo que da "1 conexión + acceso lazy por sector"; aplazar anidamiento >2 niveles |
| 10 | **churn del spec MCP** (prompts/resources cambian) | BAJA-MED | adaptador fino |

## 4. Mejoras concretas (idea/diseño/clasificación)

- **Arquitectura recomendada (corrección):** NO un proceso por sector. **Tronco único dirigido por
  catálogo** con **sectores lógicos** (namespaces) + **spawn perezoso** de sub-MCPs (nuestros y externos)
  al primer uso. Da tu visión (1 conexión, todo por sector, acceso inmediato a lo nuestro) con menos
  fallos. El "MCP-de-sector" separado solo se justifica si un sector necesita aislamiento real (p.ej.
  permisos/credenciales distintos) — entonces SÍ proceso propio, caso por caso.
- **Skills:** servir con tool `get_skill(name)`→devuelve el contenido (robusto a cualquier cliente) Y
  además como `prompt` MCP donde el cliente lo soporte. Cinturón y tirantes. "Sin descarga" garantizado.
- **Clasificación v2 (catálogo):** añadir `tags` (multi-sector), `version`, `license`, `trust`
  (vetted?), `transport` (stdio/http), `mode` operativo: **served** (nuestro, sin descarga) /
  **connected** (externo, conexión) / **installed** (skill a dir, solo si no se sirve). `provenance`
  (source+fetched_at) en lo sembrado.
- **Fuente de verdad única:** catálogo YAML = registro; el contenido de sector se DERIVA, no se copia.

## 5. Orden revisado de C (cero retroceso)

0. **SPIKE** (desechable): ¿llegan `prompts`/`resources` MCP al modelo en Claude Code? Decide el
   mecanismo de skills (#1 del premortem). Sin esto, no diseñar encima.
1. **Catálogo v2**: añadir tags/version/license/trust/transport/mode + migrar el YAML actual.
2. **Tronco dirigido por catálogo** (sectores lógicos + spawn perezoso): `serve()` lee hijos+sector del
   catálogo, no de `native_roots` fijo. Externos se conectan al primer uso.
3. **Mecanismo de skills servidos** (`get_skill` + prompt donde haya soporte), un skill real E2E.
4. **Sembrar catálogo** del registro oficial (`registry.modelcontextprotocol.io`, ya en allowlist) con
   procedencia → candidatos por sector/kind.
5. **prove-it loop** → marcar `verificado` (con veto SentinelGate).
6. **Instalador por `mode`**: served (nada que bajar) / connected (`claude mcp add` + hijo del tronco) /
   installed (skills dir, solo si no se sirve).

Criterio de éxito: 1 conexión; acceso inmediato a lo nuestro por sector; externos perezosos y vetados;
nada vapor (cada pieza con ≥1 miembro real); cero copias divergentes.
