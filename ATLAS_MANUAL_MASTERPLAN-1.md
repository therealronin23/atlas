# ATLAS — Manual para construir el MASTERPLAN

> **Qué es esto**: no es el masterplan. Es el *generador* del masterplan.
> Un molde con checklist por Gate que tú anclas al código real en Claude Code.
> Yo (la instancia de este chat) solo tengo la síntesis del 2026-06-26, que es un
> resumen de los ADRs — no los ADRs. Por eso este manual define **qué decidir y
> qué verificar** en cada Gate con precisión, pero las coordenadas exactas que el
> resumen no me da van marcadas como `[VERIFICAR EN REPO]` en vez de inventadas.
>
> **Cómo se usa en Claude Code**: por cada Gate, abres los archivos reales,
> resuelves cada `[VERIFICAR EN REPO]`, respondes cada casilla, y congelas las
> decisiones marcadas `🔒 DECIDIR ANTES DE EJECUTAR`. Cuando un Gate tiene los
> cinco campos resueltos y todas sus casillas marcadas, **ese** texto es la
> entrada para autobuild / dynamic workflows. Antes de eso, no se ejecuta.
>
> **Regla de oro**: este manual no inventa trabajo nuevo. Ordena, prioriza y marca
> dependencias de lo que ya existe. Si aparece un hueco, se anota como hueco
> (`⛳ HUECO`) — no se rellena con un Gate nuevo en caliente.

---

## 0. CONVENCIONES (leer una vez)

### Las tres capas

| Capa | Qué es | Regla |
|---|---|---|
| **Capa 0** | El lazo de auto-construcción: que Atlas se repare y mejore a sí mismo con verificación real | Cimiento. Nada de Capa 1/2 es real hasta que esto cierre. **Se desarrolla a fondo.** |
| **Capa 1** | Lo que el lazo cerrado *acelera*: modelo de usuario, routing, uso diario | Esqueleto aquí. Se profundiza cuando Capa 0 esté cerrada. |
| **Capa 2** | El horizonte que solo es real si 0 y 1 existen: gateway cableado, lenguaje, seL4 | Esqueleto + trampas marcadas. No se toca aún. |

**El orden dentro de cada capa lo manda `BLOQUEADO-POR`, no el interés.** Si A no puede vivir sin B, B va antes aunque A sea más emocionante.

### Los cinco campos de cada Gate

Todo Gate del masterplan final debe tener estos cinco, y ni uno más:

1. **REFERENCIA REAL** — `archivo:símbolo` o `archivo:línea`. Coordenada, no prosa. El modelo no puede alucinar dónde vive algo si le das la dirección.
2. **DONE-CRITERION (machine-checkable)** — un test que pasa, un consumidor que importa. Tu propio `wire-before-claim` convertido en condición de salida. Si no es verificable por máquina, no es un done-criterion.
3. **BLOQUEADO-POR** — qué debe existir antes. Esto es lo que impide que el workflow arranque B antes que A.
4. **DESBLOQUEA** — qué se abre al cerrarlo.
5. **DECISIÓN CONGELADA** — la elección creativa ya tomada, escrita como restricción fija, para que el modelo *implemente y no diseñe*.

### El test de front-loading

Por cada ítem, una sola pregunta decide si se investiga ahora o se deja abierto:

> **¿Aquí autobuild tendría que tomar una decisión creativa?**

- **Sí** → se decide ahora y se congela (`🔒 DECIDIR ANTES DE EJECUTAR`). Firma de función, qué consumidor la carga, qué pasa si falla, qué invariante aplica.
- **No** → se deja abierto a propósito. Detalle de implementación que el modelo rellena sin riesgo.

Investigar todo por igual desperdicia esfuerzo donde no reduce alucinación. La precisión va donde está el riesgo.

### Convención de honestidad (taxonomía CAPABILITIES.md)

Cada ítem se marca: **real** (código + test + consumidor vivo) / **durmiente** (núcleo sin consumidor) / **no-existe** / `[VERIFICAR EN REPO]` (yo no tengo la coordenada; tú la confirmas).

---

# CAPA 0 — EL LAZO DE AUTO-CONSTRUCCIÓN

**Tesis del orden**: el lazo es _fallo → lección → restricción del productor → fix → verificación → aplicación segura → registro inmutable → repetir mejorando_. La cadena de prerrequisitos va de abajo arriba. No se salta.

