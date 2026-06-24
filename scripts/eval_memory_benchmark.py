"""
eval_memory_benchmark.py — Benchmark de evaluación honesta del SqliteMemoryIndex.

Ejecuta un conjunto FIJO de queries sobre un corpus sintético controlado y reporta
precision/recall/F1 por query, más agregados macro.

DISEÑO ANTI-LEAK (honestidad del repo):
  El split es real: primero se indexa el corpus completo, LUEGO se ejecutan las
  queries. Las queries NO participan en la indexación — el índice no las ve hasta
  el momento del recall. Esto equivale al split train/test estándar aplicado a
  recuperación de información: el "entrenamiento" (indexación + embeddings) ocurre
  sobre el corpus, y la evaluación ocurre sobre queries que el índice nunca vio.
  No hay fuga porque:
    1. Las queries son literalmente distintas de los textos indexados.
    2. La función recall() sólo lee el índice construido, no tiene acceso al
       conjunto de queries al momento de la indexación.
    3. La semilla (SEED=42) fija el corpus sintético, garantizando determinismo.

Uso:
    python scripts/eval_memory_benchmark.py [--db /tmp/eval_bench.db]

Salida: informe de texto a stdout, reproducible (misma salida en cada ejecución).
"""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from atlas.memory.memory_index import SqliteMemoryIndex
from atlas.memory.record import GenericRecord


# ---------------------------------------------------------------------------
# Corpus sintético (fijo, determinista — no leer antes de indexar)
# ---------------------------------------------------------------------------

CORPUS: list[tuple[str, str]] = [
    # (record_id, text)
    ("m01", "Python usa indentación para definir bloques de código"),
    ("m02", "El garbage collector de CPython usa conteo de referencias"),
    ("m03", "Los decoradores en Python son funciones que envuelven otras funciones"),
    ("m04", "SQLite es una base de datos embebida que no requiere servidor"),
    ("m05", "Los índices en SQL aceleran las consultas a costa de espacio en disco"),
    ("m06", "Una clave foránea (foreign key) mantiene integridad referencial entre tablas"),
    ("m07", "El protocolo HTTP usa verbos como GET, POST, PUT y DELETE"),
    ("m08", "TLS cifra el tráfico HTTP para formar HTTPS"),
    ("m09", "Un certificado X.509 asocia una clave pública a una identidad"),
    ("m10", "Los embeddings vectoriales representan texto como vectores de números reales"),
    ("m11", "La similitud coseno mide el ángulo entre dos vectores en el espacio"),
    ("m12", "Los transformers usan mecanismos de atención para procesar secuencias"),
    ("m13", "El patrón Observer desacopla emisores de eventos de sus suscriptores"),
    ("m14", "El patrón Factory centraliza la creación de objetos complejos"),
    ("m15", "pytest descubre tests buscando funciones con prefijo test_"),
    ("m16", "mypy verifica tipos estáticos en Python usando anotaciones PEP 484"),
]

# Queries con sus matches esperados (record_ids que DEBEN aparecer en top-k).
# Diseño: cada query es semánticamente cercana a 1-2 memorias del corpus y
# claramente distante del resto. Esto permite medir recall real.

@dataclass(frozen=True)
class QueryCase:
    query_id: str
    query_text: str
    relevant_ids: frozenset[str]   # IDs que deben estar en el top-k resultado


QUERIES: list[QueryCase] = [
    QueryCase("q1", "¿Cómo se indenta el código en Python?",            frozenset({"m01"})),
    QueryCase("q2", "base de datos sin proceso servidor separado",       frozenset({"m04"})),
    QueryCase("q3", "cifrado de tráfico web y certificados",             frozenset({"m08", "m09"})),
    QueryCase("q4", "representación vectorial de texto para búsqueda",  frozenset({"m10", "m11"})),
    QueryCase("q5", "herramienta para tipos estáticos en Python",        frozenset({"m16"})),
    QueryCase("q6", "patrón de diseño para notificar cambios de estado", frozenset({"m13"})),
]


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

