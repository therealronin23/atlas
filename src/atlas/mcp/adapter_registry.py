"""AtlasAdapter — validador puro del contrato schemas/adapter.schema.json.

Igual patrón que atlas/fabric/models.py y atlas/events/schemas.py: la
autoridad es el JSON Schema versionado; este modelo pydantic valida en
runtime sin añadir la dependencia `jsonschema` (invariante 6, pydantic ya
está en pyproject). Si cambias un campo en schemas/adapter.schema.json,
cambia este módulo en el mismo commit — tests/test_adapter_registry.py
cruza ambos.

Contexto (t3-3-harness-adapter-contract-registry): docs/architecture/
CAPABILITY_FABRIC.md y el atlas-bible del handoff pack dicen que "una
integración sin contrato no entra en Atlas". El schema llevaba tiempo en el
repo sin ningún consumidor — este módulo es el primero. El catálogo MCP real
(docs/design/mcp_catalog.yaml, vía atlas.mcp.catalog) usa un formato ad-hoc
propio (trust/status/read_only_tools) que NO declara risk_profile/
sandbox_required/failure_modes; por eso no hay traductor genérico
catalog→adapter todavía (no hay de dónde inventar esos campos para el resto
de entradas). `computer_control_mcp_adapter()` es la traducción manual y
auditada de UNA entrada real, ancla al YAML real para no servir un adapter
obsoleto en silencio si la entrada cambia. Migrar el resto del catálogo
queda como deuda (ver docs/backlog.yaml, t3-3).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atlas.events.schemas import Risk

__all__ = [
    "AdapterRegistry",
    "AtlasAdapter",
    "ProviderType",
    "computer_control_mcp_adapter",
]


class ProviderType(str, Enum):
    LOCAL_CLI = "local_cli"
    LOCAL_SERVICE = "local_service"
    REMOTE_API = "remote_api"
    MCP = "mcp"
    IMPORTER = "importer"
    INTERNAL = "internal"


class AtlasAdapter(BaseModel):
    """schemas/adapter.schema.json — contrato de integración Atlas.

    required_permissions/failure_modes vacíos son válidos para el JSON
    Schema (solo exige el tipo array de string); risk_profile,
    sandbox_required y failure_modes deben estar presentes (sin default) —
    eso es lo que hace que un adapter incompleto sea rechazado.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^adapter_[A-Za-z0-9_-]+$")
    display_name: str
    provider_type: ProviderType
    capability_type: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    required_permissions: list[str]
    risk_profile: Risk
    sandbox_required: bool
    supports_streaming: bool
    supports_diff: bool
    supports_files: bool
    supports_rollback: bool
    emits_events: bool
    memory_policy: str
    audit_policy: str
    failure_modes: list[str]


class AdapterRegistry:
    """Registro en memoria de adapters validados contra el contrato.

    `register()` es el único punto de entrada: acepta dict o AtlasAdapter ya
    construido, valida contra el schema (vía pydantic) y solo entonces lo
    guarda. Un adapter que falla la validación nunca llega a `_adapters` —
    "una integración sin contrato no entra en Atlas".
    """

    def __init__(self) -> None:
        self._adapters: dict[str, AtlasAdapter] = {}

    def register(self, adapter: AtlasAdapter | dict[str, Any]) -> AtlasAdapter:
        model = (
            adapter
            if isinstance(adapter, AtlasAdapter)
            else AtlasAdapter.model_validate(adapter)
        )
        self._adapters[model.id] = model
        return model

    def get(self, adapter_id: str) -> AtlasAdapter | None:
        return self._adapters.get(adapter_id)

    def all(self) -> list[AtlasAdapter]:
        return list(self._adapters.values())


def computer_control_mcp_adapter(catalog_path: Path) -> AtlasAdapter:
    """Traduce la entrada real `computer-control-mcp` de
    docs/design/mcp_catalog.yaml al contrato AtlasAdapter.

    Ancla al catálogo real (en vez de servir un dict hardcodeado suelto): si
    la entrada desaparece o deja de estar `verificado`, falla ruidosamente
    en vez de dar por buena una integración que ya no es la que se auditó.
    risk_profile/sandbox_required/required_permissions/failure_modes no
    existen en el formato del catálogo — son conocimiento de dominio
    (Xvfb :99 virtual, nunca el display real; mouse/teclado/OCR) que este
    wiring añade a mano, precisamente el hueco que t3-3 cierra.
    """
    from atlas.mcp.catalog import load_catalog

    entries = load_catalog(Path(catalog_path))
    entry = next((e for e in entries if e.name == "computer-control-mcp"), None)
    if entry is None:
        raise LookupError(
            "computer-control-mcp ya no está en mcp_catalog.yaml — "
            "actualiza el wiring de t3-3-harness-adapter-contract-registry"
        )
    if entry.status != "verificado":
        raise ValueError(
            f"computer-control-mcp status={entry.status!r} (se esperaba "
            "'verificado') — revisa el adapter antes de confiar en él"
        )

    return AtlasAdapter(
        id="adapter_mcp_computer_control",
        display_name=entry.name,
        provider_type=ProviderType.MCP,
        capability_type="desktop.computer_use",
        required_permissions=[
            "desktop.mouse_control",
            "desktop.keyboard_control",
            "desktop.screen_read",
        ],
        risk_profile=Risk.MEDIUM,
        sandbox_required=True,
        supports_streaming=False,
        supports_diff=False,
        supports_files=False,
        supports_rollback=False,
        emits_events=True,
        memory_policy="summaries_only",
        audit_policy="full",
        failure_modes=[
            "xvfb_display_not_running",
            "stdio_transport_disconnect",
            "ocr_misread",
            "coordinate_out_of_bounds",
        ],
    )
