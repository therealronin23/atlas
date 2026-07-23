"""compile_openapi_to_recipe — compilador OpenAPI 3.x -> ConnectionRecipe.

t3-4-openapi-to-capability-compiler: dada una spec OpenAPI mínima
(paths+operations+security scheme), deriva un ConnectionRecipe válido que
pase validate_recipe() sin RecipeProblem. Sin red real: parseo de dict ya
cargado.
"""

from __future__ import annotations

from atlas.fabric.models import ConnectionRecipe, RouteType
from atlas.fabric.recipes import RecipeEngine, compile_openapi_to_recipe, validate_recipe

SYNTHETIC_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Acme Tasks API", "version": "1.0.0"},
    "paths": {
        "/tasks": {
            "get": {"operationId": "listTasks", "summary": "Listar tareas"},
            "post": {"operationId": "createTask", "summary": "Crear tarea"},
        },
        "/tasks/{task_id}": {
            "get": {"operationId": "getTask", "summary": "Leer una tarea"},
            "delete": {"operationId": "deleteTask", "summary": "Borrar tarea"},
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
        },
    },
}


def test_compile_returns_connection_recipe() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    assert isinstance(recipe, ConnectionRecipe)
    assert recipe.recommended_route is RouteType.OPENAPI_REST


def test_compile_derives_connector_id_from_title() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    assert recipe.connector_id == "acme_tasks_api"
    assert recipe.human_name == "Acme Tasks API"


def test_compile_derives_read_capability_from_get() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    assert "files.read" in recipe.capabilities


def test_compile_gates_write_capability_instead_of_granting() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    # post/delete son mutaciones: nunca concedidas por defecto, siempre gateadas.
    assert "files.write" not in recipe.capabilities
    assert "files.write" in recipe.gated_capabilities


def test_compile_safe_defaults_have_no_dangerous_outbound_true() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    dangerous = {"send", "delete", "publish", "pay", "sign", "file"}
    for action, allowed in recipe.safe_defaults.items():
        if action in dangerous:
            assert allowed is False


def test_compile_derives_bearer_credential() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    assert recipe.credential is not None
    assert recipe.credential.auth_mode == "bearer_token"


def test_compile_passes_validate_recipe_without_problems() -> None:
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    assert validate_recipe(recipe) == []


def test_compile_accepted_by_recipe_engine_end_to_end(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """El RecipeEngine real (el mismo que carga fixtures/) acepta la receta
    compilada tal cual, serializada a JSON como cualquier *.recipe.json."""
    recipe = compile_openapi_to_recipe(SYNTHETIC_SPEC)
    (tmp_path / f"{recipe.connector_id}.recipe.json").write_text(
        recipe.model_dump_json(), encoding="utf-8"
    )
    engine = RecipeEngine(tmp_path)
    assert engine.rejected == {}
    loaded = engine.get(recipe.connector_id)
    assert loaded is not None
    assert loaded.recommended_route is RouteType.OPENAPI_REST


def test_compile_read_only_spec_has_no_gated_write() -> None:
    read_only_spec = {
        "info": {"title": "Read Only API"},
        "paths": {"/items": {"get": {"operationId": "listItems"}}},
    }
    recipe = compile_openapi_to_recipe(read_only_spec)
    assert recipe.gated_capabilities == {}
    assert "files.read" in recipe.capabilities
    assert validate_recipe(recipe) == []