```
G0.0  Atlas puede auditarse a sí mismo (hoy CRASHEA)         ← blocker absoluto
  │
G0.1  Runner real de prove-it                                ← materia prima de lecciones
  │
G0.2  ErrorRegistry → LessonPromoter + sembrar 3 lecciones   ← fallos se vuelven lecciones
  │
G0.3  LessonStore consumido (Analyst/codegen)                ← lecciones restringen al productor
  │
G0.4  VerifiedProducer cableado al worker vivo               ← productor genera diffs verificados
  │
G0.5  Persistencia del log + auditoría de muestra del enjambre ← evidencia para auto-apply
  │
G0.6  ColdUpdate auto-apply ON (tipo-1 reversible)           ← el lazo se cierra
  │
G0.7  record_synthesis del Cónclave → LessonStore            ← las correcciones persisten
G0.8  SelfImprovementBridge → loop (CVE→propuesta)           ← el lazo se alimenta solo
G0.9  TwinDecider (Slice 2 shadow → Slice 3 aprende)         ← el lazo aprende de TI
```

---

## G0.0 — Atlas puede auditarse a sí mismo

**Por qué es el blocker absoluto**: la síntesis reporta que `self-audit report` crashea al arrancar. Si Atlas no puede inspeccionarse, no puede construirse. Todo lo demás de Capa 0 es vapor hasta que esto pase.

- **REFERENCIA REAL**: `orchestrator.py:1060` — `enable_gate_d_pipeline()` intenta abrir `KuzuVectorStore` sin que exista la DB. `[VERIFICAR EN REPO: nombre exacto del método de self-audit en cli.py]`
- **DONE-CRITERION**: `atlas self-audit report` corre end-to-end y devuelve exit 0 con un reporte no vacío. Test de regresión que ejecuta el comando en CI.
- **BLOQUEADO-POR**: nada. Es la raíz.
- **DESBLOQUEA**: todo G0.1–G0.9.
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR** — ¿el self-audit *crea* la `KuzuVectorStore` si no existe (lazy-init), o *falla limpio* con mensaje accionable cuando falta? Las dos son válidas; el modelo improvisará si no lo fijas. Recomendación: lazy-init con flag, porque un self-audit que exige setup manual previo rompe la autonomía.

Checklist:
- [ ] Reproducir el crash en local y capturar el traceback exacto
- [ ] `[VERIFICAR EN REPO]` confirmar si hay otros code paths que abran Kuzu sin guard
- [ ] Decidir lazy-init vs fail-closed (congelar arriba)
- [ ] Test de regresión que corre el comando completo

---

## G0.1 — Runner real de prove-it

**Por qué va aquí**: el `LessonStore` no tiene contenido real porque el `ProveItResult` se inyecta a mano — no hay runner que pruebe lecciones de verdad. Sin esto, todo lo de aprendizaje es teatro.

- **REFERENCIA REAL**: `src/atlas/core/lesson_store.py` (ADR-044). Mecanismo descrito: worktree en `fix_commit^` + pytest. `[VERIFICAR EN REPO: existe esqueleto de runner o se parte de cero; dónde se inyecta hoy el ProveItResult manual]`
- **DONE-CRITERION**: dado un `fix_commit`, el runner checkout-ea `fix_commit^`, corre pytest, confirma que falla, aplica el fix, confirma que pasa, y emite un `ProveItResult` real (no inyectado). Test que lo demuestra con un commit conocido del repo.
- **BLOQUEADO-POR**: G0.0.
- **DESBLOQUEA**: G0.2 (sin runner no hay lecciones reales que sembrar).
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR** — aislamiento del runner: ¿worktree simple, o worktree dentro de `BwrapJail`? Correr pytest de un commit arbitrario sobre tu FS es superficie de ataque. Dado el hallazgo de que `execute_command` no usa jail (`sandbox.py:122-156`), congela aquí: el runner de prove-it corre **dentro del jail** desde el día uno, no se añade después.

Checklist:
- [ ] `[VERIFICAR EN REPO]` estado del esqueleto en `lesson_store.py`
- [ ] Implementar checkout `fix_commit^` + pytest + apply + pytest
- [ ] Congelar aislamiento (jail sí/no — recomendado sí)
- [ ] Emitir `ProveItResult` real con evidencia (exits, diffs)
- [ ] Test con un `fix_commit` conocido

