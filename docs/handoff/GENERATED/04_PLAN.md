<!-- GENERADO por atlas handoff 2026-07-22T19:57:27.068581+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

---
title: "ATLAS — Plan Maestro de Implantación"
status: propuesto
date: 2026-07-16
authority: "Este doc manda sobre el orden de construcción. Cambiarlo de orden exige Cónclave + operador. AGENTS.md manda sobre el CÓMO operar; este doc sobre el QUÉ y CUÁNDO."
---

# ATLAS — Plan Maestro de Implantación (v1)

## 0. Por qué existe este documento

Diagnóstico del operador (2026-07-16, literal): *"no hay un plan cerrado…
todas las IAs empezaban y luego se iban dispersando… muchas decisiones que van
apareciendo sobre el camino, muchas manías que probablemente hagan que una IA
dude o no tome la decisión correcta… no hay un plan de implantación, un orden,
algo, para que cuando tú no estés o aún estando tú cualquiera pueda construir
Atlas y mejorarlo."*

Este doc es ese plan. No es una lista de ideas (para eso están inbox y
backlog): es **intención + decisiones ya tomadas + orden con porqué**. Una IA
que trabaje en Atlas empieza aquí; si algo no está cubierto, usa la escalera
de decisiones (§3) — nunca improvisa dirección ni pregunta al operador el CÓMO.

## 1. La visión (palabras del operador — NO reinterpretar)

- **Qué es**: "una inteligencia personal persistente que sobrevive a las
  generaciones de modelos". Los modelos son "cerebros de alquiler, amnésicos";
  Atlas es la continuidad (memoria, lecciones, decisiones, herramientas,
  identidad) en hardware propio. "El SOTA no es el competidor: es el
  combustible."
- **Universal**: "no quiero solo un super arnés… quiero que Atlas sirva para
  cualquier cosa, para cualquier persona". Si Codex/Claude hacen algo, Atlas
  también y mejor; cualquier dominio (médico, abogado, ciencia…).
- **Vigilancia = descubrimiento abierto**: "el ecosistema entero no es Hermes,
  Cursor u Odysseus — tal vez es un paper o algo que no conocemos porque no
  sabemos su nombre". No listas fijas de fuentes: serendipia sistematizada.
- **Objetivo operativo**: "que Atlas se construya más rápido a sí mismo…
  el humano suelta intención y revisa lotes; Atlas muele 24/7 con SUS
  proveedores" (no con los tokens de Claude del operador).
- **Elasticidad**: cualquier hardware, se adapta; si delega fuera, privacidad
  siempre. La cripto es mecanismo de confianza, no el producto.

El norte de toda priorización: ¿acerca esto a (a) construirse solo más
rápido, (b) servir a cualquier dominio/persona, (c) vigilar el ecosistema
entero? Si no toca ninguna, no entra en un tramo: va a inbox como candidata.

## 2. Principios anti-dispersión (reglas duras para cualquier IA)

1. **Intención sobre instancia.** Los ejemplos son ejemplos. Caso real que
   motiva la regla: el operador pidió "que Atlas use cualquier programa de
   forma autónoma, p.ej. Cursor" y la IA construyó "usar Cursor". PROHIBIDO.
   Cada ítem define la capacidad GENERAL y su evidencia de generalidad
   (mínimo 2 objetivos distintos sin código específico por objetivo).
2. **Una evidencia observable por ítem.** Nada se declara hecho sin
   test/receipt/demo verificable. "Debería funcionar" no existe.
3. **Adoptar real, no cascarón** (descargar→diseccionar→envolver); jamás
   reimplementar de oídas.
4. **Investigar antes de decidir** en arquitectura: barrer SOTA y comparar,
   con enjambre + Cónclave, no con la opinión de una sesión.
5. **Sustrato antes que docs**: para entender Atlas, grafo + reality + ledger;
   los .md son pasado/futuro.
6. **Detector de dispersión**: si al ejecutar un ítem aparecen >3 decisiones
   no previstas de nivel ≥2 (§3), STOP — el ítem estaba mal definido; se
   vuelve a este doc y se re-corta. No se "sigue tirando".
7. **No re-litigar lo sellado** (§4). La duda ante una manía del operador se
   resuelve leyendo la memoria/feedback correspondiente, no preguntándole otra
   vez ni ignorándola.
8. **Readback obligatorio en peticiones ambiguas** (añadido 2026-07-17; origen:
   caso Cursor + "el modelo hace como que entiende y hace lo que le sale").
   Ante una petición interpretable, el plan de misión declara: "interpreto X;
   alternativas que descarto: Y, Z" — y el operador aprueba la INTERPRETACIÓN
   antes que el diff. Nada ambiguo se ejecuta sin readback aceptado.
