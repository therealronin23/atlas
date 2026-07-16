---
title: "Doctrina de construcción de Atlas — Fable 5 (opinión firmada)"
status: propuesto
date: 2026-07-16
authority: "OPINIÓN de modelo, NO autoridad. Si contradice la visión del operador, gana la visión. Discrepar de esto con evidencia es legítimo y deseable."
---

# Cómo construiría yo Atlas al máximo — Fable 5, antes de desaparecer

Pedido por el operador (2026-07-16): "estaría bien que Fable 5 diga cómo
construir Atlas y mejorarlo al máximo; hay que ver discrepancias, manías mal
redactadas, cosas que pueden malinterpretarse". Esto es mi criterio sincero,
no diplomático. Registrado para que el siguiente modelo no tenga que
reconstruirlo ni fingir que lo tiene.

## 1. Lo que Atlas ya tiene BIEN (que nadie lo toque por moda)

- **El sustrato con procedencia** (memoria+Merkle+lecciones+grafo). Es LA
  ventaja: "nadie puede replicar con dinero lo que se fabrica con tiempo
  vivido". Todo lo demás es reemplazable; esto no.
- **La disciplina de honestidad**: reality-checks, receipts, "no declarar vivo
  lo que no lo está". Es rara en proyectos de IA y vale más que cualquier
  feature.
- **La ruta dorada** (aprobación humana registrada ANTES de actuar): el patrón
  correcto de autonomía. Ampliar su vocabulario, jamás relajar su ceremonia.
- **Adopt-real**: ha evitado al menos 3 cascarones (Sentinel, Hermes-shell,
  y el casi-MCP-de-Neo4j). Mantener.

## 2. Dónde discrepo / qué haría distinto (lo que nadie me preguntó)

1. **Hay demasiada doctrina y poca síntesis.** 666 docs y 40+ memorias son un
   PASIVO de sucesión, no un activo. Impondría un presupuesto de autoridad:
   UNA página de leyes (AGENTS.md), UN plan (master plan), UNA doctrina
   (esta), y todo lo demás o es GENERADO desde el sustrato o es histórico.
   Cada doc de autoridad nuevo debe jubilar a otro. El instinto de "escribir
   otro doc" es el enemigo silencioso de este proyecto.
2. **T5.1 (smoke diario de proveedores) debería adelantarse a T1.** Es barato
   (~horas) y sin él la autoconstrucción nocturna muere en silencio la primera
   noche que un proveedor caiga (ya pasó: 3 modelos muertos sin que nadie lo
   supiera). El cuello de Atlas ES proveedores — está medido, no opinado.
3. **La manía de delegación necesita cláusula de cruce.** "Siempre
   Sonnet/Haiku" es correcta en general y falsa en los bordes: hoy mismo, 4
   reanudaciones muertas de un agente costaron más que hacer yo las 2 tareas.
   Regla que propongo: delega si (briefing + riesgo de re-trabajo) < (coste de
   hacerlo tú); re-evalúa SIEMPRE tras 2 fallos consecutivos del delegado.
4. **El tronco es para descubrimiento y gobernanza, no para tráfico.** La
   manía "capability routing estructural" choca con el "no todo tiene que
   pasar por el tronco" del operador. Mi resolución: el tronco descubre,
   cataloga y autoriza; una vez autorizada, la rama habla directo. Un router
   que intermedia cada llamada es un cuello artificial.
5. **La UI vale más de lo que su historial de aparcamientos sugiere.** El
   operador NO programa: cada semana sin Mission Console viva es él pegando
   textos entre 200 IAs — el proceso que más lo quema. Yo haría T2.1-mínima
   EN PARALELO con T1, no después. Ojo, driver futuro: "APARCADA" en las
   memorias fue decisión de secuencia por tokens, NUNCA de valor.
6. **Los chats externos del operador son el mayor yacimiento sin explotar.**
   Valen más que 300 de los 666 docs. T0.5 (intake+digestión) es minería, no
   burocracia.
7. **La sucesión se mide, no se narra.** F2.6 (Sonnet frío 6/6) es EL test.
   Todo pack de handoff sin ese número verde es esperanza, no ingeniería.
8. **El máximo de Atlas no es más features**: es minimizar la latencia del
   bucle intención→misión→receipt→lección con CERO tokens del operador.
   Cada propuesta de construcción debería justificarse contra esa métrica.
   Si no la mueve, es decoración.

## 3. Trampas de malinterpretación detectadas (semilla de la campaña T0.5c)

Casos REALES, no hipotéticos — cada uno necesita corrección en su fuente:

- **Ejemplo-como-alcance** (caso Cursor). Ya es ley en el plan maestro §2.1.
  Corrección pendiente: barrer los docs de intención buscando "p.ej./como/
  tipo X" donde X pueda leerse como el alcance entero.
- **Afirmación punto-en-tiempo sin caducidad**: el ledger describió como
  vivos 3 scripts que Codex retiró horas después (cazado por la revisión
  final HOY). Regla: toda afirmación de estado lleva fecha + "verificar con
  reality"; los docs de estado son proyecciones, no verdades.
- **"APARCADA" leído como "no importa"**: aparcado = secuencia, no valor. El
  doc que aparca debe decir POR QUÉ y CUÁNDO se reabre (ADR-066 lo hace bien;
  las memorias de UI no).
- **"Docs raíz los cura el operador" — alcance ambiguo**: ¿incluye
  docs/design/? Propuesta de redacción: raíz = ficheros en `/` + AGENTS.md +
  README; `docs/design/` es territorio normal con status `propuesto`.
- **Memorias superseded sin marcar**: "el tronco usa 2-3 de 6 primitivos MCP"
  estuvo 8 días obsoleta y casi me hace repetir trabajo hecho. Corrección:
  al descubrir una memoria obsoleta, editarla EN EL MOMENTO (no anotar aparte).
- **scripts/README.md vende Neo4j como vigente** (neo4j-import,
  knowledge-stack) con Neo4j aparcado — un driver nuevo montaría Neo4j.
- **Inventarios negativos en caliente**: "no tenemos hooks, no tenemos loops,
  no tenemos nada" (operador, frustrado, 2026-07-15) era falso literal — los
  hooks estaban activos. Regla para drivers: un inventario negativo emocional
  es señal de dolor, no un hecho técnico; verificar con reality antes de
  actuar sobre él (aquel día la parte real era: el daemon estaba parado).

## 4. Mi orden sincero para "mejorarlo al máximo"

Las próximas 2 semanas (si yo decidiera): **T0 completo** (con F2.6 REAL,
número verde) + **T5.1 adelantado** + **T2.1-mínima** (aprobar misiones desde
la consola). Con esas tres cosas: cualquier modelo mediocre continúa sin mí,
el sistema avisa cuando un proveedor muere, y el operador dirige VIENDO en
vez de pegando textos. Después T1 a pleno (la máquina que hace el resto), y
el resto del plan tal como está.

La semana tipo a la que hay que llegar: el daemon muele de noche con
proveedores propios; el operador revisa lotes por la mañana en la consola en
10 minutos; el modelo caro de turno solo diseña tramos, audita lotes y decide
N2. Si una semana no se parece a eso, algo del plan se está ejecutando mal.

## 5. Contrato de esta doctrina

Firmada: claude-fable-5, 2026-07-16. Se ingiere al sustrato para recall.
Caduca: revisarla en cada cambio de generación de modelo — el siguiente
"Fable" debe escribir la suya, discrepando de esta donde tenga evidencia.
No es autoridad: es el testigo que paso.
