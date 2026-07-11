# ADR-066 — Visual Orchestrator Territory y Coding+Research Territories: parked

- Estado: aceptado (2026-07-11)
- Contexto: la auditoría de recuperación de fases F1-F16
  (`docs/continuation/phase_recovery/`) encontró que
  `docs/handoff/atlas_build_pack/docs/atlas-bible/17_PHASES_ROADMAP.md`
  define **Fase 5 — Visual Orchestrator Territory** (canvas tipo n8n, node
  palette, inspector, graph JSON export/import, graph compiler, ejecución
  visual vía eventos) y **Fase 6 — Coding + Research Territories**
  (editor Monaco con diff/tests; árbol de preguntas/fuentes/evidencia para
  investigación) con entregables y "gate" explícitos, y que ninguna de las
  dos se ejecutó nunca. No existe código (`grep -ri "react-flow\|monaco"
  ui/ src/` → sin resultados), ningún ADR previo las menciona, y
  `docs/INDEX.yaml` marca el documento fuente como `status: propuesto`
  desde su ingesta — nunca promovido ni revisitado.

## Decisión

1. **Se parkean formalmente Fase 5 y Fase 6 de `17_PHASES_ROADMAP.md`.**
   No se implementan en esta sesión ni se planifican para F17 sin pedido
   explícito del operador.
2. **Motivo de fondo, no solo de alcance**: la decisión D11 de Fase 15
   (`docs/continuation/phase15/DECISION_REVIEW.md` y ADR-059) ya estableció
   que `ui/atlas-shell` es un **arnés de validación, no la UX final de
   Atlas**. Invertir en un canvas visual completo (React Flow + node
   palette) o en un editor de código embebido (Monaco) dentro de un
   arnés que se sabe temporal sería trabajo que probablemente se
   reescribiría al construir la superficie nativa/líquida real — el mismo
   razonamiento que ya mató el rediseño JARVIS del shell antes de
   escribirse código (ver memoria de sesión
   `atlas-os-phase15-product-os-2026-07-10`).
3. **No es un rechazo del concepto**, es un parking por secuencia: cuando
   exista la superficie nativa (post Presence Engine / Liquid Workbenches,
   ver `WHAT_WAS_NOT_IMPLEMENTED.md`), Visual Orchestrator y las
   Territories son candidatos legítimos a reabrir.
4. **F15 y F16 NUNCA dependieron de esto** — verificado en
   `docs/continuation/phase_recovery/F15_F16_DEPENDENCY_AUDIT.md`:
   ninguna ruta de `fabric/`/`business/`/`product_routes.py` referencia
   nada relacionado con un canvas de workflows ni con edición de código
   embebida.

## Consecuencias

- `docs/continuation/KNOWN_RISKS.md` y `CONTINUATION_STATE.md` registran
  este parking para que ninguna sesión futura las busque de nuevo
  asumiendo que se perdieron por descuido.
- Si en el futuro se decide construirlas, este ADR debe superseder-se
  explícitamente con la decisión de reabrir, no reinterpretarse en
  silencio.