9. **Las métricas de eficacia de Atlas son estas, en este orden** (cómo se
   mide lo "inmedible"): (a) tasa de re-trabajo — correcciones/reversiones
   posteriores por malentendido, extraída de git+ledger; (b) tasa de
   aceptación del readback a la primera; (c) hallazgos por auditoría de
   intención (caza de discrepancias dicho-vs-hecho, método probado
   2026-07-16: cazó el ledger mintiendo sobre scripts retirados); (d) test
   de sucesión 6/6; (e) benchmarks estándar donde existan (memoria:
   LongMemEval R@5=0.94 ya medido; código: suite tipo SWE cuando AtlasCoder
   madure). Ceremonia sobre confianza: modelo flojo = vocabulario estrecho
   con barandillas; modelo frontier = vocabulario ancho, MISMA ceremonia.

## 3. Escalera de decisiones (quién decide qué)

- **N0 — Ya decidido**: lo que está en este doc, ADRs aceptados y manías
  registradas. Se ejecuta sin preguntar.
- **N1 — Técnica reversible** (nombres, estructura interna, librería ya
  presente): la decide la IA implementadora y la REGISTRA (1 línea en el
  ledger de campaña). No se pregunta a nadie.
- **N2 — Arquitectura, contrato público, coste real, dependencia nueva**:
  Cónclave (deliberation_council) con recomendación escrita; el operador solo
  veta a posteriori. **Regla de oro**: al operador JAMÁS se le pregunta el
  CÓMO técnico ("no tengo ni puta idea" es una respuesta legítima que este
  plan hace innecesaria) — se le presenta decisión tomada + porqué + cómo
  revertirla.
- **N3 — Solo operador**: dinero/créditos nuevos, credenciales, privacidad,
  docs raíz, alcance de la visión, prioridad entre tramos, todo lo
  irreversible hacia fuera (publicar, desplegar, borrar).

## 4. Decisiones selladas (no re-abrir sin Cónclave + operador)

Kuzu como grafo (Neo4j aparcado) · NotebookLM = capa humana sin API ·
monitor graphify RETIRADO (vía única: quality wrapper foreground) · sustrato
único de memoria con procedencia Merkle (sin silos por herramienta) ·
aprobación humana obligatoria en la ruta dorada (Merkle antes de actuar) ·
TDD + mypy --strict + worktrees efímeros · delegación por coste (criterio en
modelo caro, implementación en barato) · Claude Code es un plus, no una
dependencia · ~~UI = evolución de la Mission Console (no reescritura)~~
**SUPERSEDED por el OPERADOR 2026-07-17** (vio la consola: "genérica,
generada por IA, una web no"): la UX final = **aplicaciones DEDICADAS
multi-plataforma comunicadas entre sí** (plan
docs/superpowers/plans/2026-07-17-t21-mission-console-viva.md; atlas-shell
vuelve a su rol D11 de arnés; doble estándar frontend-design +
frontend-ui-engineering y los 9 mockups JARVIS como referencia SIGUEN
vigentes — los mockups deben depositarse en docs/design/ui/references/) ·
autonomía de updates de dependencias BLOQUEADA hasta
condición medible (N≥10 lotes/M≥6 semanas/cero reversiones).

## 5. El plan por tramos (orden con porqué)

Regla de lectura: cada tramo habilita el siguiente. Dentro de un tramo, los
ítems son paralelizables salvo nota. Cada ítem nace con: intención general,
evidencia observable, y nivel de decisiones esperado. Al bajarse a ejecución,
cada ítem se convierte en entradas de `docs/backlog.yaml` (nivel tarea).

### T0 — Sucesión (EN CURSO — es el prerequisito de todo)
Porqué primero: todos los tramos siguientes los construirán IAs distintas de
Fable; sin T0, cada una re-deriva o malinterpreta.
- T0.1 `atlas handoff` generado desde el sustrato (spec B+C §2, aprobada en
  arquitectura). Evidencia: pack regenerable, gate de frescura.
- T0.2 Migración de la memoria privada del harness al sustrato (spec B+C §3).
  Evidencia: recall con procedencia desde sesión sin acceso al dir privado.
- T0.3 Onboarding ejecutable + test de sucesión F2.6 como gate recurrente
  (spec B+C §4). Evidencia: Sonnet frío 6/6 con ≥1 ciclo fallo→arreglo.
- T0.4 Mapa-árbol del ecosistema con ciclo de vida de piezas + radar de
  deriva (spec B+C §5). Evidencia: pieza sin fila en el mapa → hallazgo.
- T0.5 **Absorción del pasado** (añadido 2026-07-16 tras reto del operador
  "¿has visto todos los documentos?" — respuesta honesta: no, 666 docs):
  - a) Doctrina Fable 5 (`fable5_build_doctrine.md`): el criterio del modelo
    saliente, firmado. HECHA — ingerir al sustrato.
  - b) Digestión total del corpus contra este plan: los 666 docs clasificados
    (alimenta-ítem / candidata / histórico / GAP). Evidencia: % de cobertura +
    lista de gaps + lista de contradicciones; plan v2 con fuentes citadas y
    lista explícita de "revisado y descartado".
  - c) Lint de la capa de autoridad y CORRECCIÓN: discrepancias entre docs,
    manías mal redactadas, trampas ejemplo-como-alcance, afirmaciones
    caducadas (semilla: doctrina §3). Docs del operador → diff propuesto;
    memorias del harness → corrección directa. Evidencia: cada trampa de la
    semilla cerrada o descartada con motivo.
  - d) Intake de chats externos: export → inbox → digestión (b). El operador
    elige cuáles; uno a uno, mayor valor primero.

