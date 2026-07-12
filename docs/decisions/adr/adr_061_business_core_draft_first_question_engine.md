# ADR-061 — Atlas Business Core draft-first, Adaptive Question Engine y Legacy Link

- Estado: aceptado (2026-07-10)
- Contexto: el pack exige que Atlas pueda generar su propio CRM/ERP mínimo
  cuando el usuario no tiene ninguno, sin clonar Salesforce/Odoo, y sin
  activar nunca estructura de negocio en silencio. También exige preguntas
  de onboarding concretas (nunca "¿cómo funciona tu empresa?").

## Decisión

1. **Un solo Business Core modular, no dos sistemas CRM/ERP**: 23 kinds de
   entidad (`EntityKind`) agrupados en `CRM_KINDS`/`ERP_KINDS`/
   `SHARED_KINDS` como vistas sobre el mismo store — evita clonar un ERP
   grande (DO_NOT_DO del pack).
2. **Draft-first con un único camino a `active`**: `create_draft` →
   `request_activation` (→ `pending_activation`) → `approve_activation`
   (humano explícito, `approved_by` obligatorio). `approve_activation`
   sobre un core que no está `pending_activation` lanza `ActivationError`;
   no existe atajo de código que salte el paso intermedio
   (`test_cannot_reactivate_already_active_core`,
   `test_business_core_starts_draft_and_requires_gate_to_activate`).
3. **`EntityCandidate.requires_review` es `Literal[True]` en el modelo**
   (no solo convención): `promote_candidate` exige `reviewed_by` no vacío
   o lanza `ReviewRequiredError`. Ningún candidato extraído se convierte
   solo en entidad de negocio.
4. **AdaptiveQuestionEngine implementa el lazo completo**: pregunta →
   respuesta → interpretación mostrada → confirmación → siguiente. Reglas:
   - `build_preview` rechaza si queda alguna respuesta sin `confirmed=True`
     (`test_full_onboarding_loop_requires_confirmation_before_progress`).
   - La rama "no sé" (`uncertain=True`) y la omisión (`skip_question`,
     que internamente también marca `uncertain=True`) son válidas — no
     bloquean el avance — pero **no conceden** `resulting_entities` /
     `resulting_capabilities` / `resulting_workbenches`: una incertidumbre
     no desbloquea permiso (`test_uncertain_answer_does_not_grant_capabilities`).
   - Cada pregunta declara `why_this_is_needed` y
     `what_atlas_will_do_with_it` como campos **obligatorios del schema**:
     una pregunta vaga no valida (`test_question_model_demands_concreteness`).
5. **Legacy Link Layer**: `propose_link` construye siempre con
   `sync_enabled=False` sin importar el modo pedido; `enable_sync` exige
   `human_approved=True` o lanza `SyncNotApprovedError`. La canonicidad
   (`external_canonical`/`atlas_canonical`/`hybrid_canonical`) se deriva
   explícitamente del modo del link, nunca queda implícita.
6. **EntityCandidateExtractor es determinista sobre evidencia estructurada**
   (listas de dicts ya parseadas), no NLP ni juicio de modelo: confianza
   fija por regla (p.ej. contacto con nombre+email → 0.9, solo email →
   0.6). Mantiene la línea "el modelo nunca es frontera de seguridad" del
   Integration Fabric (ADR-060) aplicada a extracción de datos.

## Consecuencias

- 5 packs de preguntas por sector (gestoría, restauración, ventas/CRM,
  software/IT, vida personal), todo en `fixtures/question_packs/`.
- Persistencia de Business Core en `$ATLAS_HOME/business_core/state.json`
  (JSON simple con lock, mismo patrón que `OsEventStore`); explícitamente
  parametrizable (`path=`) para que los tests nunca toquen el
  `$ATLAS_HOME` real (mismo bug clase que forzó la app perezosa en Fase 4 —
  se detectó y corrigió ANTES de que escribiera nada real, ver
  `PHASE_15_COMPLETION_REPORT.md`).
- Deferred a Fase 16: activación con Gate real de `governance/` (hoy el
  `gate_id` es descriptivo, no está enlazado al motor de gates general);
  ingesta de candidatos promovidos al índice canónico de memoria.
