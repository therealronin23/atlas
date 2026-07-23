"""ConnectorRecipeEngine — carga y valida recetas de conexión humanas.

Una receta inválida no se sirve a medias: se excluye y se reporta
(fail-closed sobre el catálogo)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from atlas.fabric.capabilities import get_capability
from atlas.fabric.ladder import ladder_violations
from atlas.fabric.models import (
    ConnectionRecipe,
    ConnectorCategory,
    CredentialSpec,
    DefaultMode,
    Difficulty,
    PermissionsExplainer,
    RouteType,
    SetupStep,
    StepKind,
)


class RecipeProblem(Exception):
    """Receta estructuralmente inválida o insegura."""


def validate_recipe(recipe: ConnectionRecipe) -> list[str]:
    """Reglas semánticas más allá del schema."""
    problems: list[str] = []
    problems.extend(
        ladder_violations(recipe.recommended_route, recipe.fallback_routes)
    )
    overlap = set(recipe.capabilities) & set(recipe.forbidden_capabilities)
    if overlap:
        problems.append(f"capacidades a la vez concedidas y prohibidas: {sorted(overlap)}")
    for cap in [*recipe.capabilities, *recipe.gated_capabilities,
                *recipe.forbidden_capabilities]:
        if get_capability(cap) is None:
            problems.append(f"capacidad fuera de catálogo: {cap}")
    for cap in recipe.capabilities:
        spec = get_capability(cap)
        if spec is not None and spec.gate_required:
            problems.append(
                f"{cap} exige gate en el catálogo: debe ir en gated_capabilities, "
                "no concedida por defecto"
            )
    for action, allowed in recipe.safe_defaults.items():
        if action in {"send", "delete", "publish", "pay", "sign", "file"} and allowed:
            problems.append(f"safe_defaults.{action}=true viola no-outbound-por-defecto")
    return problems


# -- Compilador OpenAPI -> ConnectionRecipe (t3-4) ---------------------------
#
# Métodos HTTP que solo leen frente a los que mutan estado. El catálogo de
# capacidades (atlas/fabric/capabilities.py) es cerrado y NO tiene un
# namespace por-conector para APIs REST genéricas; reusamos el par
# files.read/files.write ya existente en el catálogo (mismo usado por otros
# fixtures de import genérico, ver tests/test_os_fabric.py) como el bucket
# neutro de "acceso a datos vía la API conectada" — no reinventamos ni
# tocamos el catálogo (fuera de alcance de esta tarea).
_READ_METHODS = {"get", "head"}
_WRITE_METHODS = {"post", "put", "patch", "delete"}
_HTTP_METHODS = _READ_METHODS | _WRITE_METHODS

_READ_CAPABILITY = "files.read"
_WRITE_CAPABILITY = "files.write"

# openapi 3.x securitySchemes.type/scheme -> CredentialSpec.auth_mode.
_SECURITY_AUTH_MODES: dict[tuple[str, str | None], str] = {
    ("apiKey", None): "api_key",
    ("http", "bearer"): "bearer_token",
    ("http", "basic"): "basic_auth",
    ("oauth2", None): "oauth2",
    ("openIdConnect", None): "oauth2",
}


def _slugify_connector_id(title: str) -> str:
    """Deriva un connector_id válido (pattern ^[a-z0-9_]+$) de info.title."""
    slug = re.sub(r"[^a-z0-9]+", "_", title.strip().lower()).strip("_")
    return slug or "openapi_connector"


def _methods_present(spec: dict[str, Any]) -> tuple[bool, bool]:
    """(hay_lectura, hay_escritura) barriendo paths+operations de la spec."""
    has_read = False
    has_write = False
    paths = spec.get("paths") or {}
    for path_item in paths.values():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            m = method.lower()
            if m in _READ_METHODS:
                has_read = True
            elif m in _WRITE_METHODS:
                has_write = True
    return has_read, has_write


def _credential_from_security(spec: dict[str, Any]) -> CredentialSpec | None:
    """Primer securityScheme reconocible -> CredentialSpec de referencia
    (nunca en claro: storage siempre credential_reference_only)."""
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    for scheme in schemes.values():
        if not isinstance(scheme, dict):
            continue
        scheme_type = scheme.get("type")
        scheme_variant = scheme.get("scheme")
        if not isinstance(scheme_type, str):
            continue
        variant = scheme_variant if isinstance(scheme_variant, str) else None
        auth_mode = _SECURITY_AUTH_MODES.get((scheme_type, variant)) or _SECURITY_AUTH_MODES.get(
            (scheme_type, None)
        )
        if auth_mode is not None:
            return CredentialSpec(auth_mode=auth_mode, storage="credential_reference_only")
    return None


def compile_openapi_to_recipe(spec: dict[str, Any]) -> ConnectionRecipe:
    """Deriva un ConnectionRecipe a partir de una spec OpenAPI 3.x mínima.

    Sin red real: `spec` es un dict ya cargado (json.load de un fichero o de
    una respuesta ya obtenida por otra vía). No hace de cliente HTTP.

    Diseño (closed-world de capacidades, ver comentario arriba de
    _READ_METHODS): GET/HEAD conceden `files.read` de inmediato (bajo
    riesgo); POST/PUT/PATCH/DELETE se agrupan en `files.write` pero SIEMPRE
    vía gated_capabilities — nunca concedidas por defecto, cumpliendo
    "safe_defaults sin outbound peligroso por defecto" con independencia de
    cuántos endpoints mutantes tenga la spec.
    """
    info = spec.get("info") or {}
    title = str(info.get("title") or "OpenAPI connector")
    connector_id = _slugify_connector_id(title)

    has_read, has_write = _methods_present(spec)

    capabilities = [_READ_CAPABILITY] if has_read else []
    gated_capabilities: dict[str, str] = {}
    if has_write:
        write_spec = get_capability(_WRITE_CAPABILITY)
        gate_id = write_spec.gate_id if write_spec is not None and write_spec.gate_id else "gate_destructive_fs"
        gated_capabilities[_WRITE_CAPABILITY] = gate_id

    credential = _credential_from_security(spec)

    setup_steps = [
        SetupStep(
            step_id="1",
            kind=StepKind.AUTOMATIC,
            description=f"Atlas compiló la receta desde la spec OpenAPI de {title}",
        )
    ]
    if credential is not None:
        setup_steps.append(
            SetupStep(
                step_id="2",
                kind=StepKind.MANUAL_SECRET,
                description="Introducir la credencial de la API; Atlas la guarda solo como referencia opaca",
            )
        )

    will = []
    will_not = ["Eliminar datos sin tu aprobación explícita"]
    if has_read:
        will.append(f"Leer datos vía la API de {title}")
    if has_write:
        will_not.insert(0, "Escribir/modificar datos vía la API sin tu aprobación explícita (gate)")

    recipe = ConnectionRecipe(
        connector_id=connector_id,
        human_name=title,
        category=ConnectorCategory.FILES_DOCUMENTS,
        recommended_route=RouteType.OPENAPI_REST,
        fallback_routes=[RouteType.WEBHOOKS, RouteType.HUMAN_MANUAL],
        difficulty=Difficulty.TECHNICAL,
        default_mode=DefaultMode.READ_ONLY,
        safe_defaults={"read": has_read, "write": False, "delete": False},
        capabilities=capabilities,
        gated_capabilities=gated_capabilities,
        forbidden_capabilities=[],
        setup_steps=setup_steps,
        permissions_explainer=PermissionsExplainer(will=will, will_not=will_not),
        demo=False,
        credential=credential,
    )
    return recipe


class RecipeEngine:
    def __init__(self, recipes_dir: Path) -> None:
        self._recipes: dict[str, ConnectionRecipe] = {}
        self._rejected: dict[str, list[str]] = {}
        if recipes_dir.exists():
            for path in sorted(recipes_dir.glob("*.recipe.json")):
                try:
                    recipe = ConnectionRecipe.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                except (ValidationError, json.JSONDecodeError) as exc:
                    self._rejected[path.stem] = [f"schema: {exc}"]
                    continue
                problems = validate_recipe(recipe)
                if problems:
                    self._rejected[recipe.connector_id] = problems
                else:
                    self._recipes[recipe.connector_id] = recipe

    @property
    def rejected(self) -> dict[str, list[str]]:
        return dict(self._rejected)

    def all(self) -> list[ConnectionRecipe]:
        return list(self._recipes.values())

    def get(self, connector_id: str) -> ConnectionRecipe | None:
        return self._recipes.get(connector_id)

    def catalog(self) -> dict[str, list[dict[str, str]]]:
        """Catálogo humano por categoría (Connection Store)."""
        grouped: dict[str, list[dict[str, str]]] = {}
        for r in self._recipes.values():
            grouped.setdefault(r.category.value, []).append({
                "connector_id": r.connector_id,
                "human_name": r.human_name,
                "difficulty": r.difficulty.value,
                "recommended_route": r.recommended_route.value,
                "default_mode": r.default_mode.value,
            })
        for items in grouped.values():
            items.sort(key=lambda item: item["human_name"])
        return grouped