### T1 — Autoconstrucción a pleno pulmón (ADR-068: F6 es núcleo, no negocio)
Porqué: multiplica todo lo posterior — "que se construya sola más rápido".
- T1.1 Ampliar el vocabulario de la ruta dorada: de append-doc a cambios de
  código acotados (motor ColdUpdate ya lo soporta; falta el vocabulario y las
  guardas). Evidencia: una mejora de código real pedida en lenguaje natural
  recorre plan→worktree→validación→aprobación→receipt.
- T1.2 Primera soul (devil_advocate) sobre el contrato soul_manifest
  existente. Evidencia: una misión rechazada/mejorada por la soul con registro.
- T1.3 Radar→misiones: los hallazgos del radar generan misiones propuestas
  (draft-first, jamás auto-aprobadas). Evidencia: un bucle real detectado
  acaba como misión aparcada o aprobada.
- T1.4 Cola del daemon alimentada desde ESTE plan (backlog.yaml como puente).
  Evidencia: el daemon completa ítems T1 en horario nocturno con receipts.
- T1.5 Coding Territory (ADR-068) — ENMENDADA 2026-07-17 (operador: "aider y
  openhands son la polla, hemos querido absorberlos supuestamente y somos 100
  veces peores"): NO crecer AtlasCoder desde cero (cascarón — violaba nuestra
  propia manía adopt-real). En su lugar: disección adopt-real de Aider
  (Apache-2.0) y OpenHands (MIT) — clon efímero, medir en 3 tareas reales
  contra AtlasCoder, veredicto Cónclave — y ENVOLVER al ganador como motor de
  código de Atlas: proveedores del hub, lecciones del sustrato dentro,
  ceremonia de la ruta dorada alrededor (readback+aprobación+receipt).
  Distinción de ley: dependencia (propietario: Claude Code/Cursor = plus) ≠
  absorción (open source vendorizado = órgano propio). Evidencia: tarea de
  código real completada por el motor absorbido con proveedores de Atlas,
  cero tokens Claude del operador, y medición comparativa registrada.

### T2 — UI/UX viva ("ver a Atlas, no leer un puto .md")
Porqué aquí: con T0+T1 la consola muestra misiones/receipts REALES; y el
operador —que no programa— necesita esta superficie para dirigir sin fricción.
- T2.1 Mission Console fase viva: aprobar/aparcar/inspeccionar misiones en
  vivo (los 9 mockups JARVIS como dirección estética; doble estándar skills).
  Evidencia: el operador aprueba una misión de la ruta dorada desde la UI.
- T2.2 Knowledge view: grafo Kuzu + comunidades semánticas navegables
  (tools graph_communities/semantic_neighbors ya existen). Evidencia: click
  en comunidad → miembros → doc.
- T2.3 Visual Orchestrator (ADR-066, reabre aquí): canvas de flujos sobre los
  Dynamic Workflows existentes. Evidencia: un workflow real editado en canvas
  y ejecutado. (N2: alcance exacto vía Cónclave al llegar.)