---

## G0.2 — ErrorRegistry → LessonPromoter + sembrar las 3 lecciones reales

**Por qué va aquí**: con runner real, los fallos pueden convertirse en lecciones almacenadas. Las 3 lecciones reales que la síntesis nombra: *matcher*, *doble escritor Merkle*, *suite recursiva*.

- **REFERENCIA REAL**: `ErrorRegistry` → `LessonPromoter` (cableado inexistente). `lesson_recaller.py:83-90` (ojo: bug de coseno reescalado documentado). `[VERIFICAR EN REPO: ubicación de ErrorRegistry y LessonPromoter]`
- **DONE-CRITERION**: las 3 lecciones reales están sembradas y recuperables; un fallo nuevo registrado en `ErrorRegistry` se promociona a lección vía `LessonPromoter` sin intervención manual. Test que registra un error sintético y verifica que aparece como lección.
- **BLOQUEADO-POR**: G0.1.
- **DESBLOQUEA**: G0.3.
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR** — antes de cablear, arreglar el bug de `lesson_recaller.py:83-90` (`(raw+1)/2` contamina el ranking; ítems irrelevantes pero recientes sobreviven). Si cableas consumidores sobre un recaller que rankea mal, propagas ruido. Congela: **el fix del coseno reescalado es prerrequisito interno de G0.2, no deuda separada.**

Checklist:
- [ ] Arreglar `lesson_recaller.py:83-90` (coseno crudo, threshold sobre escala correcta)
- [ ] `[VERIFICAR EN REPO]` ubicar ErrorRegistry / LessonPromoter
- [ ] Cablear `ErrorRegistry → LessonPromoter`
- [ ] Sembrar las 3 lecciones reales (matcher, doble escritor Merkle, suite recursiva)
- [ ] Test de promoción automática

---

## G0.3 — LessonStore consumido (Analyst / codegen cargan `avoid_pattern`)

**Por qué va aquí**: una lección que nadie carga no restringe nada. Este Gate es el que convierte el `LessonStore` de durmiente a real.

- **REFERENCIA REAL**: `lesson_store.py` (ADR-044, durmiente). Consumidores objetivo: Analyst, `maintenance_codegen_proposer`. `[VERIFICAR EN REPO: punto exacto donde codegen construye el prompt/contexto del productor]`
- **DONE-CRITERION**: el `maintenance_codegen_proposer` carga los `avoid_pattern` relevantes antes de proponer, y un test demuestra que una lección sembrada cambia el output del productor (no propone el patrón prohibido).
- **BLOQUEADO-POR**: G0.2.
- **DESBLOQUEA**: G0.4 (el productor ya está restringido por lecciones).
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR** — ¿cómo entra la lección en el productor: inyección en el prompt (blando) o restricción dura en el verificador (`avoid_pattern` como check que rechaza el diff)? La síntesis sugiere la capa Lesson→LLMProducer. Congela: las lecciones de *seguridad/irreversibles* entran como **check duro** en el verificador; las de *estilo/preferencia* como inyección de prompt. No todo al mismo canal.

Checklist:
- [ ] `[VERIFICAR EN REPO]` punto de construcción de contexto en codegen
- [ ] Decidir canal duro vs blando por tipo de lección (congelar)
- [ ] Cablear carga de `avoid_pattern` en Analyst y codegen
- [ ] Test: lección sembrada cambia el output del productor

---

## G0.4 — VerifiedProducer cableado al worker vivo

**Por qué va aquí**: el lazo A-F está completo como librería pero no cableado al `WorktreeWorker.produce_diff` real. Hasta cablearlo, es librería sin uso en producción.

- **REFERENCIA REAL**: `verified_producer.py` (ADR-048), `adversarial_panel.py` (ADR-047). Falta: `WorktreeWorker.produce_diff` real en el coordinador vivo. `[VERIFICAR EN REPO: firma actual de WorktreeWorker.produce_diff y dónde lo llama el coordinador]`
- **DONE-CRITERION**: el coordinador vivo invoca `VerifiedProducer` que produce un diff, pasa por panel adversarial, y emite `Evidence` PASS/FAIL/UNKNOWN. Test E2E desde intención hasta diff verificado.
- **BLOQUEADO-POR**: G0.3.
- **DESBLOQUEA**: G0.5/G0.6 (ya hay productor verificado cuyos diffs se pueden aplicar).
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR** — comportamiento ante `UNKNOWN` (sin diversidad mínima de panel). La síntesis dice "unknown > mentir". Congela: `UNKNOWN` **nunca** auto-aplica, siempre va a HITL. Esto es invariante, no configuración.

