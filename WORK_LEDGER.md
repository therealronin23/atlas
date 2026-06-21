# WORK LEDGER — estado vivo de la matrioska

Fuente única del "¿dónde estamos?". Una línea por nodo activo. Se actualiza al abrir/cerrar
un nodo. Sobrevive a compactaciones: leer esto al retomar y se está orientado.
Detalle por feature en su design doc; el porqué/lecciones en memoria (`MEMORY.md`).

Formato: `[estado] nodo — próxima acción / bloqueado-por`. Estados: ✅ hecho · 🔄 en curso ·
⬜ pendiente · 🧱 muro (tipo-3) · ⏸ diferido.

## Línea activa: sustrato de memoria verificable (Fase 1 + Fase 2)

Design doc: `docs/design_verifiable_memory.md` · rama: trabajo mergeado a `main`.

- ✅ **Fase 1 — Sustrato (1a–1d)** — completa, auditada, deudas tipo-1 cerradas.
  - ✅ 1a índice persistente + Merkle + cableado · ✅ 1b PatternAbstractor · ✅ refactor motor/inquilino
  - ✅ 1c-seguridad (Garak real) · ✅ 1c-motor · ✅ 1d-a temporal/supersesión · ✅ 1d-b tiers
  - ✅ auditoría pre-merge (3 fixes) · ✅ deudas tipo-1 (ciclo de vida)
- 🧱 **Muro 1c — intención-vs-tema** — atacado (contrastive): separación ×2-3, FP fronterizo ~33%,
  no es detector usable. Acotado. `docs/immune_intent_vs_topic_contrastive.md`.
- 🔄 **Fase 2 — Huecos abiertos** (checklist en design doc):
  - ⬜ **2.1 multi-hop** ← SIGUIENTE
  - ⬜ 2.2 PII/crypto-shredding (fundacional + GAP-1 EU AI Act)
  - ⬜ 2.3 evaluación honesta (diseñada, falta construir) · ⬜ 2.4 envenenamiento (parcial)
  - ⬜ 2.5 fuga entre usuarios/tenancy · 🧱 2.6 personalización-vs-contaminación · ✅ 2.7 cold-start (conceptual)

## Otras líneas (no activas ahora)

- ⏸ Paper `subject_enforced_completeness` — listo; subida a arXiv = acción del usuario.
- ⏸ Deuda diferida del sustrato: multihilo (sin consumidor), IC/corpus mayor en 1c.
