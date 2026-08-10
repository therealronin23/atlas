# ADR-085 — Reducción de Alcance UI (Flutter Mission Console)

- **Estado**: aceptado (2026-08-03)
- **Fecha**: 2026-08-03
- **Contexto previo**: ADR-071 (aplicaciones dedicadas Linux desktop + Android superseden la UX web-first), ADR-082 (Selección de Flutter como stack nativo).

## Contexto y Problema

Con la selección de Flutter (ADR-082) como el framework principal para construir la aplicación nativa en `prototypes/atlas_ui/`, las iteraciones previas de la interfaz gráfica web (Tauri, React, y los experimentos en `ui/atlas-shell/`) han quedado obsoletas y suponen una carga cognitiva y de mantenimiento (código dormido detectado por radares AST).

Para consolidar el esfuerzo, es necesario formalizar una reducción drástica del alcance de la UI (Fase F3.1) que converja todo el desarrollo visual en el entorno de Flutter.

## Decisión

Se **reduce oficialmente el alcance del desarrollo de UI** exclusivamente a la Mission Console construida en Flutter. 

1. **Abandono de alternativas Web**: Se archivan y descartan todos los esfuerzos previos relacionados con aplicaciones web híbridas, Tauri o React. El directorio `ui/atlas-shell/` y similares se consideran código muerto/archivado y no forman parte del plan de mantenimiento.
2. **Convergencia**: Las tareas de las fases T2.1, T2.2 (navegación del grafo semántico de Kùzu) y T2.3 (Visual Orchestrator) deberán realizarse en Flutter.
3. **Mantenibilidad Inteligente**: El esfuerzo de UI se apoyará en herramientas agentic adaptadas a Flutter (como la skill `flutter-build-responsive-layout`) para maximizar la mantenibilidad de la base de código.

## Consecuencias y Próximos Pasos

- **Reducción de Backlog**: Se actualiza `docs/backlog.yaml` para reflejar la consolidación bajo T2.1.
- **Saneamiento**: Todo archivo remanente de prototipos UI pasados debe ser ignorado por los analizadores estáticos o eliminado.
- **Foco de Desarrollo**: Los esfuerzos futuros de visualización operarán exclusivamente a través del puerto 7341 y la aplicación nativa Dart/Flutter.
