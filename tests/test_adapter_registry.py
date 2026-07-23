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
    """El catálogo real (docs/design/mcp_catalog.yaml) sigue teniendo la
    entrada computer-control-mcp, verificada — si esto cambia, el wiring de
    t3-3 debe revisarse, no servir un adapter obsoleto en silencio."""
    from atlas.mcp.catalog import load_catalog

    entries = load_catalog(CATALOG_PATH)
    entry = next((e for e in entries if e.name == "computer-control-mcp"), None)
    assert entry is not None
    assert entry.status == "verificado"
    assert entry.kind == "mcp"


def test_computer_control_mcp_adapter_validates_via_registry() -> None:
    registry = AdapterRegistry()
    adapter = registry.register(computer_control_mcp_adapter(CATALOG_PATH))
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
