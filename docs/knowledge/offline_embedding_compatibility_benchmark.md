# Benchmark offline de compatibilidad de embeddings

**Estado:** `VALIDATION_HARNESS` medido localmente; no es una decisión de
runtime, dependencia, modelo, reconstrucción ni migración.

## Propósito

El arnés mide si una identidad concreta de FastEmbed conserva ranking semántico
mínimo sobre un corpus español versionado. Existe porque FastEmbed 0.8.0 emitió
un aviso upstream sobre mean pooling frente a CLS. La medición evita convertir
ese aviso, por sí solo, en un cambio irreversible de memoria.

## Límites constitucionales

- Se fuerza `HF_HUB_OFFLINE=1` antes de construir el embedder: no hay descarga
  ni fallback de red.
- La salida es un único JSON efímero por stdout. El arnés no escribe Merkle,
  SQLite, Kuzu, configuración, vectores ni registros de modelo.
- Un extra ausente, artefacto no disponible, corpus inválido, fallo de vector o
  umbral no satisfecho se clasifica explícitamente; nunca se sustituye el
  embedder por un stub.
- Vectores vacíos, no finitos o que desborden la norma/coseno abortan la
  medición. El runner usa JSON estricto (`allow_nan=False`).
- Un resultado `MEASURED` no equivale a `LIVE_VERIFIED`, ni autoriza pin,
  modelo custom, rebuild o migración.

## Ejecución reproducible

Desde la raíz del repositorio y únicamente con un artefacto FastEmbed ya
presente localmente:

```bash
PYTHONPATH=src HF_HUB_OFFLINE=1 python scripts/benchmark_fastembed_compatibility.py
```

Estados de salida: `MEASURED` (0),
`COMPATIBILITY_THRESHOLD_NOT_MET` (5), `OPTIONAL_DEPENDENCY_MISSING` (2),
`MODEL_ARTIFACT_UNAVAILABLE` (3), `INVALID_BENCHMARK_INPUT` (4) y
`MEASUREMENT_FAILED` (1). `--help` también produce un documento JSON de uso.

El corpus es [fastembed_compatibility_cases.json](../../fixtures/fastembed_compatibility_cases.json).
El evaluador puro es [embedding_benchmark.py](../../src/atlas/memory/embedding_benchmark.py)
y sus pruebas son [test_embedding_benchmark.py](../../tests/test_embedding_benchmark.py).

## Evidencia local registrada — 2026-07-28

La ejecución offline registrada produjo `status=MEASURED`, `passed=true` en
tres casos españoles, con FastEmbed 0.8.0, dimensión 384, fingerprint
`sha256:d2463fb0b4881ae9b8c05f19230bf3c40447db58afab336135727964f5d9882d`
y artefacto SHA-256
`e844933822b84e4feda6da123ecfa5cf42eb5a0f409eb46e8f7b881e181394a9`.

El aviso upstream de pooling permanece como señal a investigar. La muestra es
demasiado pequeña para declarar equivalencia universal de memoria persistente.

## Siguiente decisión requerida

Antes de cualquier cambio de FastEmbed, modelo, dimensión, registro de modelo o
almacenamiento se debe comparar esta identidad con un baseline guardado y abrir
una decisión separada de dependencia/memoria. Esa decisión debe definir
aceptación, rollback y si procede una reconstrucción o migración; este arnés no
puede ejecutarla.

## Trazabilidad

- Diseño: [2026-07-28-fastembed-compatibility-benchmark-design.md](../superpowers/specs/2026-07-28-fastembed-compatibility-benchmark-design.md).
- Plan: [2026-07-28-fastembed-compatibility-benchmark.md](../superpowers/plans/2026-07-28-fastembed-compatibility-benchmark.md).
- Work order: `ADC-WO-115` en
  [implementation_registry.yaml](../canon/implementation_registry.yaml).
- Estado operativo: [WORK_LEDGER.md](../../WORK_LEDGER.md).