Checklist:
- [ ] `[VERIFICAR EN REPO]` firma y call-site de `produce_diff`
- [ ] Cablear `VerifiedProducer` al coordinador
- [ ] Congelar manejo de `UNKNOWN` → HITL siempre
- [ ] Test E2E intención → diff verificado

---

## G0.5 — Persistencia del log + auditoría de muestra del enjambre

**Por qué va aquí, junto**: no puedes confiar en auto-apply si (a) el log se evapora al cerrar el proceso, ni (b) no tienes evidencia de que el enjambre propone bien. Los dos son prerrequisito de encender G0.6.

- **REFERENCIA REAL**: log efímero — `orchestrator.py:1090` (`TransparencyLog` sin `path=`); soporte de persistencia existe en `log.py:111-149` pero no cableado. Anti-replay en memoria — `gateway.py:115` (`_committed` se pierde al reiniciar). Auditoría — `reverify_swarm_proposals`. `[VERIFICAR EN REPO: firma de reverify_swarm_proposals y dónde se invoca]`
- **DONE-CRITERION**: (a) el log persiste a disco y sobrevive reinicio — test que escribe, reinicia proceso, y lee STHs de ayer; (b) `reverify_swarm_proposals` muestra ≥N ciclos limpios (ningún patch aceptado que luego falle) sobre el corpus real. 🔒 **DECIDIR N antes** (recomendado: arrancar en N=20 ciclos limpios consecutivos).
- **BLOQUEADO-POR**: G0.4.
- **DESBLOQUEA**: G0.6.
- **DECISIÓN CONGELADA**: 🔒 cablear `path=` y anti-replay durable van juntos — log persistente con anti-replay en memoria sigue aceptando seqs ya vistos tras reinicio (combinación explícita en la síntesis). No cerrar uno sin el otro.

Checklist:
- [ ] Cablear `path=` en `TransparencyLog` (`orchestrator.py:1090` usando `log.py:111-149`)
- [ ] Persistir el set anti-replay (`gateway.py:115`)
- [ ] Test: escribir → reiniciar → leer STHs previos + rechazar seq repetido
- [ ] `[VERIFICAR EN REPO]` correr `reverify_swarm_proposals` sobre corpus real
- [ ] Congelar umbral N de ciclos limpios

---

## G0.6 — ColdUpdate auto-apply ON (tipo-1 reversible) — EL CIERRE DEL LAZO

**Por qué es el cierre**: aquí Atlas pasa de "propone" a "se mantiene solo". Es el Gate de más riesgo de toda la Capa 0. Solo se enciende con G0.5 verde **y** la seguridad de ejecución cerrada.

- **REFERENCIA REAL**: `cold_update_manager.py` (ADR-025), `swarm_cycle.py`, flag `ATLAS_SWARM_SCHEDULER`. Seguridad: `sandbox.py:122-156` (`execute_command` sin jail), ASTGuard degradado a lint (ADR-055 propuesto). `[VERIFICAR EN REPO: qué define "tipo-1 reversible" en el código hoy]`
- **DONE-CRITERION**: con el flag ON, un patch de mantenimiento mecánico tipo-1 (whitespace, orden de imports, imports muertos) se aplica sin HITL, queda registrado en Merkle con `origin=swarm` + `revert(action_hash)` disponible, y un test demuestra rollback exitoso de un patch auto-aplicado.
- **BLOQUEADO-POR**: G0.5 **y** cierre de seguridad de ejecución (ver decisión congelada).
- **DESBLOQUEA**: G0.7, G0.8 (el lazo ya gira solo y se puede alimentar).
- **DECISIÓN CONGELADA**: 🔒 **DECIDIR ANTES DE EJECUTAR, no negociable**:
  - **Solo tipo-1 reversible** auto-aplica. Define la lista cerrada de transforms permitidos (whitespace, EOF newline, orden de imports, imports muertos) y **nada fuera de esa lista** sin HITL. Cualquier transform nuevo entra a la lista solo tras su propia auditoría de muestra.
  - **Todo patch auto-aplicado corre dentro del jail** antes de aplicarse. Dado que `execute_command` no usa jail, este Gate **incluye** llevar el path de aplicación al bwrap jail. No se enciende auto-apply sobre un path sin jail.
  - El invariante `sin-undo → Deny` del `AutonomousDecider` aplica: si un patch no tiene revert verificado, no auto-aplica.

