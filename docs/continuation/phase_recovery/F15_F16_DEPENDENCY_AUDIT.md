# F15_F16_DEPENDENCY_AUDIT — Phase Recovery

Inspeccionado: `src/atlas/fabric/`, `src/atlas/business/`,
`src/atlas/api/product_routes.py`, `src/atlas/interfaces/cli.py`,
`schemas/`, `fixtures/`, `tests/test_os_*.py`, `docs/continuation/`,
`docs/decisions/`, `docs/design/`, memoria (`MEMORY.md` + ficheros), grafo
Kuzu/tronco de conocimiento.

## 1. ¿F15 asumía algún componente F1-F14 existente?

**Sí, tres explícitamente, todos verificados como reales:**

1. **Event Kernel / bus de eventos (F1-F3)** — `product_routes.py` importa y
   usa el mismo `emit_event`/patrón de `src/atlas/events/emit.py` que F2-3
   creó. `PolicyEngine.evaluate()` emite eventos vía este mecanismo.
2. **Backend Bridge / app FastAPI (F2-3)** — `register_product_routes(app)`
   se registra sobre la MISMA instancia de app que `server.py` (F2-3) crea;
   no monta un segundo servidor.
3. **UI Shell (F4)** — F16-6 (HarnessPanel) se monta como una vista más
   dentro del mismo `App.tsx` de F4, reutilizando `core/api.ts` y
   `styles.css` ya existentes (variables CSS `--warn`, `--radius`, `--pad`,
   `--border`).

**No asumía F5 ni F6** (Visual Orchestrator / Coding+Research Territories) —
verificado por ausencia total de referencias cruzadas (ver Coverage Matrix).

## 2. ¿F16 asumía algún componente F1-F14 existente?

Sí, los mismos tres de F15 (hereda todo lo de F15), más un cuarto propio:
**Gate Engine (F16-2) reutiliza el mismo patrón `_Store` con lock+JSON** que
ya usaban `BusinessCoreEngine` (F15) y, antes, componentes del núcleo
preexistente (`TransparencyLog`) — patrón arquitectónico heredado, no
dependencia directa de código.

## 3. ¿Algún módulo de F15/F16 está construido sobre cimientos ausentes?

**No.** Todo lo que F15/F16 importan de fuera de `fabric/`/`business/` existe
y está probado: `src/atlas/events/emit.py`, la app FastAPI de `server.py`,
y (solo en tests) fixtures de `governance/gates.json` preexistentes de F7-9.
No hay ningún `ImportError` latente ni mock que sustituya algo que debería
ser real — verificado con `MYPYPATH=src python -m mypy src/atlas/fabric/
src/atlas/business/ src/atlas/api/ src/atlas/interfaces/cli.py` limpio (ya
confirmado en cierre de F16 anterior) y con grep explícito: `fabric/` y
`business/` NO importan `atlas.memory` ni `atlas.graph` (0 resultados) —
cero acoplamiento oculto a capas no relacionadas.

## 4. ¿Algún módulo de F15/F16 queda aislado porque faltan capas
   grafo/memoria/UI/workflow anteriores?

**Parcialmente, y ya documentado con honestidad antes de esta auditoría**
(`docs/continuation/phase15/WHAT_WAS_NOT_IMPLEMENTED.md`):

- La promoción de un `BusinessEntity`/`EntityCandidate` a memoria canónica
  NO ocurre automáticamente — queda en `$ATLAS_HOME/business_core/`, sin
  escribirse en el índice de memoria del núcleo. Esto es un gap real, pero
  NO es porque falte una "Fase" del pack — es porque el puente
  memoria-OS↔memoria-núcleo nunca se diseñó (mismo gap ya conocido para
  `os_import_v1`, ver memoria `atlas-os-foundation-2026-07-10`).
- La ausencia de F5 (Visual Orchestrator) NO aísla nada de F15/F16 — ningún
  flujo de negocio necesita un canvas visual para funcionar (las recetas de
  conexión y el motor de preguntas son data-driven, no requieren editor
  visual).

## 5. ¿Pasan los tests solo porque fixtures/stubs esconden capas
   inferiores ausentes?

**No.** Los 190 tests OS corren contra código real:
`GmailReadOnlyConnector` hace una llamada HTTP real vía `urllib` cuando hay
token (gateada, no mockeada a nivel de librería); `GateEngine` persiste a
disco real (JSON+lock) en paths aislados de test; `BusinessCoreEngine`
idem. Los ÚNICOS mocks reales del sistema son los 5 conectores de F7-9
(WhatsApp/Odoo/etc., documentados explícitamente como mock desde su
creación, no un intento fallido de ser reales) y el modo de Gmail sin
token (`BLOCKED_BY_MISSING_DEPENDENCY`, un estado honesto, no un mock
disfrazado de real). No hay fixture que sustituya una capa "de verdad
ausente" sin decirlo.

## 6. ¿Qué trabajo de F15/F16 es seguro conservar?

**Todo.** No se encontró ningún módulo de F15/F16 construido sobre una
premisa falsa o un cimiento inexistente. La ausencia de F5/F6 no invalida
nada porque nunca fueron una dependencia real.

## 7. ¿Qué trabajo de F15/F16 necesita re-cableado?

**Ninguno de forma urgente/bloqueante.** Un candidato de mejora, no de
re-cableado correctivo: conectar la promoción de `BusinessEntity` al
índice de memoria del núcleo (mencionado en el punto 4) — es una extensión,
no una corrección de algo roto.

## 8. ¿Qué trabajo de F15/F16 debería parkearse?

**Ninguno.** Todo lo construido en F15/F16 tiene test+código+doc real y
está en uso por el arnés UI verificado en vivo. No hay nada especulativo
que convenga parkear.

## Veredicto de esta fase

F15 y F16 son estructuralmente sanos: dependen solo de fundaciones reales
(F0-F4, F7-9), no dependen de las fases nunca ejecutadas (F5-F6), y no
tienen tests que oculten capas ausentes. El único gap real heredado
(memoria-OS↔memoria-núcleo) ya estaba documentado honestamente antes de
esta auditoría — no es un descubrimiento nuevo, es una confirmación de que
la documentación previa no mentía.
