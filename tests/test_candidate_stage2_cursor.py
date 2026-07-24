"""Tests de `atlas.mcp.candidate_stage2_cursor` (B.2, ADR-076) --
clasificación de estado + selección de lote + merge, para que el tick de
vetting continuo (B.3) nunca reprocese lo ya completado ni lo terminal, y
retome lo transitorio.

Categorías reales medidas contra `docs/design/mcp_catalog_stage2_report.jsonl`
(2100 filas, 904 completados, corrida 2026-07-24): 908 HTTP 401/403/404/405,
154 DNS muerto, registryType no soportado (oci/mcpb/...), paquete/versión
inexistente, entry point ambiguo/sin declarar -> terminal; 5xx, HTTP 0
(timeout/conexión, ver http_mcp_transport.py), redirect 307/308 no seguido,
crash no anticipado -> retryable. Cualquier razón NO catalogada cae a
retryable por defecto (fail-closed hacia "sigue intentando").
"""

from __future__ import annotations

from atlas.mcp.candidate_stage2_cursor import (
    classify_stage2_status,
    merge_stage2_report,
    select_stage2_batch,
)

# ---------------------------------------------------------------------------
# classify_stage2_status
# ---------------------------------------------------------------------------


def test_completed_is_never_reprocessed_regardless_of_severity() -> None:
    row = {"track": "stdio", "name": "x", "completed": True, "reason": "ok", "worst_severity": "MAJOR"}
    assert classify_stage2_status(row) == "completed"


def test_http_401_403_404_405_are_terminal() -> None:
    for code in ("401", "403", "404", "405"):
        row = {"track": "http", "name": "x", "completed": False, "reason": f"HTTP {code} del endpoint remoto"}
        assert classify_stage2_status(row) == "terminal", code


def test_dns_dead_is_terminal() -> None:
    row = {
        "track": "http", "name": "x", "completed": False,
        "reason": "egress bloqueado por allowlist: Resolución DNS fallida para foo.example",
    }
    assert classify_stage2_status(row) == "terminal"


def test_registry_type_unsupported_is_terminal_for_any_type() -> None:
    """Prefijo genérico, no enumeración literal -- un registryType nuevo
    todavía no visto (ej. 'nuget') es igual de terminal: no cambia sin una
    acción externa (soporte de código nuevo), la reseed no lo arregla."""
    for kind in ("oci", "mcpb", "nuget", "cualquier-cosa-futura"):
        row = {"track": "stdio", "name": "x", "completed": False, "reason": f"registryType no soportado: '{kind}'"}
        assert classify_stage2_status(row) == "terminal", kind


def test_package_or_version_nonexistent_is_terminal() -> None:
    row_a = {"track": "stdio", "name": "x", "completed": False, "reason": "paquete/versión no encontrado en PyPI: foo==0.2.1"}
    row_b = {"track": "stdio", "name": "x", "completed": False, "reason": "versión '0.1.0' no publicada (disponibles: ['1.0.0'])"}
    assert classify_stage2_status(row_a) == "terminal"
    assert classify_stage2_status(row_b) == "terminal"


def test_ambiguous_or_missing_entrypoint_is_terminal() -> None:
    row_a = {"track": "stdio", "name": "x", "completed": False, "reason": "ambiguo: 2 binarios declarados (['a', 'b']), ninguno obvio"}
    row_b = {"track": "stdio", "name": "x", "completed": False, "reason": "sin 'bin' declarado en package.json"}
    row_c = {"track": "stdio", "name": "x", "completed": False, "reason": "sin [project.scripts] declarados"}
    assert classify_stage2_status(row_a) == "terminal"
    assert classify_stage2_status(row_b) == "terminal"
    assert classify_stage2_status(row_c) == "terminal"


def test_http_5xx_is_retryable() -> None:
    for code in ("500", "502", "503", "530"):
        row = {"track": "http", "name": "x", "completed": False, "reason": f"HTTP {code} del endpoint remoto"}
        assert classify_stage2_status(row) == "retryable", code


def test_http_0_connection_failure_is_retryable() -> None:
    """HTTP 0 = fallo de conexión (rechazada/DNS/timeout a nivel transporte,
    ver http_mcp_transport.py::urllib_fetcher_with_headers) -- transitorio,
    no un rechazo deliberado del servidor."""
    row = {"track": "http", "name": "x", "completed": False, "reason": "HTTP 0 del endpoint remoto"}
    assert classify_stage2_status(row) == "retryable"


