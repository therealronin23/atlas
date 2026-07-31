<!-- GENERADO por atlas handoff 2026-07-31T01:59:30.937157+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-31 — ADC-WO-102 y ADC-WO-103 cerrados: los dos falsifiers
  pendientes del EDR se ejecutaron por primera vez, ninguno falsificó su
  claim.** Orden del operador: "los dos, ahora" (no diferir).
  **ADC-WO-102** (`EDR-ADR-069-durable-work.md`, commit `795e00c`):
  `tests/test_task_persistence_recovery.py`, 3 tests permanentes que cruzan
  un límite de PROCESO REAL (subprocess con intérprete nuevo, cero memoria
  compartida) — no "no lanzó excepción": task persistida `EXECUTING` por un
  proceso, reconstruida campo a campo por otro completamente distinto (PID
  verificado distinto), más el receipt Merkle verificado en su propia
  cadena (2 persist() reales → 2 receipts, no 1 reusado) y el caso honesto
  de id desconocido → `None`, no un resultado fabricado. Confianza
  medium→medium-high; explícito lo que NO responde (throughput concurrente,
  upgrade de SQLite, recuperación de Mission vs Task).
  **ADC-WO-103** (`EDR-ADR-057-memory-promotion.md`, commit `bc716f8`):
  LongMemEval_S a escala completa por primera vez, n=500/k=5/los 6 modos
  (1284.9s). Overall Recall@5: 0.9300 cosine/temporal/temporal_aof, 0.9340
  hybrid/hybrid_multihop — sostiene el baseline smoke n=50 (0.9400) sin
  colapsar; `single-session-user` es la categoría más débil en todos los
  modos (0.7857-0.8000). **Hallazgo honesto sin maquillar**: `multihop`
  puro da 0.0040 overall (casi cero). Investigado, no es un bug de
  `recall_multihop`: encadena cada hop sobre el TEXTO DEL RESULTADO
  anterior (no la pregunta original) y devuelve como mucho `hops=2`
  candidatos pase lo que pase con `k` — diseño para explorar cadenas
  asociativas de memoria, no para "mejor respuesta a ESTA pregunta" (la
  forma de tarea de LongMemEval); `hybrid_multihop` iguala a `hybrid` liso,
  confirmando que el componente multihop no aporta señal en ESTE benchmark
  — su uso previsto (cadenas de lecciones) sigue sin medir. Confianza
  medium→medium-high; brecha de alcance dejada explícita: el falsifier del
  EDR habla de una "promotion policy" que aún no existe para comparar en
  A/B, esta corrida mide la base de calidad de recuperación que ese
  falsifier futuro necesitaría, no el falsifier en sí.
  **De las 6 decisiones REQUIRES_OPERATOR, quedan sin dossier de evidencia
  ejecutado**: ADC-WO-100 y ADC-WO-105 (irreducible, juicio legal/negocio
  del operador, sin dossier posible). ADC-WO-107 y ADC-WO-124 ya tienen
  dossier con evidencia medida (ver entrada anterior) pendientes de
  decisión del operador, no de más trabajo mío.
