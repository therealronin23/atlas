<!-- GENERADO por atlas handoff 2026-07-31T14:21:41.187129+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 (F0 del plan nuevo) — 4 decisiones del operador ejecutadas;
  docs raíz reconciliados; credencial root borrada.**
  Plan vivo aprobado: `~/.claude/plans/stateless-prancing-pebble.md`.
  **Credencial**: `VPS_ROOT_PASSWORD` **borrada de `.env`** por orden del
  operador. Verificado antes de tocarla que estaba HUÉRFANA: cero
  referencias en `src/`, `scripts/`, `tests/`, `.githooks/`, y **ningún
  script usa `sshpass`** — el "fallback con sshpass" que anunciaba su
  comentario nunca existió. `VPS_HOST`/`VPS_USER` NO se tocan (los usan de
  verdad 3 scripts, que se autentican por clave SSH). Respaldo previo del
  `.env` en scratchpad. Excepción consciente a la norma de ADR-070 ("el
  `.env` es del operador y no se toca"): instrucción explícita.
  **Docs raíz reconciliados** (aprobados en el plan): `PLAN.md` §"Decisiones
  reservadas" de 10 a 5 abiertas + 4 cerradas nombradas + Android como fuera
  de alcance; 4 filas de §"Deuda" corregidas con lo medido; `STATUS.md`
  §"Pendiente operador"; `ATLAS.md` (el bridge 7341 ya no "queda elevado":
  ADR-080 lo resolvió); `atlas_master_plan.md` §7, parado desde el 16-jul,
  con entrada nueva; `backlog.yaml`: `t3-1`→done y los tres micro-PoC→done
  en su tramo Linux (su criterio "APK Android" es inalcanzable por diseño
  desde que Android salió de alcance, y así queda escrito).
  **Registro**: `dependencies` de ADC-WO-102/103 ya no dicen "explicit
  operator decision" (está tomada); `generated_at`/`base_commit` refrescados
  al HEAD real (leído con `git rev-parse`, tras corregirme a mí mismo por
  haber escrito un hash inventado).
  **F0.5 — hipótesis mía DESCARTADA con medición**: pensaba que el skip de
  gobierno de `test_t3_1_desktop_operator_e2e.py` había quedado muerto tras
  admitir el MCP. No lo está: es un fail-safe correcto que solo dispara si
  el receipt falta o se revoca. Los 4 skips actuales son por infraestructura
  (sin Xvfb). Se deja como está.
  **Estado**: suite 4854 passed · `check_canon.py` PASS (2105) · backlog
  70 done / 6 pending / 6 deferred.
  **Próxima acción**: F0.2 — arreglar el punto ciego de
  `sanitation_audit.py` (regex→AST) ANTES de fiarse de él; luego F1 (cablear
  los 1.315 loc dormidos de `src/atlas/engineering/`).
