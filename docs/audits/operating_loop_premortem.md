# Premortem + auditoría del OPERATING LOOP (2026-06-21)

Ejercicio: *asumir que dentro de 3 meses el sistema falló igual que antes* (hilo perdido,
skills enterrados, tokens malgastados) y averiguar por qué. Cada fallo → mitigación aplicada.

## Fallos imaginados y su mitigación

| # | Cómo falló | Causa raíz | Mitigación aplicada |
|---|---|---|---|
| 1 | **No corro el pre-flight.** El loop dice "léelo primero" pero depende de mi disciplina — lo mismo que ya falló | La única función forzosa REAL no es un doc, es un **hook** | Declarado honesto en el loop: el doc es best-effort; **enforcement real = SessionStart hook** (recomendado al usuario, no auto-instalado). El ledger deja que el usuario me corrija barato |
| 2 | **El ledger se queda viejo** y miente → peor que nada | Actualizarlo depende de la misma disciplina | Regla: **actualizar `WORK_LEDGER.md` es parte de "done"** y va EN EL MISMO COMMIT que el trabajo (los commits sí ocurren) |
| 3 | **3 fuentes de estado divergen** (ledger ⨯ checklist del design doc ⨯ memoria) — justo lo que queríamos evitar | No definí autoridad por eje | **Autoridad única por eje**: ledger=DÓNDE (estado/próxima), design doc=CÓMO (detalle), memoria=POR QUÉ (lecciones). El estado vive SOLO en el ledger; el design doc no duplica estado |
| 4 | **Matrioska como ceremonia**: forzar Gate→ADR→Fase→Tipo cuando 2 niveles bastan | Estructura rígida = fricción → se abandona | **Profundidad flexible**: usar el nodo MÁS SOMERO que ubique el trabajo. No todo necesita Gate/ADR |
| 5 | **Listo skills pero no los invoco** (listar ≠ usar) | Una lista no es accionable | **Tabla tarea→skill** (no lista suelta) + compromiso: la 1ª tarea de código (2.1) DEBE invocar un skill o sigue enterrado (dogfooding tracked) |
| 6 | **El anti-bloat se vuelve bloat**: loop+ledger+memoria cargan cada sesión | Sin presupuesto | **Presupuesto**: ledger ≤ ~40 líneas; podar nodos cerrados a un archivo; loop terso |
| 7 | **Delegación cuesta más de lo que ahorra**: subagente arranca en frío, re-deriva contexto, deriva | Delegar trabajo ambiguo | Regla: delegar SOLO unidades autocontenidas con criterios de aceptación; lo exploratorio/ambiguo lo hace Opus |
| 8 | **MCP cargo-cult**: lo menciono para contentar, sin uso real | No hay necesidad real de MCP hoy | Honesto en el loop: **ninguna MCP necesaria ahora**; usar una solo si la tarea exige un servicio externo no cubierto por CLI (`gh` cubre git/GitHub) |
| 9 | **No sé cuándo compactar** | Sin disparador | Regla: compactar al CERRAR un nodo si el contexto pesa — seguro porque el estado vive en ledger/checklist/memoria |

## Oro minado de estos días (manías nuevas que faltaban)

Patrones que demostraron valor repetido en la sesión y NO estaban capturados:

- **`verify-the-real-case`**: un test verde solo prueba lo que ejercita; smoke con variación
  natural antes de declarar que un detector funciona; estresar el set de control; el gap/margen
  es la métrica robusta, los absolutos con n pequeño son ruido. (De: FP del drift, guard de dim,
  borderline benigno, contrastive 0%-suerte.)
- **`internal-prior-art-first`**: antes de fiarte de/escribir código nuevo para un problema ya
  resuelto, grep del repo por el patrón existente; un módulo nuevo que lo ignora es sospechoso.
  (De: el guard de dim que `vector_store.py` YA tenía y `memory_index.py` ignoró.)

## Lo que NO se pudo cerrar (honesto)

- **Enforcement duro**: sin un SessionStart hook, el loop sigue dependiendo de mi disciplina.
  Recomendado; pendiente de decisión del usuario. Es el techo real del sistema.
- **Dogfooding de skills**: hasta que una tarea real de código invoque un skill, "skills cableados"
  es promesa, no hecho. Se valida en 2.1.
