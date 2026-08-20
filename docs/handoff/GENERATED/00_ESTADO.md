<!-- GENERADO por atlas handoff 2026-08-20T21:20:48.578936+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-20 — CR-001: L1 Groq migrado; F2.6 sigue `due`, sin PASS
  forzado.** Groq retiró `llama-3.3-70b-versatile` para los tiers
  free/developer (error directo `model_not_found`); el catálogo y sus callers
  pasan a `groq_gpt_oss_120b` / `openai/gpt-oss-120b`, reemplazo oficial. La
  corrida limpia `f26:20260820T195303959278+0000` sí dejó transcript y receipt
  en HEAD `90864f7`, pero el grader automático devolvió `fail` (1/6): el
  transcript muestra que su primera consulta de grafo recibió estado `STALE`.
  No hubo verificación semántica independiente, así que el gate permanece
  `due`. Los reintentos posteriores no deben fingir capacidad: Groq está al
  95% del presupuesto local y falló cerrado antes de inferir; OpenRouter no
  tenía crédito suficiente para el máximo solicitado. **Verificado:** suite
  completa `6023 passed, 6 skipped, 27 deselected` (exit 0), `27` computer-use
  (exit 0), mypy de 361 módulos, canon 2.118 y Merkle; `docs_index_audit
  --strict` sigue `FAIL` por 334 documentos sin indexar (deriva amplia previa).
  **Próxima acción:** Frontier Reconciliation decide proveedor/presupuesto y
  repetir F2.6 completa sólo en checkout limpio; no reinterpretar el 1/6 como
  aprobación.
