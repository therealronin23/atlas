# T0.5b paso 3 — síntesis del corpus (gaps + contradicciones + plan v2)

Estado: **borrador para revisión del operador**, no vigente hasta aprobación. Cierra
`atlas_master_plan.md` §T0.5.b (b): "Digestión total del corpus contra este plan...
% de cobertura + lista de gaps + lista de contradicciones; plan v2 con fuentes citadas
y lista explícita de 'revisado y descartado'".

Ejecutado según el diseño de
`docs/superpowers/plans/2026-07-22-t05b-paso3-parallel-digestion-BRIEF.md`: 4 divisiones
por proveedor (Groq→T0/T1, OpenRouter→T2/T3, NVIDIA→T4/T5/T6+histórico+ADRs+candidata,
Gemini→sin_clasificar) + auditoría cruzada rotada (ninguna división se audita a sí
misma) + esta síntesis, hecha por la sesión orquestadora, no delegada.

Datos crudos (por documento, digest + auditoría) en `docs/knowledge/t05b_paso3/`:
`corpus_digest_consolidated.json` (708 registros, veredicto ya con correcciones de
auditoría aplicadas) y los 4 pares `digest_X.json`/`audit_X.json` originales.

## 0. Cobertura y método

- **708/708 documentos procesados** (0 fabricados; división D declaró explícitamente
  0 pendientes tras cubrir el lote completo de 459).
- **Auditoría cruzada real, no trámite**: de 191 registros revisados por los 4
  auditores (100% de gaps/contradicciones + muestra ~15-24% del resto), **17 fueron
  corregidos** (8.9%). El caso más significativo: 2 de los 3 "gap" que reportó la
  División A resultaron ya estar implementados en código (verificado por grep contra
  `src/atlas/`) — la auditoría cruzada evitó que 2 falsos gaps entraran al plan v2.
  Detalle de las 17 correcciones en los ficheros `audit_X.json`.
- **Veredicto final (post-auditoría)**: `historico` 496 · `alimenta_item` 129 ·
  `gap` 50 · `candidata` 33.

## 1. Gaps consolidados (50 documentos → 4 clusters temáticos reales)

Un "gap" es un documento que describe algo real y vigente que ninguna sección T0-T6
del plan maestro cubre hoy. Los 50 gaps NO son 50 temas distintos — se agrupan en 4
clusters, cada uno con su propia pregunta de disposición para el operador.

### 1.1 Cluster Osmosis / Compliance Gateway (~29 de los 50 gaps — el más grande)

Fuentes representativas: `docs/membrana/OSM-000_membrana.md` (meta-doc del mecanismo,
vivo desde 2026-06-17, 40+ propuestas OSM rastreadas, varias ya "Absorbida" con código
real en `src/atlas/security/`, `src/atlas/transparency/`), `docs/compliance/eu_ai_act_mapping.md`
+ `eu_ai_act_gaps_2026-06-18.md` + `technical_file_annex_iv.md`, `docs/outreach/outreach_emails.md`
(envío real a AESIA/Anthropic), `docs/outreach/paper/paper_subject_enforced_completeness.md`
(paper ~10k palabras), `docs/demo/README.md` (implementación de referencia reproducible),
`docs/audits/reports/{pyrit_crescendo_report,redteam_campaign_report}.md` (red-team real).

Verificado (auditoría División D): grep de "osmosis/membrana/compliance/completeness"
contra `atlas_master_plan.md` completo → 0 resultados fuera de una línea genérica en
T4.2. Esto es un cluster real, sustancial, con código+ADRs+papers+outreach ya en curso,
sin ningún tramo T0-T6 que lo reconozca.

**Contradicción asociada** (ver §2.1): `docs/design/atlas_synthesis_2026-06-26.md`
(2026-06-26) trataba Osmosis como una de solo DOS direcciones estratégicas co-iguales
del proyecto entero, y dejaba la pregunta abierta explícitamente sin resolver. El plan
maestro vigente (2026-07-16) no la resuelve — simplemente no la menciona.