Checklist:
- [ ] `[VERIFICAR EN REPO]` definición actual de tipo-1 reversible
- [ ] Congelar lista cerrada de transforms auto-aplicables
- [ ] Llevar el path de aplicación al `BwrapJail` (cubre el gap de `sandbox.py`)
- [ ] Test: auto-apply de patch tipo-1 + registro Merkle + rollback exitoso
- [ ] Encender `ATLAS_SWARM_SCHEDULER` solo con todo lo anterior verde

---

## G0.7 — record_synthesis del Cónclave → LessonStore

**Por qué va aquí**: las correcciones al trío (manía `challenge-the-trio`) hoy se pierden — el trío es one-shot/sin estado. Que las síntesis del Cónclave persistan como lecciones cierra esa fuga.

- **REFERENCIA REAL**: `deliberation_council`, `record_synthesis` (no cableado a LessonStore real). `[VERIFICAR EN REPO: dónde se produce record_synthesis]`
- **DONE-CRITERION**: una síntesis del Cónclave con corrección se persiste como lección recuperable; un Cónclave posterior sobre tema relacionado la carga. Test que lo demuestra.
- **BLOQUEADO-POR**: G0.3 (LessonStore consumido) + G0.6 (lazo cerrado).
- **DESBLOQUEA**: memoria de correcciones del trío.
- **DECISIÓN CONGELADA**: ⛳ HUECO menor — la síntesis menciona v2.0.5 (fallback de slot por-linaje, fallo correlacionado NIM Kimi+Mistral). `[VERIFICAR EN REPO]` si afecta este cableado.

Checklist:
- [ ] `[VERIFICAR EN REPO]` ubicar `record_synthesis`
- [ ] Cablear → LessonStore
- [ ] Test: corrección persiste y se recarga en Cónclave posterior

---

## G0.8 — SelfImprovementBridge → loop de auto-mejora

**Por qué va aquí**: cierra el bucle externo — un CVE detectado en deps propias se convierte en propuesta ColdUpdate automática. El lazo deja de necesitar que tú detectes el problema.

- **REFERENCIA REAL**: `self_improvement.py` (`SelfImprovementBridge`), `scheduler.py` (ADR-039, `ATLAS_SELF_AUDIT_SCHEDULER`). No cableado al loop. `[VERIFICAR EN REPO: estado del SelfImprovementBridge]`
- **DONE-CRITERION**: un CVE detectado por scout genera una propuesta ColdUpdate que pasa por el flujo verificado. Test con CVE sintético.
- **BLOQUEADO-POR**: G0.6.
- **DESBLOQUEA**: auto-mejora reactiva ante el entorno.
- **DECISIÓN CONGELADA**: 🔒 las propuestas de CVE **no** son tipo-1; van a HITL salvo que la actualización de dep sea trivialmente reversible y testeada. No relajar G0.6 por esto.

Checklist:
- [ ] `[VERIFICAR EN REPO]` estado de `SelfImprovementBridge`
- [ ] Cablear CVE → propuesta ColdUpdate
- [ ] Congelar: CVE → HITL por defecto
- [ ] Test con CVE sintético

---

## G0.9 — TwinDecider (Slice 2 shadow → Slice 3 aprende)

**Por qué va al final de Capa 0**: es lo que hace que el lazo aprenda *de ti*. Requiere corpus del `RecordingDecider` (Slice 1b, ya completo) y el Slice 2 (shadow eval) que aún no existe.

