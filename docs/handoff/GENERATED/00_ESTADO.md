<!-- GENERADO por atlas handoff 2026-07-17T00:36:10.181894+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **T0.1+T0.2 CERRADAS — núcleo de sucesión vivo (2026-07-17, ola bootstrap)** —
  la memoria privada del harness YA vive en el sustrato con procedencia
  (58 registros `harness:*` + 2 `doctrine:*` en ~/atlas-mcp/memory.db, recall
  verificado: succession-proofing 0.700, doctrina 0.733, ambos con Merkle) y
  `atlas handoff` regenera el pack de sucesión desde fuentes vivas
  (docs/handoff/GENERATED/, MANIFEST con head_sha; `--check` exit 1 si STALE).
  Commits c0f2b72f (migración, dry-run default) + 2852e132 (handoff). El tipo
  `user` NO se migra (dato personal, queda en harness a propósito). Backups
  pre-migración: ~/atlas-mcp/memory.db{,.keys}.pre-t0-migration.bak.
  **Próxima acción:** T5.1 smoke de proveedores (recon + mini-plan) y cola
  [bootstrap] del addendum de auditoría 2026-07-17.