def test_redirect_not_followed_is_retryable() -> None:
    for code in ("307", "308"):
        row = {"track": "http", "name": "x", "completed": False, "reason": f"HTTP {code} del endpoint remoto"}
        assert classify_stage2_status(row) == "retryable", code


def test_unanticipated_crash_is_retryable() -> None:
    row = {"track": "stdio", "name": "x", "completed": False, "reason": "crash: The read operation timed out"}
    assert classify_stage2_status(row) == "retryable"


def test_uncatalogued_reason_defaults_to_retryable_fail_closed() -> None:
    """Razones reales del reporte de hoy que NO caen en ninguna categoría
    terminal nombrada (ej. HTTP 429/410/421, respuesta no-JSON, JSON-RPC
    server error) -- fail-closed hacia 'sigue intentando', nunca hacia
    'descarta en silencio'."""
    for reason in (
        "HTTP 429 del endpoint remoto",
        "HTTP 410 del endpoint remoto",
        "respuesta no-JSON: <!DOCTYPE html>...",
        "server error -32001: Authentication failed: token_missing",
        "respuesta vacía del endpoint remoto",
    ):
        row = {"track": "http", "name": "x", "completed": False, "reason": reason}
        assert classify_stage2_status(row) == "retryable", reason


# ---------------------------------------------------------------------------
# select_stage2_batch
# ---------------------------------------------------------------------------


def _triaged(names_stdio: list[str], names_http: list[str]) -> list[dict]:
    out = [{"name": n, "track": "stdio", "eligible": True} for n in names_stdio]
    out += [{"name": n, "track": "http", "eligible": True} for n in names_http]
    return out


def test_batch_never_reprocesses_terminal_or_completed() -> None:
    triaged = _triaged(["a", "b", "c"], [])
    prior = {
        "a": {"track": "stdio", "name": "a", "completed": True, "reason": "ok"},
        "b": {"track": "stdio", "name": "b", "completed": False, "reason": "ambiguo: x"},
    }
    stdio, http = select_stage2_batch(triaged, prior, limit_stdio=10, limit_http=10)
    assert "a" not in stdio  # completed
    assert "b" not in stdio  # terminal
    assert "c" in stdio      # nuevo, nunca visto


def test_batch_reprocesses_retryable() -> None:
    triaged = _triaged(["a"], [])
    prior = {"a": {"track": "stdio", "name": "a", "completed": False, "reason": "crash: timeout"}}
    stdio, _ = select_stage2_batch(triaged, prior, limit_stdio=10, limit_http=10)
    assert stdio == ["a"]


def test_batch_respects_independent_limits_per_track() -> None:
    triaged = _triaged(["s1", "s2", "s3"], ["h1", "h2", "h3"])
    stdio, http = select_stage2_batch(triaged, {}, limit_stdio=1, limit_http=2)
    assert len(stdio) == 1
    assert len(http) == 2


def test_batch_prioritizes_new_over_retries() -> None:
    triaged = _triaged(["retry_me", "brand_new"], [])
    prior = {"retry_me": {"track": "stdio", "name": "retry_me", "completed": False, "reason": "crash: x"}}
    stdio, _ = select_stage2_batch(triaged, prior, limit_stdio=1, limit_http=1)
    assert stdio == ["brand_new"]  # el nuevo entra antes que el reintento, y el límite=1 lo deja fuera


def test_batch_ignores_ineligible_entries() -> None:
    triaged = [{"name": "blocked", "track": "stdio", "eligible": False}]
    stdio, _ = select_stage2_batch(triaged, {}, limit_stdio=10, limit_http=10)
    assert stdio == []


# ---------------------------------------------------------------------------
# merge_stage2_report
# ---------------------------------------------------------------------------


def test_merge_new_rows_override_prior_by_name() -> None:
    prior = {"a": {"name": "a", "completed": False, "reason": "crash: x"}}
    new_rows = [{"name": "a", "completed": True, "reason": "ok"}]
    merged = merge_stage2_report(prior, new_rows)
    assert merged["a"]["completed"] is True


def test_merge_preserves_untouched_prior_rows() -> None:
    prior = {
        "a": {"name": "a", "completed": True, "reason": "ok"},
        "b": {"name": "b", "completed": False, "reason": "ambiguo: x"},
    }
    new_rows = [{"name": "a", "completed": True, "reason": "ok"}]  # solo "a" se reprocesó
    merged = merge_stage2_report(prior, new_rows)
    assert merged["b"] == prior["b"]  # intacto, byte a byte