### T3 — Capacidad universal de operación (el caso Cursor, GENERALIZADO)
Porqué: es la mitad de "universal" — Atlas debe poder USAR cualquier
herramienta, como Codex/Claude mueven el ratón.
- T3.1 Operador universal de aplicaciones: planner sobre computer-control-mcp
  (Xvfb) + Playwright + ExternalFsBridge, que dado "abre X y haz Y" descompone
  en acciones GUI. Evidencia de generalidad OBLIGATORIA: ≥2 aplicaciones
  distintas (p.ej. un editor Y una app de oficina) sin una línea de código
  específica por app. "Funciona con Cursor" NO cierra este ítem.
- T3.2 Biblioteca de recetas aprendidas: las secuencias que funcionan se
  guardan como lecciones reutilizables con procedencia. Evidencia: segunda
  ejecución de una tarea similar usa la receta y tarda menos.

### T4 — Vigilancia serendípica del ecosistema
Porqué: los sentidos de Atlas — "saber cuál es la corriente e ir más rápidos".
- T4.1 Descubrimiento abierto (NO lista fija): expansión de temas + fuentes
  que se descubren unas a otras (el patrón mempalace: encontrar lo que no
  sabías que existía). Evidencia: un hallazgo útil cuya fuente no estaba en
  ninguna lista inicial.
- T4.2 Pipeline candidata→diseccionada→absorbida industrializado (T0.4 da el
  mapa; esto da el músculo). Primera víctima: cipher (rol aún sin decidir —
  disección adopt-real y veredicto). Evidencia: informe de disección + entrada
  en el mapa con estado.
- T4.3 Digestión→catálogo con señal cruzada (hoy 128 hallazgos → 0 candidatos
  por falta de señal). Evidencia: primer candidato automático real no-falso.

### T5 — Cadena de proveedores robusta (el cuello real de Atlas)
Porqué: sin esto, T1 se para cuando un proveedor muere (ya pasó: 3 modelos
muertos, ollama mal apuntado, NVIDIA con límites).
- T5.1 Smoke diario de cadena — CERRADA 2026-07-17 (bootstrap). El recon
  descubrió que YA existía desde 2026-07-09 (ProviderChainSmoke + tick opt-in
  ATLAS_PROVIDER_SMOKE=1, cadencia 24h, Merkle) — "pendiente desde 2026-07-08"
  era una afirmación caducada (trampa doctrina §3). El gap real era
  visibilidad: cerrado proyectando el último smoke en `atlas reality --json`
  (sección provider_smoke, fail-honesta). Evidencia: el smoke de 2026-07-17
  detectó openrouter_qwen3_coder_free muerto (429 upstream) y reality lo
  aflora sin red. Mini-plan: docs/superpowers/plans/2026-07-17-t51-provider-smoke-surfacing.md.
- T5.2 Fuentes largas de graphify: resolver las 12 pendientes (Groq
  openai-compatible primero; si no, ignore deliberado). Evidencia:
  quality-report con status verde o exclusión documentada.
- T5.3 Presupuestos por proveedor con corte fail-closed (la lección del
  sangrado NVIDIA, generalizada). Evidencia: un tope simulado corta el gasto.

### T6 — Twin real y elasticidad multi-hardware
Porqué al final: ya funcionó una vez (Hermes VPS, mayo), es re-despliegue con
todo lo anterior encima. Reabrir es decisión N3 (dinero + credenciales).
- T6.1 Hermes real re-desplegado con el playbook existente. T6.2 reparto de
  carga laptop↔VPS con privacidad ("si delega fuera, privacidad siempre").

## 6. Cómo se mantiene cerrado (el contrato del plan vivo)

- Las ideas nuevas (los miles de chats del operador) entran SIEMPRE por
  `docs/inbox/` → triage → o alimentan un ítem existente o nacen como
  candidata en el mapa. JAMÁS crean un tramo nuevo por sí solas.
- Reordenar tramos o añadir/matar uno: Cónclave + operador (N3). Todo lo
  demás del plan se ejecuta sin tocar el plan.
- Al cerrar cada tramo: actualizar §7, regenerar handoff (T0.1), y una
  retrospectiva de 5 líneas en el ledger: qué decisiones N2 aparecieron que
  este doc debió prever.
- Este doc se INGIERE al sustrato (como el destilado Foundry) para que
  cualquier driver lo recupere por recall con procedencia.

## 7. Estado y próxima acción (actualizar al cerrar cada tramo)

- 2026-07-16: v1 escrita tras sellar la campaña toasty (F1-F5 + revisión
  final). T0 en curso (spec B+C aprobada en arquitectura; F2 le dio la
  primera generación manual). Próxima acción: revisión del operador de este
  plan + spec B+C → writing-plans de T0.1-T0.2.

