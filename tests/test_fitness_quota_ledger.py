"""t13: el presupuesto del banco es DIARIO, y ahora lleva libro.

Evidencia nueva del 2026-08-11, de correr el banco y no de razonar sobre él.
La tirada `--limit 4 --repeats 2 --presupuesto 40` pasó las dos puertas —el
coste (40 ≤ 40) y la sonda, que no avisó de nada— y murió igual:

    groq_llama_70b: Rate limit reached for model `llama-3.3-70b-versatile`
    openrouter_nemotron: Rate limit exceeded: free-models-per-day

Las dos puertas hacían bien su trabajo y ninguna podía ver el problema:

- `coste_estimado()` sabe lo que VA a costar la tirada. No sabe lo que ya se
  gastó hoy. Dos tiradas de 40 pasan por separado contra una cuota diaria que
  no da para las dos.
- La sonda gasta UNA petición y responde "¿puedo llamar?" cuando la pregunta
  es "¿puedo llamar 40 veces?". Es estructuralmente incapaz de ver un límite
  por número de peticiones. Por eso deja de llamarse `cuota_agotada` y pasa a
  `cadena_no_responde`: el nombre prometía lo que la función no puede dar.

Lo que faltaba era el libro: cuánto lleva gastado el banco HOY.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def mod() -> object:
    spec = importlib.util.spec_from_file_location(
        "fitness_run_t13", REPO / "scripts" / "fitness_run.py"
    )
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["fitness_run_t13"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def test_sin_libro_el_gasto_de_hoy_es_cero(mod, tmp_path: Path) -> None:
    assert mod.gasto_de_hoy(tmp_path, hoy="2026-08-11") == 0


def test_el_gasto_se_acumula_dentro_del_mismo_dia(mod, tmp_path: Path) -> None:
    assert mod.registrar_gasto(tmp_path, 40, hoy="2026-08-11") == 40
    assert mod.registrar_gasto(tmp_path, 20, hoy="2026-08-11") == 60
    assert mod.gasto_de_hoy(tmp_path, hoy="2026-08-11") == 60


def test_el_libro_de_ayer_no_cuenta_hoy(mod, tmp_path: Path) -> None:
    """Las cuotas se renuevan; un libro que no caducara convertiría el banco
    en inejecutable para siempre."""
    mod.registrar_gasto(tmp_path, 40, hoy="2026-08-11")

    assert mod.gasto_de_hoy(tmp_path, hoy="2026-08-12") == 0
    assert mod.registrar_gasto(tmp_path, 5, hoy="2026-08-12") == 5


@pytest.mark.parametrize(
    "contenido",
    ['{"fecha": "2026-08-11", "peticiones": "muchas"}', "{", "[]", "null", ""],
)
def test_un_libro_corrupto_no_bloquea_ni_miente(
    mod, tmp_path: Path, contenido: str
) -> None:
    """Fallar hacia 0 es deliberado: un libro ilegible no puede impedir medir.
    Lo que no puede hacer es inventarse un número."""
    libro = tmp_path / "workspace" / "fitness" / "gasto.json"
    libro.parent.mkdir(parents=True)
    libro.write_text(contenido, encoding="utf-8")

    assert mod.gasto_de_hoy(tmp_path, hoy="2026-08-11") == 0


def test_el_libro_es_json_legible_por_un_humano(mod, tmp_path: Path) -> None:
    """Lo va a leer alguien preguntándose por qué el banco no arranca."""
    mod.registrar_gasto(tmp_path, 40, hoy="2026-08-11")

    datos = json.loads(
        (tmp_path / "workspace" / "fitness" / "gasto.json").read_text(encoding="utf-8")
    )
    assert datos == {"fecha": "2026-08-11", "peticiones": 40}


def test_un_gasto_negativo_no_devuelve_credito(mod, tmp_path: Path) -> None:
    mod.registrar_gasto(tmp_path, 40, hoy="2026-08-11")
    assert mod.registrar_gasto(tmp_path, -100, hoy="2026-08-11") == 40


# ---------------------------------------------------------------------------
# El nombre de la sonda
# ---------------------------------------------------------------------------


def test_la_sonda_se_llama_por_lo_que_comprueba(mod) -> None:
    assert hasattr(mod, "cadena_no_responde")
    assert not hasattr(mod, "cuota_agotada"), (
        "el nombre viejo prometía detectar límites por número de peticiones, "
        "que es justo lo que no puede hacer"
    )


def test_la_sonda_declara_lo_que_NO_puede_detectar(mod) -> None:
    """Un docstring que no diga el límite deja al siguiente confiando en
    ella para lo que no sirve — que es lo que me pasó a mí dos veces."""
    doc = mod.cadena_no_responde.__doc__ or ""
    assert "número de peticiones" in doc
    assert "coste_estimado" in doc
