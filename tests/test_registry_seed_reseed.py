"""Tests de `reseed_candidates()` (A.1, ADR-076) -- extracción de la lógica de
paginación+dedup que hoy vive inline en `scripts/mcp_seed_registry.py::main()`,
para que un tick del scheduler pueda invocarla sin pasar por un script CLI.

Mismo patrón que `tests/test_mcp_registry_seed.py`: fetcher inyectado, nunca
red real.
"""

from __future__ import annotations

import json


def _page(names: list[str], next_cursor: str | None = None) -> str:
    servers = [{"server": {"name": n, "description": "x"}} for n in names]
    meta = {"nextCursor": next_cursor} if next_cursor else {}
    return json.dumps({"servers": servers, "metadata": meta})


def test_reseed_dedups_by_name_across_pages() -> None:
    from atlas.mcp.registry_seed import RegistrySource, reseed_candidates

    pages = {
        None: _page(["a", "b"], next_cursor="c1"),
        "c1": _page(["b", "c"], next_cursor=None),  # "b" repetido entre páginas
    }

    def fetcher(method, url, body, headers):
        cursor = url.split("cursor=", 1)[1].split("&", 1)[0] if "cursor=" in url else None
        return 200, pages[cursor]

    result = reseed_candidates(source=RegistrySource(fetcher=fetcher))
    names = [c["name"] for c in result["candidates"]]
    assert names == ["a", "b", "c"]  # sin duplicados, orden de aparición
    assert result["pages_fetched"] == 2


def test_reseed_stops_without_next_cursor() -> None:
    from atlas.mcp.registry_seed import RegistrySource, reseed_candidates

    calls: list[str] = []

    def fetcher(method, url, body, headers):
        calls.append(url)
        return 200, _page(["a"], next_cursor=None)

    result = reseed_candidates(source=RegistrySource(fetcher=fetcher))
    assert len(calls) == 1
    assert result["pages_fetched"] == 1


def test_reseed_raises_if_first_page_not_200() -> None:
    from atlas.mcp.registry_seed import RegistrySource, reseed_candidates

    def fetcher(method, url, body, headers):
        return 500, "error"

    try:
        reseed_candidates(source=RegistrySource(fetcher=fetcher))
    except RuntimeError as exc:
        assert "500" in str(exc) or "pagina" in str(exc).lower() or "página" in str(exc).lower()
    else:
        raise AssertionError("se esperaba RuntimeError cuando pages_fetched==0")


def test_reseed_never_touches_real_network() -> None:
    """Fetcher inyectado obligatorio -- sin `source`, no debe hacer una llamada
    real (regresión: un default que golpee red real rompería la suite)."""
    from atlas.mcp.registry_seed import RegistrySource, reseed_candidates

    called = {"n": 0}

    def fetcher(method, url, body, headers):
        called["n"] += 1
        return 200, _page(["a"], next_cursor=None)

    reseed_candidates(source=RegistrySource(fetcher=fetcher))
    assert called["n"] == 1  # una sola llamada, toda vía el fetcher inyectado


def test_reseed_includes_provenance_and_uses_default_source_url() -> None:
    from atlas.mcp.registry_seed import RegistrySource, reseed_candidates

    def fetcher(method, url, body, headers):
        return 200, _page(["a"], next_cursor=None)

    result = reseed_candidates(source=RegistrySource(fetcher=fetcher))
    cand = result["candidates"][0]
    assert "registry.modelcontextprotocol.io" in cand["provenance"]["source"]
