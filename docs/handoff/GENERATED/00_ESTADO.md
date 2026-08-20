<!-- GENERADO por atlas handoff 2026-08-20T19:37:08.030914+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-20 — L1 Groq migrado tras retirada de Llama 3.3; F2.6 sigue due
  hasta transcript válido.** Groq retiró `llama-3.3-70b-versatile` para los
  tiers free/developer (error directo `model_not_found`); el catálogo y sus
  callers pasan a `groq_gpt_oss_120b` / `openai/gpt-oss-120b`, reemplazo
  oficial. Tres dispatches F2.6 anteriores dejaron receipts honestos pero
  transcript vacío: Llama retirado; Qwen era L0 frente a una rúbrica L1; y
  Hermes/OpenRouter no ofrecía endpoint de tool use. **Verificado:** 62 tests
  de gate/council/workbench, exit 0; 65 tests ColdUpdate/SelfBuild, exit 0.
  **Próxima acción:** commit acotado, reiniciar el servicio y ejecutar una
  única F2.6 con `--provider groq_gpt_oss_120b` sobre checkout limpio; sólo un
  transcript gradeable puede mover el gate.