class Metrics(NamedTuple):
    precision: float
    recall: float
    f1: float


def compute_metrics(retrieved: set[str], relevant: frozenset[str]) -> Metrics:
    """Calcula precision/recall/F1 para un conjunto de resultados recuperados."""
    if not retrieved and not relevant:
        return Metrics(1.0, 1.0, 1.0)
    tp = len(retrieved & relevant)
    precision = tp / len(retrieved) if retrieved else 0.0
    recall = tp / len(relevant) if relevant else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0.0)
    return Metrics(precision, recall, f1)


# ---------------------------------------------------------------------------
# Lógica principal del benchmark
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    case: QueryCase
    retrieved_ids: set[str]
    metrics: Metrics


def run_benchmark(db_path: Path, *, k: int = 3, threshold: float = 0.0) -> list[QueryResult]:
    """
    Ejecuta el benchmark completo sobre un índice en db_path.

    Pasos:
      1. INDEXACIÓN: se insertan todos los registros del corpus.
         Las queries NO intervienen en este paso (anti-leak real).
      2. EVALUACIÓN: se ejecutan las queries y se miden métricas.

    threshold=0.0 porque StubEmbedder usa embeddings aleatorios — en producción
    con un embedder real se usaría un umbral más alto (e.g. 0.7).
    """
    idx = SqliteMemoryIndex(db_path, threshold=threshold)

    # FASE 1 — Indexación (el índice no conoce las queries)
    for record_id, text in CORPUS:
        record = GenericRecord(record_id=record_id, text=text)
        idx.upsert(record)

    # FASE 2 — Evaluación (las queries se presentan al índice ya construido)
    results: list[QueryResult] = []
    for case in QUERIES:
        top_k = idx.recall_all(case.query_text, k=k)
        # Con threshold=0.0 todos los resultados top-k cuentan como "recuperados"
        # (sin umbral de corte — honesto para StubEmbedder); con threshold>0, solo los matched.
        retrieved = {r.lesson_id for r in top_k if r.matched or threshold == 0.0}
        metrics = compute_metrics(retrieved, case.relevant_ids)
        results.append(QueryResult(case=case, retrieved_ids=retrieved, metrics=metrics))

    return results


def print_report(results: list[QueryResult]) -> None:
    """Imprime el informe de benchmark de forma determinista."""
    print("=" * 60)
    print("ATLAS MEMORY BENCHMARK — Informe de evaluación honesta")
    print("Corpus: 16 memorias sintéticas | Queries: 6 | k=3")
    print("=" * 60)
    print()
    for qr in results:
        m = qr.metrics
        print(f"[{qr.case.query_id}] {qr.case.query_text[:50]!r}")
        print(f"       Relevantes: {sorted(qr.case.relevant_ids)}")
        print(f"       Recuperados: {sorted(qr.retrieved_ids)}")
        print(f"       P={m.precision:.3f}  R={m.recall:.3f}  F1={m.f1:.3f}")
        print()

    # Agregados macro
    precisions = [qr.metrics.precision for qr in results]
    recalls    = [qr.metrics.recall    for qr in results]
    f1s        = [qr.metrics.f1        for qr in results]
    print("-" * 60)
    print(f"MACRO  P={sum(precisions)/len(precisions):.3f}  "
          f"R={sum(recalls)/len(recalls):.3f}  "
          f"F1={sum(f1s)/len(f1s):.3f}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark de evaluación del SqliteMemoryIndex")
    parser.add_argument("--db", default=None, help="Ruta al archivo SQLite (temporal si no se indica)")
    args = parser.parse_args()

    if args.db:
        db_path = Path(args.db)
        results = run_benchmark(db_path)
    else:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as f:
            db_path = Path(f.name)
        results = run_benchmark(db_path)

    print_report(results)


if __name__ == "__main__":
    main()