**Pregunta para el operador (decisión N3, Cónclave si hace falta)**: ¿Osmosis/Compliance
Gateway sigue siendo una dirección estratégica activa que merece su propio tramo (T7?),
o fue implícitamente aparcada cuando el plan maestro se reenfocó 100% en sucesión-primero
y debe formalizarse como PARK con ADR explícito? Ahora mismo es ninguna de las dos cosas
de forma explícita — es el vacío más grande que dejó esta digestión.

### 1.2 Cluster Product OS / Business Core / Integration Fabric (~13 gaps, más matizado)

Fuentes: `docs/handoff/atlas_product_os_liquid_ui_pack_v1/product/{30_ATLAS_BUSINESS_CORE,32_ATLAS_NATIVE_ERP_CORE}.md`,
`docs/architecture/ARCHITECTURE_MAP.md`, `docs/handoff/atlas_product_os_liquid_ui_pack_v1/backend/00_BACKEND_CAPABILITY_MAP.md`,
`docs/design/atlas_max_capability_roadmap.md`.

**Matiz importante de la auditoría (División A, sobre `RECOMMENDED_PHASE_16.md`)**:
de las 8 recomendaciones de ese documento, **6 ya están implementadas** (PolicyEngine↔
`/permissions/evaluate`, Gate Engine, Gmail connector, Sector/Objective Registry,
Legal/ToS registry, `personal_channel`) — verificado por grep contra código real. Solo
**2 siguen siendo gap real**: persistencia de `OnboardingSession` a disco y una UI
mínima de `/connections`/`/business`. Esto NO es "Fase 15/16 sin representación" en
bloque — es una pieza YA construida (Fase 15/16, ADR-060 a ADR-065) que el plan maestro
T0-T6 simplemente no cita en ningún lado, más 2 huecos reales y pequeños dentro de ella.

**Propuesta concreta (no decidida, para revisión)**: no necesita tramo nuevo. Encaja
como nota informativa en T0.1 (`atlas handoff` — sección "quién es quién"/estado vivo)
y como 2 líneas de backlog bajo el T-item que el operador designe (T1 por ser
infraestructura, o un T-item de negocio si se crea). El gap real es de tamaño pequeño
(2 de 8 puntos), el resto es solo falta de cita, no falta de trabajo.

### 1.3 Cluster seguridad/verificabilidad (~4 gaps)

`docs/decisions/adr/adr_043_verifiable_authorization.md`, `adr_053_gateway_trust_completeness.md`,
`adr_056_red_team_tooling.md`, `adr_024_observability_logging_v2.md`. Estos son ADRs
aceptados con código real (verificado: `src/atlas/logging/{microledger,telemetry_bus,
operational_wal}.py` existen) que se solapan parcialmente con el cluster Osmosis (1.1) —
misma pregunta de disposición aplica.

### 1.4 Miscelánea (4 gaps sueltos, sin cluster)

`docs/design/future_work_ideas.md` (ideas de literatura SCITT/COSE para el paper de
completeness — depende de la decisión sobre 1.1), y 3 documentos del pack Product OS
(Device/App Control Fabric, Cross-Device Atlas, Secure Personal Mesh) que describen una
dirección de control multi-dispositivo sin tramo propio — más cercano a T6 (elasticidad
multi-hardware) que a cualquier otro tramo; candidato natural a nota bajo T6 si el
operador confirma que sigue vigente.

## 2. Contradicciones consolidadas (43 flags → 3 clusters + 2 sueltas)

### 2.1 Osmosis como "dirección co-igual" vs. plan maestro que no la menciona

Ya cubierto en 1.1 — es la contradicción que motiva la pregunta de disposición de ese
cluster. Fuente: `docs/design/atlas_synthesis_2026-06-26.md` vs. ausencia total en
`atlas_master_plan.md`.

### 2.2 Churn de stack UI: Slint/wgpu → Tauri+React → web-first → apps dedicadas (12 docs)

