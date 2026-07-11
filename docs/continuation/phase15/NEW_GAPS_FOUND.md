# NEW_GAPS_FOUND — Fase 15 (mandatorio, honesto)

Formato: problema → clasificación → si bloquea Fase 15 o se mueve a
Fase 16 → estado.

1. **8 de 26 capacidades apuntaban a `gate_id` sin gate real registrado**
   (gate_accounting, gate_business_activation, gate_business_write,
   gate_computer_use, gate_data_export, gate_browser_submit,
   gate_memory_review, gate_official_submit no existían en
   `fixtures/governance/gates.json`). Efecto real: `PolicyEngine` seguía
   fail-closed (require_gate por defecto), pero el `gate_id` devuelto era
   un callejón sin salida para cualquier UI que quisiera resolverlo.
   — Clasificación: **architecture / security**. — **No bloqueaba** (el
   default seguía siendo seguro). — **FIJADO en esta fase**: 8 gates
   añadidos a `fixtures/governance/gates.json` + test de regresión
   `test_every_capability_gate_id_resolves_to_a_real_gate`.

2. **PolicyEngine y el evaluador v1 (`/permissions/evaluate`) son dos
   superficies paralelas** que comparten el mismo fixture de gates pero no
   convergen en un único punto de evaluación. Un capability nuevo añadido
   solo a uno de los dos no se refleja en el otro.
   — Clasificación: **architecture**. — No bloquea Fase 15 (documentado en
   D14 como decisión consciente: extender, no duplicar, pero la
   convergencia total queda pendiente). — Fase 16.

3. **`BusinessCore.activation.gate_id` no está enlazado a una ceremonia de
   Gate real** (el "Gate Engine" del pack, `docs/handoff/.../backend/
   GATE_ENGINE.md`, es solo una frase de una línea; no hay motor). Hoy
   `approve_activation` exige `approved_by` no vacío por código, no por
   una ceremonia auditable con evidencia adjunta.
   — Clasificación: **backend / security**. — No bloquea (el invariante
   "no hay atajo sin approved_by" sí se cumple). — Fase 16.

4. **Persistencia de `BusinessCoreEngine` con un solo `threading.Lock`**:
   protege contra carreras dentro de UN proceso, no entre procesos (bridge
   + CLI escribiendo `$ATLAS_HOME/business_core/state.json` a la vez
   podrían pisarse). El event store tiene el mismo patrón hoy (no es
   regresión de Fase 15, pero se hereda).
   — Clasificación: **backend / data model**. — No bloquea (mismo riesgo
   que ya existía, no empeorado). — Fase 16: lock de fichero o backend
   transaccional si el uso multi-proceso se vuelve real.

5. **Sesiones de onboarding en memoria del proceso** (`_sessions` dict en
   `product_routes.py`): reiniciar el bridge pierde toda sesión activa; no
   hay persistencia a disco ni expiración.
   — Clasificación: **backend / UX**. — No bloquea (es demo/Fase 15). —
   Fase 16: persistir sesiones (mismo patrón JSON que BusinessCoreEngine).

6. **Sin modelo de propiedad de sesión**: cualquier caller que conozca un
   `session_id` o `business_core_id` puede operar sobre él vía API; no hay
   autenticación/autorización por usuario todavía (el bridge entero es
   127.0.0.1 sin auth, heredado de Fase 4).
   — Clasificación: **security**. — No bloquea (consistente con el resto
   del bridge, que ya asume localhost de confianza). — Fase 16 si el
   bridge deja de ser solo-localhost.

7. **`AuthBroker.looks_like_secret` es heurístico y honestamente
   imperfecto**: puede dar falso negativo con secretos cortos/atípicos
   (documentado en `test_secret_leak_attempt_corpus_has_recognizable_secret_marker`,
   que tuvo que ajustarse porque el corpus de demo usa un secreto
   deliberadamente corto) y falso positivo con cadenas largas legítimas.
   — Clasificación: **security**. — No bloquea (es defensa en profundidad,
   no la única barrera: el AuthBroker de todas formas nunca persiste el
   VALOR, solo la referencia). — Fase 16: si se necesita más rigor, mover a
   un escaneo de patrones mantenido (p.ej. gitleaks rules) en vez de regex
   propia.

8. **Confianzas de `EntityCandidateExtractor` son constantes fijas en
   código** (0.9/0.6/0.95/0.7), no calibradas contra ningún dataset real ni
   configurables por sector.
   — Clasificación: **product / data model**. — No bloquea (es
   determinista y documentado, no pretende ser ML). — Fase 16 si se
   detecta que el umbral fijo produce mala UX real.

9. **Un conector con `connector_id` que NO empiece por `whatsapp_personal`
   pero que sea de facto una vía de WhatsApp personal** (p.ej. import de
   Telegram personal, o una futura receta mal nombrada) no quedaría
   cubierto por el patrón `whatsapp_personal*` del invariante duro
   `pol_hard_whatsapp_personal_send`. El invariante depende de una
   convención de nombres, no de una propiedad estructural del recipe.
   — Clasificación: **security**. — No bloquea (hoy solo existe un
   conector personal, y su `forbidden_capabilities` en el recipe ya cubre
   el caso independientemente). — Fase 16: añadir un campo estructural
   explícito `personal_channel: bool` al schema de receta en vez de
   inferir por nombre.

10. **Legal/licensing**: `whatsapp_business_platform.recipe.json` y
    `odoo_erp.recipe.json` declaran `legal_notes` de una línea; no hay
    registro central de términos de plataforma por conector (el pack
    pedía un "Legal/ToS registry per platform", `tasks/
    GAP_DETECTION_REGISTER.md` #8 del pack, ya listado allí como gap
    conocido del propio pack, no descubierto por mí).
    — Clasificación: **legal/licensing**. — No bloquea Fase 15. — Fase 16.

11. **Testing**: no hay test de carga/concurrencia sobre
    `BusinessCoreEngine` ni sobre las sesiones de onboarding (solo tests
    funcionales secuenciales).
    — Clasificación: **testing**. — No bloquea. — Fase 16 si el volumen
    real lo justifica.

12. **UX**: el catálogo de conexión (`/connections/catalog`) no distingue
    entre "disponible hoy" y "receta existe pero conector real no
    implementado" de forma visible para un consumidor no técnico — hoy
    hay que llamar a `/connections/test` con `mode=real` y leer
    `BLOCKED_BY_MISSING_DEPENDENCY` para descubrirlo.
    — Clasificación: **UX**. — No bloquea. — Fase 16: campo
    `implementation_status` en el catálogo.
