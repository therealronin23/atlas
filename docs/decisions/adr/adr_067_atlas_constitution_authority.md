# ADR-067 — Atlas Constitution Authority

- Estado: aceptado (2026-07-11)
- Contexto: `docs/handoff/atlas_fable5_handoff_v1/docs/QUALITY_GATES.md`
  define un "Gate A — Architecture Coherence" que exige una Constitución en
  la ruta `docs/atlas-master/00_CONSTITUTION.md`. Esa ruta no existe en el
  repo (`find docs/handoff -iname "*atlas-master*"` → sin resultados) y
  nunca existió — es una ruta que ZIP2 esperaba pero que ningún pack ni
  sesión llegó a poblar ahí. El cierre de los 3 ZIPs
  (`docs/continuation/zip_closure/CROSS_ZIP_CONFLICT_TABLE.md`, conflicto
  #11) dejó esto como `NEEDS_OPERATOR_DECISION`: ¿se escribe el fichero
  que falta, o se reconoce formalmente que la Constitución vive en otro
  sitio? El operador eligió la segunda opción.

## Decisión

1. **La Constitución de Atlas vive distribuida, no como fichero único**,
   en las siguientes fuentes, cada una con su rol:
   - **`AGENTS.md`** (raíz del repo) — invariantes operativos, manías
     permanentes, reglas de naming, loop operativo. Es la fuente más
     cercana a "reglas de construcción" del sentido que ZIP2 le daba a
     "Constitution".
   - **`docs/design/atlas_ecosystem_map.md`** — taxonomía y clasificación
     canónica del ecosistema (qué es cada pieza, cómo se relaciona).
   - **Los ADRs reales vigentes** (`docs/decisions/adr/adr_058` en
     adelante) — cada decisión de arquitectura de peso, con su motivo,
     documentada individualmente en vez de en un manifiesto único.
   - **`docs/handoff/atlas_product_os_liquid_ui_pack_v1/product/
     00_ATLAS_PRODUCT_CONSTITUTION.md`** (ZIP3) — la constitución de
     PRODUCTO (visión "Liquid Software"/OS orientado a objetivos), no de
     ingeniería. Sigue siendo la referencia de principios de producto,
     absorbida en las decisiones D11 y ADR-060/061 sin haberse copiado
     literalmente a ninguna otra ruta.
2. **No se crea `docs/atlas-master/00_CONSTITUTION.md`** como duplicado o
   resumen de lo anterior. Concatenar/resumir estas 4 fuentes en un
   fichero nuevo introduciría una quinta copia de verdad que divergiría
   con el tiempo (exactamente el patrón de fragmentación que el cierre de
   ZIPs de esta sesión ya diagnosticó entre packs). Si el operador pide
   explícitamente ese fichero en el futuro, este ADR debe superseder-se,
   no ignorarse en silencio.
3. **Gate A de `QUALITY_GATES.md` (ZIP2) queda formalmente resuelto**: se
   considera cumplido en espíritu por la distribución de arriba, no por la
   ruta literal que el pack esperaba. El pack sigue siendo correcto
   history — solo su ruta de fichero queda superseded por esta decisión.

## Consecuencias

- `docs/continuation/zip_closure/CROSS_ZIP_CONFLICT_TABLE.md` (conflicto
  #11) pasa de `NEEDS_OPERATOR_DECISION` a `RESOLVED`.
- `docs/continuation/zip_closure/FINAL_ZIP_CLOSURE_VERDICT.md` y
  `CANONICAL_WORK_ORDER_AFTER_ZIPS.md` retiran `GATE_A_CONSTITUTION_
  CLOSURE_01` de la lista de candidatos pendientes — queda cerrado.
- Ninguna sesión futura debe volver a proponer escribir
  `docs/atlas-master/00_CONSTITUTION.md` sin superseder este ADR primero.
- No se toca código ni UI — este ADR es puramente documental/de gobierno
  de documentación.
