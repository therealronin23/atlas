<!-- GENERADO por atlas handoff 2026-07-17T11:03:58.255703+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **OLA BOOTSTRAP COMPLETA — T0 núcleo de sucesión + T5.1 + cola de auditoría
  (2026-07-17)** — 8 commits: c0f2b72f/2852e132/68ff22f6 (T0: migración de 58
  memorias harness + 2 doctrinas al sustrato con procedencia, recall verificado
  0.700/0.733 con Merkle; `atlas handoff` genera docs/handoff/GENERATED/ con
  `--check` de frescura; backups pre-migración .pre-t0-migration.bak), 00f84212
  (revisión final de rama Sonnet: APROBADO CON ARREGLOS, 1 Important+6 Minor,
  arreglados I1/M2/M3/M5-M7, M4 no-cambio adjudicado), 6e145c04 (T5.1: el smoke
  YA existía desde 2026-07-09 y corrió hoy — el gap real era visibilidad;
  sección provider_smoke en `atlas reality`, que HOY aflora
  openrouter_qwen3_coder_free muerto), 5b2300a1 (umbral matched 0.8→0.5 MEDIDO:
  positivos 0.533-0.774 vs ruido 0.303-0.449; chunking de docs largos → T0.5b),
  6f08e972 (ADR-070: HermesRestAdapter retirado con evidencia de cero callers,
  -909 líneas; canal canónico = Kanban/atlas-twin). 4bis-1 CORREGIDO en la
  misma ola: el primer veredicto "sin bug" era incompleto — el mecanismo del
  tick es correcto pero load_bitemporal_into_kuzu re-embebía el histórico
  ENTERO (~29k llamadas ONNX CPU) en cada regen → ticks de HORAS, grafo
  perpetuamente STALE bajo flujo de commits (cazado en vivo con py-spy:
  scheduler 5h dentro de embed()). Arreglado con ingesta incremental por
  id path@commit_sha (re-pasada = 0 embeds, delta-only; test con embedder
  contador) — el re-sello FRESH ocurre solo tras el restart del daemon.
  4bis-4: .venv-scraping reconstruido (crawl4ai 0.9.2), marcador real
  success=200 vía SSRF bridge. Re-verificación: 183 tests dirigidos verdes +
  reality limpio. F2.6 PENDIENTE con prompt listo
  (docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md — la ola
  llegó con >50% de presupuesto consumido, regla bootstrap).
  EXTENSIÓN misma ola (orden operador "haz todos"): 52822e86 (trabajo daemon
  commiteado) + 18af7e0c (higiene INDEX: 500 handoff→historico, --strict
  limpio) + aa2f8adc (wrapper OAuth sin secretos en argv + runbook — la
  ROTACIÓN queda para el operador) + cf5ce30b (ciclos scheduler loguean
  fallos con traceback) + 6a533d05 (12-fuentes: Groq NO —413 TPM medido—,
  Gemini free SÍ, 12 exclusiones deliberadas, cobertura 98.3%→99.3%, quedan
  5 grandes re-intentables al reset del cupo; + guard pre-push refs/codex/*).
  F2.6 INTENTADA en real: 401 token revocado → prerequisito operador
  `claude setup-token` (doc F2.6 actualizado).
  **Próxima acción:** operador: rotar secret OAuth (runbook
  docs/operations/oauth_rotation_google_workspace.md) + claude setup-token
  (desbloquea F2.6) + re-run 5 fuentes al reset (comando en ledger campaña).
  Siguiente ola: T2.1 consola mínima ∥ T0.5b digestión.
