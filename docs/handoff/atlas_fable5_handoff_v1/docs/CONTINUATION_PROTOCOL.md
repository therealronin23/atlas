# Atlas OS — Continuation Protocol for Future AI

## Archivos obligatorios de continuidad

Fable 5 debe crear y mantener:

```text
CONTINUATION_STATE.md
NEXT_AI_INSTRUCTIONS.md
ARCHITECTURE_DECISIONS_INDEX.md
OPEN_QUESTIONS.md
KNOWN_RISKS.md
IMPLEMENTATION_LOG.md
TESTING_STATUS.md
```

## CONTINUATION_STATE.md debe contener

- Fecha.
- Resumen del estado.
- Qué existe y funciona.
- Qué está incompleto.
- Cómo ejecutar backend.
- Cómo ejecutar UI.
- Cómo ejecutar tests.
- Archivos clave.
- Decisiones que no deben revertirse.
- Próximos tickets exactos.
- Dudas que requieren web search.

## Regla para IA menos potente

La IA posterior no debe rediseñar Atlas desde cero.
Debe:

1. Leer `CONTINUATION_STATE.md`.
2. Leer `ARCHITECTURE_DECISIONS_INDEX.md`.
3. Leer ADRs.
4. Ejecutar tests.
5. Tomar el primer ticket pendiente.
6. Hacer cambio pequeño.
7. Actualizar continuidad.

## Prohibición

No aceptar cambios que:

- Pongan chat como home.
- Conviertan Visual Orchestrator en home.
- Metan frameworks externos como kernel.
- Añadan conectores sin permisos/auditoría.
- Rompan Event Canon.
