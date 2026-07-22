<!-- GENERADO por atlas handoff 2026-07-22T19:57:27.068581+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **MAXIMUS Cycle 14 — cierre de sesión: F2.6/taxonomía "hecho bien" diseñados
  (no parcheados) + brief T0.5b paso 3 redactado (2026-07-22 21:56)** — el
  operador cerró explícitamente el "vamos al lío" con una instrucción clara:
  NO otro parche barato en F2.6 ni en la taxonomía ("creo que conviene hacer
  algo que sea válido, funcional, profesional y que sea definitivo, no
  pequeños parches... si quieres hacer algo rápido ahora y dejar apuntado
  para que en una sesión futura se haga de la forma correcta"). Aplicado
  literal en los tres frentes pendientes:
  - **F2.6**: `docs/superpowers/plans/2026-07-17-f26-succession-test-PENDIENTE.md`
    ampliado con el diseño real de lo que falta para que sea definitivo — NO
    otro comando suelto, sino 4 piezas ordenadas: (1) `atlas f26 run` que
    dispare la sesión fría (sustituto validado del `claude -p` bloqueado por
    credencial: subagente Sonnet vía Agent tool, PRIME Cycle 6, 6/6), (2)
    grading estructurado del transcript por ítem (no impresión humana de
    memoria), (3) auto-registro (`record_f26_run()` desde el propio comando,
    no un paso manual separado — ahí es donde se pierde en la práctica), (4)
    notificación accionable (`spawn_task`) SOLO al final, nunca primero. El
    bloqueador de credencial (`claude -p` 401 desde 2026-07-17) sigue abierto
    y no es mío de resolver — requiere `claude setup-token` del operador.
  - **Taxonomía**: `docs/superpowers/specs/2026-07-15-succession-ecosystem-design.md`
    §5 (raíces/tronco/ramas/hojas/savia) marcada **SUPERSEDED formalmente**
    por la taxonomía real de `atlas_ecosystem_map.md` — no se abandona el
    mapa real, se abandona el vocabulario árbol que nunca se implementó.
    Diseño completo de la reconciliación "hecha bien" documentado para
    sesión futura: columna `Tramo` en las 51 filas del mapa real (trabajo de
    clasificación humana, 1-2h, NO automatizable), con paso explícito de
    verificar que produce valor real antes de construir nada sobre ella (si
    no predice nada nuevo, descartar formalmente en vez de mantener a
    medias).
  - **T0.5b paso 3**: brief completo y autocontenido en
    `docs/superpowers/plans/2026-07-22-t05b-paso3-parallel-digestion-BRIEF.md`
    — el diseño del operador (4 proveedores en paralelo + pool de modelos
    dentro de cada uno + auditor cruzado por división, rotación A→C/B→D/C→A/
    D→B para evitar autoevaluación) traducido a plan ejecutable con
    proveedores/modelos REALES de `DEFAULT_PROVIDERS` (no inventados) y
    números reales del corpus (707 docs, 461 `sin_clasificar` tras Cycle 6 =
    división D/Gemini, ventana de contexto grande para el caso ya conocido de
    docs largos diluyendo el coseno). Incluye prompt listo para copiar/pegar
    en la sesión fresca; la síntesis final (gaps+contradicciones+plan v2)
    queda explícitamente marcada como NO delegable — es juicio real de la
    sesión orquestadora, no de las 4 divisiones.
  - `AGENTS.md` revisado (grep por F2.6/ecosystem_map/plugin/A1/A2/A3): NO
    estaba desfasado, sin cambios necesarios.
  - **Próxima acción real:** ninguna — el operador cerró la sesión explícito
    ("no quedaría nada más por cerrar... pasamos ya en la siguiente sesión
    fresca"). La siguiente sesión arranca con el prompt del brief T0.5b, o
    con cualquiera de las 4 piezas de F2.6 si el operador prefiere resolver
    la credencial `claude setup-token` primero.