- **REFERENCIA REAL**: `recording_decider.py`, `memory_decision_sink.py` (Slice 1b real). TwinDecider: no-existe. Slice 2 (shadow eval): no-existe. `[VERIFICAR EN REPO: volumen de corpus acumulado en el RecordingDecider]`
- **DONE-CRITERION**: Slice 2 — el sistema captura el veredicto humano al resolver `RequiresHuman` y lo almacena. Slice 3 — el `TwinDecider` predice (no decide) en shadow y se mide su acierto contra el veredicto humano real.
- **BLOQUEADO-POR**: G0.6 + corpus suficiente del RecordingDecider (la síntesis dice que hoy **no hay suficiente historial**).
- **DESBLOQUEA**: la transición de Capa 0 a Capa 1 (modelo de usuario empieza a tener sustrato de decisiones).
- **DECISIÓN CONGELADA**: 🔒 el TwinDecider arranca **solo en shadow** (predice, no decide) hasta tener métrica de acierto. No se le da poder de decisión por entusiasmo. Esto enlaza con la pregunta Q4 de la síntesis.
- ⛳ **HUECO real**: ¿cuánto corpus es "suficiente"? No está definido. Antes de G0.9, definir el umbral mínimo de decisiones grabadas para que el shadow eval sea estadísticamente útil.

Checklist:
- [ ] `[VERIFICAR EN REPO]` volumen actual de corpus
- [ ] Definir umbral de corpus suficiente (HUECO)
- [ ] Slice 2: capturar veredicto humano en `RequiresHuman`
- [ ] Slice 3: TwinDecider en shadow + métrica de acierto
- [ ] Congelar: shadow-only hasta tener números

---

### ✅ Criterio de cierre de CAPA 0

> Atlas detecta un fallo, lo convierte en lección verificada, la lección restringe a su
> productor, el productor genera un fix verificado, el fix se aplica solo si es
> tipo-1 reversible y dentro del jail, queda en Merkle persistente con revert, y el
> TwinDecider aprende de tus decisiones en shadow. **Cuando esto gira sin que lo
> mires y puedes auditar lo que hizo ayer, Capa 0 está cerrada.** Solo entonces se
> profundiza Capa 1.

---

# CAPA 1 — LO QUE EL LAZO ACELERA *(esqueleto)*

> No se profundiza hasta cerrar Capa 0. Aquí solo el mapa y las dependencias, para
> que nada se escape. Cada uno se expandirá a los cinco campos cuando toque.

- **G1.1 — Modelo de usuario (Gota 1, el alma)**. Sustrato listo (`SqliteMemoryIndex`, fastembed, FTS5, temporal). Falta la capa de modelado encima. BLOQUEADO-POR: G0.9 (TwinDecider da el corpus de decisiones). Nota: arreglar `StubEmbedder` por defecto (`memory_index.py:209`) es prerrequisito — hoy la memoria mide stub.
- **G1.2 — Captura de intención ambiente (Gota 2)**. Hook que observe estado del sistema y lo convierta en intención. BLOQUEADO-POR: G1.1 (sin modelo de usuario, toda señal ambiente es ruido).
- **G1.3 — Routing determinista (Pieza 2 + 3)**. Pieza 1 (enriquecer catálogo) HECHA. Falta Pieza 2 (trial-en-jaula + escáneres adoptados) y Pieza 3 (hook `UserPromptSubmit`). BLOQUEADO-POR: G0.6 (jail de ejecución cerrado, que Pieza 2 reutiliza).
- **G1.4 — Entrypoint conversacional de uso diario**. Flujo CLI/chat que use el sustrato existente, muestre en qué piensa, pida confirmación. BLOQUEADO-POR: G1.3.
- **G1.5 — Multi-hop memory (Fase 2.1)**. Sustrato listo. Recuperación en cadena. BLOQUEADO-POR: nada técnico, sí prioridad.
- **G1.6 — PII / crypto-shred de memoria (Fase 2.2, GAP GDPR)**. Aplicar `SaltStore` a `SqliteMemoryIndex`. El patrón ya existe en el gateway. BLOQUEADO-POR: nada técnico.

⛳ **HUECO de Capa 1**: métricas de "¿funciona para Tomás?" (Q7 de la síntesis) — frecuencia de uso, confirmaciones HITL por sesión, % sugerencias aceptadas sin editar. Sin esto, el desarrollo de Capa 1 es a ciegas. Definir antes de G1.1.

---

# CAPA 2 — HORIZONTE *(esqueleto + trampas marcadas)*

