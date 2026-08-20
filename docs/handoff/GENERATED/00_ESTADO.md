<!-- GENERADO por atlas handoff 2026-08-20T18:41:53.390489+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-13 — GoldenRoute admite Markdown raíz sin abrir una autoridad
  genérica sobre el root.** Request→ColdUpdate permite modificar un fichero
  `*.md` raíz sólo si ya existe, es regular, no es symlink y ambos lados del
  patch nombran la misma ruta; creación, borrado, cambio de ruta y
  `agents.md` fallan cerrados. La aceptación completa modifica `README.md`
  únicamente tras validate→approve→apply y prueba que el puntero de cinco
  líneas queda byte-idéntico. No se encontró una petición README raíz previa
  identificable en las 295 propuestas almacenadas, por lo que no se inventó
  ni aplicó una. El ensanchamiento de superficie fue cuestionado y quedó
  documentado en el dossier ADR-069; no cambia la autoridad durable ni el
  requisito HITL. **Verificado:** suite global `6023 passed, 6 skipped, 27
  deselected` (exit 0), mypy estricto 361 módulos, canon 2.118 registros,
  Merkle y diff-check (exit 0). **No cerrado:** `docs_index_audit --strict`
  sigue en exit 1 por deriva preexistente/amplia; `docs/INDEX.yaml` pertenece
  a los cambios del operador y no se tocó. **Próxima acción:** commit acotado,
  grafo/handoff y GoldenRoute separado para la memoria raíz solicitada.
