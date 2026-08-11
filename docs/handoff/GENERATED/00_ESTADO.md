<!-- GENERADO por atlas handoff 2026-08-11T21:29:24.457259+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-06 — CORRECCIÓN DE REGISTRO: dos commits contienen cambios que su
  mensaje no menciona.** `git add <ficheros> && git commit` commitea el ÍNDICE
  ENTERO, no sólo lo añadido; lo di por acotado y no lo está.
  - `f1ee888` ("fix(mcp): el trunk de ingeniería…") contiene además los **30
    renombrados de `ui/atlas-shell/` → `docs/archive/_graveyard/`** que el
    operador ya tenía staged (archivado de ADR-085). Trabajo del operador, no
    del commit que lo firma.
  - `582ae6b` ("fix(pre-commit)…") contiene además los **16 renombrados de
    `compose_micropoc`/`qt_micropoc` → graveyard**.
  El CONTENIDO de ambos es correcto y es exactamente lo que ADR-085 manda; lo
  incorrecto es la atribución. No se reescribe la historia (`no-rewrite-git-history`,
  y además ya está fusionado). Esta entrada es el rastro para quien lea el log.
  Patrón correcto a partir de ahora: `git commit <rutas> -F -`.
