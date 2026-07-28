# Diseño — benchmark de compatibilidad FastEmbed

**Estado:** aprobado por el operador para implementación; pendiente de ejecución y validación.
**Fecha:** 2026-07-28
**Programas:** P04 — Memory and Continuity; P09 — Security, Evaluation, Operations and Recovery.

## Problema

La suite local carga FastEmbed 0.8.0 con el modelo multilingüe de Atlas y recibe un aviso: el proveedor usa ahora mean pooling donde antes usaba CLS.

El índice persistente ya incluye versión de implementación y digest del artefacto en la identidad del embedder, por lo que no mezcla vectores incompatibles en silencio. Aun así falta una medición reproducible de recuperación semántica y coste de compatibilidad antes de fijar una versión, registrar un modelo custom o iniciar una reconstrucción.

## Alternativas consideradas

1. **Fijar FastEmbed 0.5.1 ahora.** Conserva el comportamiento histórico, pero cambia una dependencia sin medir calidad, soporte ni impacto de seguridad. Rechazada para este corte.
2. **Registrar inmediatamente un modelo custom con pooling explícito.** Evita el aviso, pero modifica la semántica de embeddings sin demostrar que mejora la recuperación de Atlas. Rechazada para este corte.
3. **Medir primero, sin alterar runtime (recomendada).** Un harness puro evalúa pares/tríadas semánticas españolas, produce evidencia de identidad y ranking, y deja cualquier pin o migración como decisión posterior.

## Alcance autorizado

Crear un harness de validación, no un motor de memoria:

- `src/atlas/memory/embedding_benchmark.py`: tipos inmutables y evaluación pura de similitud/ranking sobre el protocolo de embedder existente.
- `fixtures/fastembed_compatibility_cases.json`: corpus pequeño, español y versionado de consultas, candidatos y expectativas de ranking.
- `scripts/benchmark_fastembed_compatibility.py`: ejecutable local que fuerza `HF_HUB_OFFLINE=1`, carga el corpus, instancia explícitamente `FastEmbedEmbedder` y emite un informe JSON a stdout.
- `tests/test_embedding_benchmark.py`: pruebas unitarias sin FastEmbed y una prueba de integración opcional cuando el extra está presente.

No se modifica `FastEmbedEmbedder`, `default_embedder`, el esquema de memoria, la configuración de gobernanza, la base vectorial ni dependencias.

## Contrato del harness

Cada caso contiene una consulta, dos o más candidatos y uno o más candidatos relevantes esperados. El evaluador genera vectores con un `Embedder` ya existente, rechaza vectores vacíos/no finitos/incompatibles, calcula coseno y ordena candidatos deterministamente.

El informe registra rango del candidato relevante, margen frente al distractor, resultado top-k, `identity`, `fingerprint`, dimensión y versión de formato.

La salida es efímera por stdout. No escribe al índice, SQLite, Kuzu, Merkle ni un registro canónico. Una ejecución puede convertirse en evidencia solo mediante la ruta de gobernanza existente.

## Seguridad y degradación

- Si FastEmbed no está instalado, el script falla explícitamente como dependencia opcional ausente; nunca cae a `StubEmbedder`.
- El benchmark no configura proveedores ni realiza efectos externos. Fuerza `HF_HUB_OFFLINE=1` antes de cargar el modelo; si falta o está corrupto, informa `MODEL_ARTIFACT_UNAVAILABLE` sin añadir una vía de descarga autónoma.
- Una identidad distinta se informa como medición; no reconstruye ni migra índices automáticamente.
- Las pruebas de lógica usan vectores estáticos; CI no depende de red, modelo ni GPU. La comprobación FastEmbed real permanece opt-in.

## Aceptación y rollback

La implementación se acepta cuando un corpus malformado o vectores incompatibles fallan de manera accionable, un embedder estático demuestra ranking/top-k/desempate deterministas, y la ejecución real opcional adjunta identidad y demuestra las expectativas semánticas del corpus.

No debe modificar configuración, dependencias ni almacenamiento, ni producir una afirmación `LIVE_VERIFIED` o autorizar una migración.

El rollback es revertir su commit aislado; no existe estado persistido que deshacer.

## Decisión posterior explícita

El informe solo responde si el comportamiento actual conserva una recuperación mínima útil y qué identidad/modelo produjo esa medición. Elegir pin, modelo custom, rebuild o migración requiere comparar el informe con un baseline guardado y una decisión de dependencia/memoria separada.
