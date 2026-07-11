"""Connection Ladder — el orden ES la política: API-first, computer-use
penúltimo, humano último. Codificada como dato para que la UI, el concierge
y los tests consuman la misma verdad."""

from __future__ import annotations

from atlas.events.schemas import Risk
from atlas.fabric.models import RouteType

# Riesgo intrínseco de cada peldaño (independiente de la capacidad pedida).
LADDER: list[tuple[RouteType, Risk]] = [
    (RouteType.NATIVE_API, Risk.LOW),
    (RouteType.MANAGED_OAUTH, Risk.LOW),
    (RouteType.OPENAPI_REST, Risk.LOW),
    (RouteType.ASYNCAPI_EVENTS, Risk.LOW),
    (RouteType.WEBHOOKS, Risk.MEDIUM),
    (RouteType.MCP, Risk.MEDIUM),
    (RouteType.DATABASE_FILE, Risk.MEDIUM),
    (RouteType.IMPORT_EXPORT_BATCH, Risk.LOW),
    (RouteType.BROWSER_EXTENSION_BRIDGE, Risk.HIGH),
    (RouteType.DESKTOP_AUTOMATION, Risk.HIGH),
    (RouteType.COMPUTER_USE, Risk.CRITICAL),
    (RouteType.HUMAN_MANUAL, Risk.LOW),
]

_POSITION: dict[RouteType, int] = {route: i for i, (route, _) in enumerate(LADDER)}
_RISK: dict[RouteType, Risk] = dict(LADDER)


def rung(route: RouteType) -> int:
    """Posición 1-based en la escalera (1 = preferida)."""
    return _POSITION[route] + 1


def route_risk(route: RouteType) -> Risk:
    return _RISK[route]


def order_routes(routes: list[RouteType]) -> list[RouteType]:
    """Ordena candidatas según la escalera (API-first)."""
    return sorted(routes, key=lambda r: _POSITION[r])


def ladder_violations(
    recommended: RouteType, fallbacks: list[RouteType]
) -> list[str]:
    """Reglas duras de la escalera para validar recetas.

    - computer_use jamás puede ser la ruta recomendada.
    - la recomendada no puede estar por debajo de un fallback API-cercano
      (una receta que recomienda desktop_automation teniendo native_api
      como fallback está rota).
    """
    problems: list[str] = []
    if recommended is RouteType.COMPUTER_USE:
        problems.append("computer_use no puede ser ruta recomendada (alto riesgo, último recurso)")
    for fb in fallbacks:
        if _POSITION[fb] < _POSITION[recommended] and fb is not RouteType.HUMAN_MANUAL:
            problems.append(
                f"fallback {fb.value} es preferible en la escalera a la recomendada "
                f"{recommended.value}: invertir"
            )
    return problems
