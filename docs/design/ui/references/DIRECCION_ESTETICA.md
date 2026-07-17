---
title: "Dirección estética de la UX de Atlas — destilada de los 9 mockups del operador"
status: vigente
date: 2026-07-17
---

# La dirección, destilada (para drivers e implementadores que no rendericen imágenes)

Fuente: los 9 mockups del operador (`mockup-01..09` en este directorio),
depositados el 2026-07-17 — la primera vez que la referencia estética del
proyecto existe DENTRO del sustrato. Análisis del driver que los vio
renderizados; los mockups mandan sobre este texto si contradicen algo.

**Caveat del operador, literal**: *"mi idea de atlas ui es algo así, pero
falta pulir muchísimo el ux"*. Los mockups dan CARÁCTER, no spec: son
concept-art generado por IA (contienen pseudo-texto ilegible tipo
"Dashcourd"/"Contextual Inspecer") — copiar layouts al píxel sería copiar
también sus errores. Lo que se copia es el lenguaje.

## El lenguaje visual (lo que hace que se sientan "Atlas")

1. **Negro profundo como lienzo, no gris-app.** Superficies casi negras con
   capas de elevación en gris-carbón; algunas pantallas flotan sobre un fondo
   real desenfocado (sensación de overlay/HUD sobre el mundo).
2. **Un solo acento: cian/teal luminoso.** Se usa como ENERGÍA (glow en
   nodos activos, chips de estado, flujos), no como decoración. Verde para
   "aprobado/sano", ámbar/rojo solo en riesgo. Todo lo demás es monocromo.
3. **Paneles redondeados que flotan.** Geometría de tarjetas con radio
   generoso, borde sutil luminoso, profundidad por capas (glass/elevación) —
   composición de instrumentos, no una página con secciones.
4. **El grafo es protagonista, no ilustración.** Visualizaciones de nodos y
   flujos en el centro de la experiencia: pipeline Intent→Planning→Execution
   →Artifact, memoria como grafo navegable, fan-out neuronal con glow para
   actividad viva. El movimiento de esos flujos ES la sensación de "Atlas
   está vivo".
5. **Densidad de instrumento con respiro.** Muchos datos (listas de
   propuestas, chips de estado, dots de riesgo, progreso) pero con jerarquía
   clara y aire — cabina de precisión, no dashboard saturado.
6. **Tipografía técnica limpia**, mono para código (el "Contextual
   Inspector" muestra diffs/código con sintaxis coloreada).

## Los componentes que los mockups piden (mapa directo a lo que Atlas YA tiene)

| En los mockups | En el núcleo real |
| --- | --- |
| Tarjetas "Proposal" con chips Draft/Pending Review, dots de riesgo y botones **Approve / Park** | La ruta dorada: misiones draft-first + aprobación registrada (receipt Merkle) |
| "Live Execution Pipeline" Intent→Planning→Execution→Artifact con estados | El bus de eventos + receipts del daemon (API 7341, WS ya existente) |
| "Memory Vault" como grafo de nodos + listas con procedencia | Sustrato Kuzu + memoria con Merkle (`graph_*`, recall) |
| Sidebar: Dashboard · Self-Build · Coding Workbench · Research · Memory Graph · Audit | Los dominios reales: self_build tick, AtlasCoder/T1.5, research tick, grafo, audit Merkle |
| "Contextual Inspector" con código/diff al lado de la propuesta | El diff real de cada ColdUpdate/propuesta |
| "Blast Radius Assessment" en tarjetas de propuesta | `graph_blast_radius` — la tool YA existe |

Lectura importante: los mockups NO piden features nuevas — piden VER lo que
ya existe. La distancia no es de backend, es de carácter visual y motion.

## Reglas duras al implementar (anti-genérico)

- Si un panel no tiene datos reales, dice "sin datos" con dignidad — JAMÁS
  placeholder que finja vida (disciplina de honestidad, en píxeles).
- Nada de librería-de-componentes-por-defecto reconocible (el look Material/
  shadcn de serie es exactamente el "generada por IA" que el operador
  rechazó). Los componentes se dibujan para ESTE lenguaje.
- El glow y el motion son moneda escasa: acentúan actividad REAL (un tick
  corriendo, una misión cambiando de estado), no ambiente permanente.
- Pantalla completa, sin chrome de navegador: apps DEDICADAS (plan T2.1
  reformulado; una web no — orden del operador).

## Corrección del operador (2026-07-17, en vivo sobre la PoC v2) — MANDA sobre lo anterior

1. **NO es "un solo acento cian": es una GRAMÁTICA de color semántica** (definida
   por el operador en el chat fundacional, líneas ~860-908 del export):
   azul=interacción · cian=IA pensando · verde=verificado · ámbar=pendiente ·
   rojo=error · morado=memoria/IA externa · gris=sistema · naranja(calor)=riesgo/
   conflicto/fricción. "Que cada color tenga un significado. No solo decoración."
2. **Surface Lifecycle Model** (export ~53904-54120): Atlas no expone pantallas;
   tiene superficies perennes (consola/composer/inspector), EFÍMERAS (gate cards,
   avisos que aparecen, se resuelven y DESAPARECEN), contextuales (Research/
   Coding/Gate/RAG se abren cuando la tarea entra ahí), sectoriales (lentes),
   diagnósticas y procesos invisibles-pero-observables ("oculto por defecto,
   observable por impacto, auditable siempre"). La UX excepcional ES este modelo.
3. **Cuadrícula de espaciado 8px** (8/16/24/32/48); las tarjetas no van pegadas.
