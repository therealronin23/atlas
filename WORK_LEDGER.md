# WORK LEDGER — estado vivo de la matrioska

Fuente única del "¿dónde estamos?" (autoridad del ESTADO; el design doc NO duplica estado).
Una línea por nodo activo. Se actualiza EN EL MISMO COMMIT que el trabajo (parte de "done").
Sobrevive a compactaciones: leer esto al retomar y se está orientado.
Detalle por feature en su design doc; el porqué/lecciones en memoria (`MEMORY.md`).
Higiene: ≤ ~40 líneas; podar nodos cerrados a la sección de archivo cuando crezca.

Formato: `[estado] nodo — próxima acción / bloqueado-por`. Estados: ✅ hecho · 🔄 en curso ·
⬜ pendiente · 🧱 muro (tipo-3) · ⏸ diferido.

## Línea activa: sustrato de memoria verificable (Fase 1 + Fase 2)

Design doc: `docs/design/design_verifiable_memory.md` · rama: trabajo mergeado a `main`.

- ✅ **Fase 1 — Sustrato (1a–1d)** — completa, auditada, deudas tipo-1 cerradas.
  - ✅ 1a índice persistente + Merkle + cableado · ✅ 1b PatternAbstractor · ✅ refactor motor/inquilino
  - ✅ 1c-seguridad (Garak real) · ✅ 1c-motor · ✅ 1d-a temporal/supersesión · ✅ 1d-b tiers
  - ✅ auditoría pre-merge (3 fixes) · ✅ deudas tipo-1 (ciclo de vida)
- 🧱 **Muro 1c — intención-vs-tema** — atacado (contrastive): separación ×2-3, FP fronterizo ~33%,
  no es detector usable. Acotado. `docs/reference/reports/immune_intent_vs_topic_contrastive.md`.
- 🔄 **Fase 2 — Huecos abiertos** (checklist en design doc):
  - ⬜ **2.1 multi-hop** ← SIGUIENTE
  - ⬜ 2.2 PII/crypto-shredding (fundacional + GAP-1 EU AI Act)
  - ⬜ 2.3 evaluación honesta (diseñada, falta construir) · ⬜ 2.4 envenenamiento (parcial)
  - ⬜ 2.5 fuga entre usuarios/tenancy · 🧱 2.6 personalización-vs-contaminación · ✅ 2.7 cold-start (conceptual)

## Gate de gobernanza (tipo-2 — orden = base de todo)

Estándar: `docs/governance/REPO_STANDARD.md` · honestidad: `docs/governance/CAPABILITIES.md`.

- ✅ **F0** estándar + CAPABILITIES + manía `wire-before-claim` (anti-vapor) cableada en AGENTS.md
- ✅ **F1** limpieza riesgo-bajo: 5 artefactos LaTeX a .gitignore, 7 scratch de raíz a graveyard,
  `.atlas-audit-home` vacío borrado
- ✅ **Huérfanos cerrados** (0 importadores no-test) → cuarentena: witness_server, log_behavioral,
  kyc_binding (+ tests). Registrados en CAPABILITIES + graveyard MANIFEST. Suite 2041 verde.
- ⬜ **F2** reorganizar `docs/` a la taxonomía (mover + actualizar refs)
- ⬜ **F3** código muerto / zombies (auditoría de cableado completa) · ⬜ **F4** migrar Gates/seals + cierres roll-up
- ⬜ ciclo de saneamiento recurrente establecido

## Otras líneas (no activas ahora)

- ⏸ Paper `subject_enforced_completeness` — listo; subida a arXiv = acción del usuario.
- ⏸ Deuda diferida del sustrato: multihilo (sin consumidor), IC/corpus mayor en 1c.
