# Audit + premortem — context collapse recovery

Fecha: 2026-07-07.
Nodo matrioska: operating context hygiene.
Tipo: 2, foundational/correctness. Arreglar antes de seguir apilando features.
Skill usada: `code-review-and-quality`.

## Verificación ejecutada

- `atlas reality --json`: repo dirty en `main`, Merkle OK, runtime OK, tests inicialmente desconocidos.
- `atlas reality --run-checks --include-browser --json`: core OK, mypy OK, browser tests fallan.
- `python -m pytest tests/ -q`: 2822 passed, 2 skipped, 27 deselected, 6 warnings in 340.83s.
- `python -m mypy src/atlas/`: Success, 216 source files.
- `python -m pytest tests/ -q -m "computer_use"`: 16 failed, 10 passed, 1 skipped.
- `scripts/sanitation_audit.py`: 15 módulos con 0 importadores no-test.

## Hallazgos principales

1. Claude Code recibía demasiado contexto al arrancar.
   `.claude/settings.json` hacía `cat WORK_LEDGER.md` en `SessionStart`. El ledger tiene 1092
   líneas y mezclaba historia, decisiones, planes, límites y próximos pasos. En el recovery pass,
   el hook se redujo a una instrucción corta que apunta a `WORK_LEDGER.md` y al mapa canónico sin
   inyectar el ledger completo.

2. El ledger dejó de cumplir su propio contrato.
   `WORK_LEDGER.md` declara higiene de ~40 líneas, pero contiene más de mil. Como autoridad viva,
   ya no es barato ni fiable para orientar sesiones. Debe compactarse: vivo arriba, histórico en
   auditorías/cierres/archive.

3. La autoridad WHY estaba rota.
   `AGENTS.md` y `WORK_LEDGER.md` declaran `MEMORY.md`/`feedback-*.md` como fuente de porqué,
   pero `MEMORY.md` no existía en raíz. El recovery pass creó `MEMORY.md` y
   `feedback-absorb-without-cloning.md`.

4. `.claude/skills/` estaba versionado aunque `.gitignore` lo prohíbe.
   Hay 538 archivos trackeados bajo `.claude`, unos 17 MB, con ~40,994 líneas Markdown. Es un bundle
   local de herramientas, no conocimiento del proyecto. El recovery pass lo sacó del índice con
   `git rm --cached -r .claude/skills` y dejó los archivos locales en disco.

5. La raíz contiene o conserva scratch que no debe ser autoridad.
   `gpt.md` y `.aider.chat.history.md` están ignorados, pero siguen en disco. Pueden contaminar
   agentes que hagan inventarios amplios. Mantenerlos fuera de git no basta si las sesiones los leen
   por heurística.

6. Hay cambios sin cierre.
   `pyproject.toml` está staged con `pyyaml>=6.0.3`; el entorno ya tiene `pyyaml 6.0.3`, pero falta
   decisión explícita. `knowledge-src/preferencias` está untracked y parece una nota de diseño de
   memoria, no una fuente de conocimiento validada.

7. `atlas reality` sobredeclaraba browser readiness.
   Reporta `browser.status=ready` porque detecta Playwright y ejecutables, pero el test real falla:
   falta `chromium_headless_shell-1223`. El recovery pass cambió readiness para comprobar el
   ejecutable Chromium exacto que Playwright va a lanzar o degradar honestamente.

8. Hay vapor de sistema.
   El radar detectó 15 módulos sin importadores no-test, incluyendo `incremental_coder.py`,
   `lesson_runner.py`, `history_compactor.py`, `token_budget.py` y varias piezas de
   `self_maintenance`. Cada uno necesita KEEP+cableado, QUARANTINE o aceptación explícita como
   biblioteca todavía no integrada.

## Premortem

Si seguimos construyendo sin sanear esto, el fallo probable no será un bug único. Será colapso por
contexto: cada sesión leerá demasiada historia, intentará obedecer autoridades contradictorias, verá
capacidades declaradas pero no cableadas, y acabará gastando el presupuesto en reorientarse. El código
core puede seguir verde mientras la operación humana/agente se vuelve lenta e incoherente.

Riesgos concretos:

- Cambios nuevos aterrizan sobre dirty state y se mezclan con bumps autónomos o notas untracked.
- Browser/computer-use se usa como si estuviera listo porque `reality` lo dice, pero los tests fallan.
- El loop autónomo encuentra módulos vapor y los amplía en vez de cablearlos.
- Agentes externos tratan `.claude/skills`, `gpt.md` o historiales como contexto del producto.
- Cada intento de “ordenar” añade otro `.md`, aumentando el problema.

## Plan de recuperación

1. Congelar superficie: no features nuevas hasta cerrar contexto, dirty state y browser readiness.
2. Desversionar `.claude/skills/` sin borrar archivos locales; confirmar `.gitignore`.
3. Compactar `WORK_LEDGER.md` a estado vivo real y mover histórico a cierre/auditoría.
4. Resolver autoridad WHY: crear `MEMORY.md` mínimo o corregir `AGENTS.md` para apuntar a la fuente real.
5. Clasificar `pyproject.toml` staged y `knowledge-src/preferencias`: aceptar con pruebas o sacar del índice.
6. Corregir `atlas reality` browser readiness y/o instalar la revisión Playwright esperada.
7. Triar los 15 módulos vapor: cablear solo los que tienen consumidor inmediato; cuarentena para el resto.

## Estado actual

Recovery pass aplicado: mapa canónico, ledger/AGENTS compactos, memoria WHY mínima,
SessionStart sin inyección de ledger, `.claude/skills` fuera del índice, y browser
readiness corregida en código.

Follow-up aplicado el 2026-07-07: Playwright Chromium/headless shell v1223 instalado
y browser tests verdes; `pyyaml>=6.0.3` aceptado como floor verificado; `knowledge-src/preferencias`
clasificado como policy/design seed y respaldado por rutas `MemoryTrunk` factual/personal;
`scripts/sanitation_audit.py` ahora separa vapor no clasificado de módulos 0-importer
clasificados. Pendiente real: smokes externos vivos solo cuando se carguen secretos/red.