> No se toca hasta que 0 y 1 existan. Aquí investigación externa (deep research) **sí**
> será la herramienta correcta cuando lleguemos. Hoy solo se marcan las dos trampas
> que tu propia disciplina prohíbe, para que no se cuelen como "Gates".

- **G2.1 — Gateway cableado (entrypoint HTTP + verificador cliente + Technical File Anexo IV)**. GAP-1 GDPR ya cerrado (crypto-shred). Abiertos: Art. 26 (Read-API), Art. 11+Anexo IV. `atlas verify` ejecutable no existe (CRÍTICO en la síntesis). BLOQUEADO-POR: G0.5 (log persistente — sin esto un comprador no audita nada de ayer). **Este es el puente "asistente → gateway"**: el uso diario de Capa 1 genera el log que el gateway demuestra.
- **G2.2 — Publicación del paper (cs.CR)**. Texto completo y verificado. Falta endorsement. Decisión de la síntesis (Q5): publicar cuando llegue el endorsement, independiente de la API. No bloquea ni es bloqueado por código.
- **G2.3 — COSE/SCITT interop**. Dep real (ADR). Alto valor estratégico. BLOQUEADO-POR: G2.1. → deep research aquí.

### 🚩 TRAMPA 1 — Lenguaje híbrido (Rust o "uno mejor")
**No es un Gate. Viola `adopt-real-not-shell` y `stdlib > deps`.** Rust ya existe, ya es soberano, ya es verificable, ya está battle-tested. Inventar un lenguaje es donde los proyectos ambiciosos de una persona encuentran una forma elaborada de no entregar nunca. **Decisión congelada: se adopta Rust donde haga falta rendimiento/seguridad de memoria. No se inventa lenguaje** salvo que aparezca una razón específica que hoy no existe. Si aparece, entra por la membrana (OSM) como cualquier idea, no como Gate.

### 🚩 TRAMPA 2 — OS que corre "cualquier app de Windows/Linux/Android"
**No es un Gate con ese alcance. Es el *porqué derivado* a escala civilizatoria** — el mismo patrón que ya te comió ("ser el primer OS multiagente que lo hace todo"), ahora disfrazado de "reemplazar a Microsoft y Apple". Correr los tres ecosistemas es rehacer WINE + WSL + runtime Android a la vez: carreras de equipos grandes, décadas, y WINE sigue incompleto tras 30 años. Una persona no lo alcanza, y perseguirlo primero garantiza no entregar lo alcanzable.

**El sueño real, reescrito como objetivo viable**:
> **seL4 no necesita correr cualquier app. Necesita correr Atlas.** Un micronúcleo
> formalmente verificado sobre el que corre tu exoesqueleto = el sustrato de computación
> personal más verificable que existe, con la tesis intacta del bit a la intención sin
> un eslabón opaco. Eso es alcanzable **y** revolucionario. "Correr Windows" es el cebo
> que ahoga; "correr lo único que importa —tú y tu sistema— sobre un núcleo probado" es
> el horizonte de verdad.

BLOQUEADO-POR: Capa 0 + Capa 1 completas. → deep research (seL4, formal verification) cuando lleguemos, no antes.

---

## RESUMEN DE EJECUCIÓN

1. **En Claude Code, abres este manual y empiezas por G0.0.** No por el que más te apetezca.
2. Por cada Gate: resuelves los `[VERIFICAR EN REPO]` contra el código real, congelas las decisiones `🔒`, marcas las casillas.
3. **Un Gate solo entra a autobuild/dynamic workflow cuando sus cinco campos están resueltos y su done-criterion es machine-checkable.** Antes, no.
4. Cierras Capa 0 entera antes de profundizar Capa 1. El criterio de cierre está arriba.
5. La investigación externa (deep research) se reserva para Capa 2. Lo de Capa 0/1 se cablea contra tu repo, no contra la web.
6. Las decisiones importantes que no son de implementación (las `🔒` y los `⛳ HUECO`) se toman **ahora, en este chat o al inicio en Claude Code** — no a mitad de vuelo donde el modelo improvisa.

> Este manual ordena lo que ya tienes. No añade territorio. Si al anclarlo al repo
> aparece algo que no encaja en ninguna capa: o es basura que se borra (usa el grace
> period del graveyard F3, expira ~2026-07-21), o es un hueco que no sabías que tenías.
> Ninguna de las dos se arregla con un Gate nuevo en caliente.
