# MEMORY

Lecciones operativas que explican el porqué de las reglas vivas. El estado vive en
`WORK_LEDGER.md`; los detalles de diseño viven en `docs/design/`.

- `absorb-without-cloning`: Atlas asimila capacidades externas de Cursor, Codex,
  Claude Code, MemGPT/MemPalace u otros sistemas sin convertirse en un fork ni
  aceptar su techo.
- `dependency-floor-honesty`: los bumps de floor aceptados en `pyproject.toml`
  se documentan como compatibilidad existente, no como dependencias nuevas.
- `adversarial-audit-no-assumptions`: ante una auditoría amplia, investigar lo
  dudoso, usar grafos y evidencia viva, corregir dentro del alcance y separar
  siempre “configurado”, “probado en aislamiento” y “verificado en vivo”.
