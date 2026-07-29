"""Qué tests toca un cambio staged — el mapeo que consume `.githooks/pre-commit`.

El gate corre en cada commit, así que no puede ser la suite completa: son ~5:47
de reloj, demasiado para cada commit. El motivo es el TIEMPO, no la RAM. Los
~7,5 GB que cita la cabecera del hook son PRE-ARREGLO: 2262de41 (julio) cacheó
el ONNX de FastEmbedEmbedder por proceso y bajó el pico a ~1,9 GB; el comentario
del hook nunca se actualizó. Medido el 2026-07-29 con /usr/bin/time -v: 2,36 GB
de pico y exit 0 con earlyoom vivo (PID 1184).

El mapeo anterior, `src/<stem>.py -> tests/test_<stem>*.py`, era demasiado
estrecho en dos direcciones y dejó pasar el 2026-07-29 un cambio que rompía los
37 tests del tronco MCP:

* los ficheros de DATOS no mapeaban a nada, y `docs/design/mcp_catalog.yaml` es
  entrada de producción que 10 ficheros de test ejercitan;
* el glob por stem alcanzaba 1 de los 16 ficheros que ejercitan
  `src/atlas/mcp/catalog.py`, porque se llaman `test_mcp_*`, no `test_catalog*`.

Aquí el mapeo es por REFERENCIA: se busca en `tests/` quién nombra el módulo
punteado o el fichero staged. Es autoexplicativo y no hay tabla que mantener a
mano, que se quedaría desfasada igual que el glob.

Sigue siendo un gate rápido, no una prueba de cobertura: un test que cargue el
catálogo a través de un helper sin nombrarlo no se detecta. Es estrictamente
mejor que el glob, no una garantía.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

# Medido el 2026-07-29 sobre este repo: 19 ficheros/210 tests = 18,6 s y 680 MB;
# 59 ficheros/833 tests = 60,5 s y 445 MB; los 371 de golpe = 5:47 y 2,36 GB.
# El tope acota el TIEMPO del gate, que es lo que lo haría insufrible por commit;
# la RAM no es el cuello que decían las notas viejas. 150 ficheros ~ 2-3 min en
# el peor caso, y los cambios reales medidos se quedan muy por debajo.
DEFAULT_MAX_FILES = 150

_TESTS_DIR = "tests"


def _module_path(rel: str) -> str:
    """`src/atlas/mcp/catalog.py` -> `atlas.mcp.catalog`."""
    return rel[len("src/") : -len(".py")].replace("/", ".")


def _test_files(root: Path) -> list[Path]:
    return sorted((root / _TESTS_DIR).glob("test_*.py"))


def _referencing(root: Path, needles: Iterable[str]) -> set[str]:
    """Ficheros de test cuyo texto nombra alguno de los `needles`."""
    wanted = [n for n in needles if n]
    if not wanted:
        return set()
    hits: set[str] = set()
    for path in _test_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in text for n in wanted):
            hits.add(path.relative_to(root).as_posix())
    return hits


def impacted_tests(
    staged: Sequence[str],
    *,
    root: Path,
    max_files: int = DEFAULT_MAX_FILES,
) -> list[str]:
    """Ficheros de test (relativos a `root`) que un cambio staged puede romper.

    Un test staged se devuelve a sí mismo. Un `.py` bajo `src/` arrastra el glob
    por stem —para no perder la cobertura que ya daba el hook viejo— más todo
    test que nombre su módulo punteado. Cualquier otro fichero arrastra todo test
    que lo nombre por ruta o por basename: así los datos de producción dejan de
    ser un punto ciego.

    El resultado va ordenado, deduplicado y recortado a `max_files` para que el
    gate no degenere nunca en la suite completa.
    """
    out: set[str] = set()
    # Se acumulan todas las agujas y se hace UNA pasada por `tests/`: leer los
    # 371 ficheros una vez por cada fichero staged era gratis con un cambio y
    # caro con un commit ancho.
    needles: list[str] = []

    for rel in staged:
        rel = rel.strip()
        if not rel:
            continue

        if rel.startswith(f"{_TESTS_DIR}/") and rel.endswith(".py"):
            if (root / rel).exists():
                out.add(rel)
            continue

        if rel.startswith("src/") and rel.endswith(".py"):
            stem = Path(rel).stem
            for hit in (root / _TESTS_DIR).glob(f"test_{stem}*.py"):
                out.add(hit.relative_to(root).as_posix())
            needles.append(_module_path(rel))
            continue

        # Datos, config, schemas, docs: por ruta completa y por basename, porque
        # los tests unas veces construyen la ruta y otras citan sólo el fichero.
        needles.extend([rel, Path(rel).name])

    out |= _referencing(root, needles)
    return sorted(out)[:max_files]


def main(argv: Sequence[str] | None = None) -> int:
    """Entrada que invoca `.githooks/pre-commit`: rutas staged por argv, un
    fichero de test por línea en stdout. Si el recorte se activa lo avisa por
    stderr, para que el gate no se reporte como cobertura completa."""
    parser = argparse.ArgumentParser(
        prog="atlas.engineering.impacted_tests",
        description="Ficheros de test que puede romper un conjunto de cambios staged.",
    )
    parser.add_argument("paths", nargs="*", help="rutas staged, relativas a la raíz")
    parser.add_argument("--root", default=".", help="raíz del repo (por defecto: cwd)")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    hits = impacted_tests(args.paths, root=root, max_files=args.max_files)

    # Recalcular sin tope sólo para saber si hubo recorte: el coste es leer los
    # mismos ficheros ya cacheados por el SO, y evita mentir sobre la cobertura.
    total = len(impacted_tests(args.paths, root=root, max_files=len(_test_files(root)) or 1))
    if total > len(hits):
        print(
            f"aviso: mapeo truncado a {len(hits)} de {total} ficheros — cambio "
            "transversal; la suite completa corresponde a CI o a "
            "ATLAS_PRECOMMIT_FULL=1",
            file=sys.stderr,
        )

    for rel in hits:
        print(rel)
    return 0


if __name__ == "__main__":  # pragma: no cover - entrada de proceso
    raise SystemExit(main())