Cadena real y verificada (grep confirmó 0 menciones de Slint/wgpu en la investigación
más reciente): `docs/handoff/atlas_product_os_liquid_ui_pack_v1/research/02_UI_TECH_DECISION_REPORT.md`
+ `docs/design/UI_QUALITY_GATE.md` (candidato: Slint+wgpu) → `docs/handoff/atlas_build_pack/`
+ `atlas_fable5_handoff_v1/` (candidato: Tauri+React+TS, 6 docs) → `docs/architecture/DECISION_REVIEW.md`
D3 (web-first Vite+React, ADR-059) → `docs/decisions/adr/adr_071_dedicated_apps_supersede_web_first_ux.md`
(supersede a ADR-059, apps dedicadas Linux+Android) → `docs/design/ui/research/{research-flutter,research-tauri-rn}.md`
(2026-07-17, no contemplan Slint en absoluto).

**Verificado por auditoría (División C): NO es una contradicción activa.** ADR-059→
ADR-071 es supersesión explícita, ya resuelta en el corpus vigente — ambos ADRs se citan
mutuamente. El único hueco real es cosmético: ADR-059 nunca actualizó su propio campo
"Estado" para apuntar a ADR-071. **Revisado y descartado como contradicción viva** — los
6 docs `atlas_build_pack`/`atlas_fable5_handoff_v1` que aún prescriben Tauri+React son
correctamente `historico`, no una contradicción sin resolver.

**Acción propuesta (pequeña, mecánica)**: añadir una línea "Estado: SUPERSEDED por
ADR-071" al encabezado de `adr_059_atlas_os_ui_stack_web_first.md` — cosmético, no
requiere decisión N3.

### 2.3 Citas alucinadas a ADR-054 en el archivo `vscode_session_2026-06-17/` (3 docs)

`membrane_design.md` y `osmosis_filter_design.md` afirman implementar "la hipermutación
descrita en ADR-054"; el propio `README.md` de ese archivo ya documenta que es una cita
alucinada (ADR-054 real trata sandbox jail, no membrana/osmosis) y que la carpeta entera
fue archivada el 2026-06-17 por esa razón + colisión de vocabulario + imports rotos.
**Revisado y descartado**: ya está correctamente archivado y auto-documentado; no
requiere ninguna acción — el propio corpus ya se auto-corrigió. Único hallazgo nuevo de
la auditoría (División D): `docs/operations/security_usage.md` describe código de esta
MISMA carpeta archivada como si fuera real y vigente, pero fue movido a `docs/operations/`
un mes después del archivado (2026-07-10), durante una reorganización masiva — un
"afirmación caducada" real que el lint T0.5.c debería atrapar. **Acción propuesta**:
borrar o archivar `docs/operations/security_usage.md` (describe clases que no existen en
`src/atlas/security/` — verificado por grep).

### 2.4 `docs/decisions/gates/CLOSURE.md` cita una sección de AGENTS.md que ya no existe

Afirma "el proyecto pivotó... citando AGENTS.md §Current Direction"; el AGENTS.md actual
solo tiene `## Current Identity`, con contenido distinto. **Revisado y descartado como
vigente** — es un artefacto de cierre de una fase anterior, correctamente clasificado
`historico`; no requiere acción salvo que alguien lo lea sin contexto y se confunda (ya
está en `docs/decisions/gates/`, no en un lugar que se presente como estado actual).

### 2.5 Colisión de nomenclatura "F2.6" (2 conceptos distintos, mismo código corto)

`docs/superpowers/specs/2026-06-25-f2-6-personal-factual-design.md` (backlog item
"f2-6-personalization-vs-contamination", CERRADO, status: done) vs. F2.6 = test de
sucesión (T0.3 del plan maestro, el que persigue el Frente 1 de esta misma sesión).
**Revisado y descartado como riesgo activo** (el primero ya está cerrado y no se toca),
pero **vale la pena una nota** en el propio doc F2.6-succession-test para desambiguar
si alguien busca "F2.6" en el repo y encuentra dos cosas.

