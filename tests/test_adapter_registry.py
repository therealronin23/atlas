"""Contracts-first: schemas/adapter.schema.json es la verdad; AtlasAdapter
(espejo pydantic en atlas.mcp.adapter_registry) debe validar exactamente lo
mismo — igual patrón que tests/test_os_event_schema.py.

t3-3-harness-adapter-contract-registry: el contrato de adapter existía en
disco sin ningún consumidor. Este test demuestra que ahora protege de verdad
(rechaza un adapter incompleto) y que al menos una entrada real del catálogo
MCP (docs/design/mcp_catalog.yaml) se expresa como AtlasAdapter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from atlas.events.schemas import Risk
from atlas.mcp.adapter_registry import (
    AdapterRegistry,
    AtlasAdapter,
    ProviderType,
    computer_control_mcp_adapter,
)

REPO = Path(__file__).resolve().parent.parent
ADAPTER_SCHEMA = json.loads((REPO / "schemas" / "adapter.schema.json").read_text())
CATALOG_PATH = REPO / "docs" / "design" / "mcp_catalog.yaml"


def _complete_adapter(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": "adapter_test_thing",
        "display_name": "Test Thing",
        "provider_type": "mcp",
        "capability_type": "desktop.computer_use",
        "required_permissions": ["desktop.mouse_control"],
        "risk_profile": "medium",
        "sandbox_required": True,
        "supports_streaming": False,
        "supports_diff": False,
        "supports_files": False,
        "supports_rollback": False,
        "emits_events": True,
        "memory_policy": "summaries_only",
        "audit_policy": "full",
        "failure_modes": ["transport_disconnect"],
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------- paridad


def test_model_mirrors_json_schema_required_fields() -> None:
    schema_required = set(ADAPTER_SCHEMA["required"])
    model_required = {
        name for name, f in AtlasAdapter.model_fields.items() if f.is_required()
    }
    assert schema_required == model_required
    assert set(ADAPTER_SCHEMA["properties"]) == set(AtlasAdapter.model_fields)


def test_model_mirrors_json_schema_enums() -> None:
    assert {p.value for p in ProviderType} == set(
        ADAPTER_SCHEMA["properties"]["provider_type"]["enum"]
    )
    assert {r.value for r in Risk} == set(
        ADAPTER_SCHEMA["properties"]["risk_profile"]["enum"]
    )


def test_id_pattern_matches_schema() -> None:
    with pytest.raises(ValidationError):
        AtlasAdapter.model_validate(_complete_adapter(id="not-a-valid-id"))


# ---------------------------------------------------------------- rechazo/aceptación


@pytest.mark.parametrize("missing", ["failure_modes", "risk_profile", "sandbox_required"])
def test_registry_rejects_adapter_missing_required_field(missing: str) -> None:
    incomplete = _complete_adapter()
    del incomplete[missing]
    registry = AdapterRegistry()
    with pytest.raises(ValidationError):
        registry.register(incomplete)
    assert registry.get("adapter_test_thing") is None


def test_registry_accepts_complete_adapter() -> None:
    registry = AdapterRegistry()
    adapter = registry.register(_complete_adapter())
    assert isinstance(adapter, AtlasAdapter)
    assert registry.get("adapter_test_thing") is adapter
    assert [a.id for a in registry.all()] == ["adapter_test_thing"]


def test_registry_rejects_unknown_extra_field() -> None:
    registry = AdapterRegistry()
    with pytest.raises(ValidationError):
        registry.register(_complete_adapter(unexpected_field="nope"))


# ---------------------------------------------------------------- wiring MCP real


def test_computer_control_mcp_adapter_matches_real_catalog_entry() -> None:
    """ADC-WO-124 CERRADA 2026-07-31: el catálogo real
    (docs/design/mcp_catalog.yaml) ya no está en cuarentena -- el artefacto
    exacto tiene un receipt Merkle revocable admitido en $ATLAS_HOME, los 4
    E2E funcionales reales corren y pasan. Este test es la trampa que
    obliga a revisar el wiring de t3-3 si el estado se mueve otra vez, en
    vez de servir un adapter obsoleto en silencio."""
    from atlas.mcp.catalog import load_catalog

    entries = load_catalog(CATALOG_PATH)
    entry = next((e for e in entries if e.name == "computer-control-mcp"), None)
    assert entry is not None
    assert entry.status == "verificado"
    assert entry.kind == "mcp"


def test_computer_control_mcp_adapter_builds_now_that_the_real_catalog_is_admitted() -> None:
    """Contraparte positiva del test anterior: con la entrada real ya
    `verificado`, el adapter que t3-3 construye contra el catálogo REAL
    (no uno sintético) debe funcionar -- es la prueba de que el wiring
    existente ya estaba listo para este momento, no dormido."""
    adapter = computer_control_mcp_adapter(CATALOG_PATH)
    assert adapter.id == "adapter_mcp_computer_control"
    assert adapter.sandbox_required is True


def test_computer_control_mcp_adapter_refuses_while_quarantined(tmp_path: Path) -> None:
    """Invariante permanente, ahora sobre un catálogo SINTÉTICO en cuarentena
    (el real ya no lo está): mientras una entrada esté `blocked-admission`,
    construir el adapter debe fallar ruidosamente. Servirlo sería confiar
    en una integración que Sentinel bloquea pre-spawn."""
    quarantined = tmp_path / "mcp_catalog.yaml"
    quarantined.write_text(
        "sectors:\n"
        "  infraestructura:\n"
        "    label: Infraestructura\n"
        "    entries:\n"
        "      - {name: computer-control-mcp, kind: mcp, subsector: escritorio,"
        " install: \"env DISPLAY=:99 computer-control-mcp\", transport: stdio,"
        " trust: quarantined, purpose: \"GUI contra Xvfb :99\", status: blocked-admission}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="blocked-admission"):
        computer_control_mcp_adapter(quarantined)


def test_computer_control_mcp_adapter_validates_via_registry(tmp_path: Path) -> None:
    """El contrato del adapter sigue siendo válido cuando la entrada SÍ está
    admitida: se prueba contra un catálogo `verificado` explícito, para no
    perder cobertura del contrato mientras el catálogo real está en cuarentena."""
    admitted = tmp_path / "mcp_catalog.yaml"
    admitted.write_text(
        "sectors:\n"
        "  infraestructura:\n"
        "    label: Infraestructura\n"
        "    entries:\n"
        "      - {name: computer-control-mcp, kind: mcp, subsector: escritorio,"
        " install: \"env DISPLAY=:99 computer-control-mcp\", transport: stdio,"
        " trust: vetted, purpose: \"GUI contra Xvfb :99\", status: verificado}\n",
        encoding="utf-8",
    )
    registry = AdapterRegistry()
    adapter = registry.register(computer_control_mcp_adapter(admitted))
    assert adapter.provider_type == ProviderType.MCP
    assert adapter.sandbox_required is True
    assert adapter.risk_profile in {Risk.LOW, Risk.MEDIUM, Risk.HIGH}
    assert adapter.failure_modes
    assert registry.get(adapter.id) is adapter


def test_computer_control_mcp_adapter_raises_if_entry_missing(tmp_path: Path) -> None:
    empty_catalog = tmp_path / "mcp_catalog.yaml"
    empty_catalog.write_text("sectors:\n  vacio:\n    label: Vacio\n    entries: []\n")
    with pytest.raises(LookupError):
        computer_control_mcp_adapter(empty_catalog)
