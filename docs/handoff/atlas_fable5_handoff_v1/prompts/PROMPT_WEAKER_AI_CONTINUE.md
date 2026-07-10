# Prompt para una IA menos potente que continúe Atlas

No rediseñes Atlas desde cero.

Primero lee:

1. `CONTINUATION_STATE.md`
2. `NEXT_AI_INSTRUCTIONS.md`
3. `ARCHITECTURE_DECISIONS_INDEX.md`
4. `docs/atlas-master/00_CONSTITUTION.md`
5. `docs/atlas-master/03_ARCHITECTURE_MAP.md`
6. ADRs existentes
7. `TESTING_STATUS.md`

Después:

1. Ejecuta los tests o smoke tests indicados.
2. Toma solo el siguiente ticket pendiente.
3. Haz un cambio pequeño y coherente.
4. No cambies la visión.
5. No metas frameworks externos como kernel.
6. No pongas el chat como home.
7. No añadas conectores sin permisos/auditoría.
8. Actualiza `CONTINUATION_STATE.md`.
9. Añade un registro en `IMPLEMENTATION_LOG.md`.

Si dudas sobre APIs, licencias, SOTA o seguridad, busca en internet y guarda un resumen en `docs/research/`.