### 2.6 `fable5_build_doctrine.md` discrepa del orden secuencial T0→T6

Recomienda adelantar T5.1 (smoke de proveedores) antes de T1 y correr T2.1 en paralelo
con T1, contra el orden estricto "cada tramo habilita el siguiente" de §5 del plan
maestro. Nota: T5.1 ya está CERRADA (§7 del plan maestro, 2026-07-17) así que ese punto
concreto quedó resuelto por los hechos. El desacuerdo sobre paralelizar T2.1/T1 sigue
abierto pero es de bajo riesgo (la doctrina es del modelo saliente, ya marcada para
ingerir al sustrato como criterio histórico, no como mandato — T0.5.a del propio plan).
**No requiere acción** más allá de la ingesta ya planeada.

## 3. Revisado y descartado (explícito, por pedido del plan maestro)

- Vocabulario árbol de taxonomía (Tramo) — ver Frente 2 de esta misma sesión,
  `docs/superpowers/specs/2026-07-15-succession-ecosystem-design.md` §5: descartado
  formalmente con evidencia, no aporta valor sobre columnas existentes del mapa real.
- Contradicción ADR-059↔ADR-071 (§2.2 arriba): NO es contradicción activa, ya resuelta.
- Citas alucinadas ADR-054 (§2.3): ya auto-corregidas en el propio archivo.
- `docs/decisions/gates/CLOSURE.md` (§2.4): histórico correcto, sin acción.
- Colisión de nombre F2.6 (§2.5): sin riesgo activo, solo nota de claridad pendiente.
- 2 de los 3 gaps originales de la División A (`RECOMMENDED_PHASE_16.md` en 6/8 puntos,
  `recording-decider-design.md` completo): ya implementados en código, no son gap —
  corregido por auditoría cruzada, no por mí.
- `docs/operations/security_usage.md` como "gap": corregido a histórico caducado por
  auditoría (D) — pasa a ser una acción de limpieza (§2.3), no un gap de cobertura.

## 4. Plan v2 — propuesta (borrador, requiere Cónclave+operador para cualquier tramo nuevo)

Por regla del propio plan maestro (§6: "reordenar tramos o añadir/matar uno: Cónclave +
operador (N3)"), esta síntesis NO decide ni edita `atlas_master_plan.md`. Propone:

1. ~~**Decisión N3 pendiente real**~~ **RESUELTO por el operador (2026-07-23)**:
   Osmosis/Compliance Gateway "sigue normal" — permanece como dirección activa en su
   forma actual (sin tramo propio nuevo, sin PARK formal). No requiere ninguna edición
   de `atlas_master_plan.md` en este momento; el cluster de ~29 gaps queda documentado
   aquí como referencia, no como trabajo bloqueado.
2. **Acción mecánica, sin decisión N3**: nota informativa en T0.1/`atlas handoff` sobre
   Product OS (Fase 15/16) + 2 huecos reales de `RECOMMENDED_PHASE_16.md` como backlog.
3. **Acción mecánica, sin decisión N3**: cosmética en ADR-059 (apuntar a ADR-071),
   limpieza/archivado de `docs/operations/security_usage.md`, nota de desambiguación
   F2.6 en el doc del test de sucesión.
4. **Sin acción**: todo lo demás (§3, revisado y descartado).

## 5. Cierre honesto para WORK_LEDGER

T0.5b paso 3 queda **cerrado en su totalidad para la parte mecanizable** (708/708 docs
clasificados y auditados, 0 fabricados) y **parcial en la parte de juicio final**: la
síntesis identifica una decisión N3 real y pendiente (Osmosis/Compliance Gateway) que
esta sesión NO tiene mandato para tomar por sí misma — queda explícitamente para el
operador, con la evidencia ya reunida para que la decisión sea informada en vez de
especulativa.
