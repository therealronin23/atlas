"""
Atlas Core — Cierre de primitivos MCP del tronco (más allá de Tools/Resources/Prompts).

`register_trunk_capabilities` añade a un FastMCP ya construido los primitivos que el
audit (`docs/design/mcp_six_primitives_audit.md`) dejó abiertos, cada uno con un
consumidor real y testeable vía el harness in-memory del SDK:

  - **Completion**  — autocompletado de argumentos sobre el catálogo (kind/name del
    template `catalog://item/{kind}/{name}`) y los nombres de skills (Prompts).
  - **Logging + Progress** — el tool `trunk_selfcheck` recorre el catálogo emitiendo
    logs estructurados y progreso (operación con varias etapas).

Los client-features que SON el workflow (Elicitation/Sampling/Roots) se registran
aparte (capacidad lista; consumidor pleno = SP-E). Diseño:
`docs/superpowers/specs/2026-06-25-mcp-close-primitives-design.md`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# Runtime import: FastMCP necesita resolver la anotación `Context` para detectar e
# inyectar el contexto (y excluirlo del schema del tool). Este módulo SOLO se importa
# de forma diferida dentro de `build_trunk_server`, que ya requiere el extra [mcp].
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel

if TYPE_CHECKING:
    from atlas.mcp.catalog import CatalogEntry
    from atlas.mcp.skills_store import SkillStore


def register_discovery_capabilities(
    server: FastMCP,
    *,
    catalog: "list[CatalogEntry] | None" = None,
    skill_store: "SkillStore | None" = None,
) -> None:
    """Registra Completion (catálogo/skills) y el tool Logging+Progress `trunk_selfcheck`."""
    from mcp.types import (
        Completion,
        PromptReference,
        ResourceTemplateReference,
    )

    @server.completion()
    async def handle_completion(ref: Any, argument: Any, context: Any) -> Any:
        """Autocompletado IDE-like: nombres de skills (Prompts) y kind/name del
        template `catalog://item/{kind}/{name}`. Filtra por lo ya tecleado."""
        value = (getattr(argument, "value", "") or "").lower()

        if isinstance(ref, PromptReference) and skill_store is not None:
            names = skill_store.list_skills()
            return Completion(
                values=[n for n in names if value in n.lower()][:25], hasMore=False
            )

        if isinstance(ref, ResourceTemplateReference) and catalog is not None:
            arg_name = getattr(argument, "name", "")
            if arg_name == "kind":
                kinds = sorted({e.kind for e in catalog})
                return Completion(
                    values=[k for k in kinds if k.startswith(value)][:25], hasMore=False
                )
            if arg_name == "name":
                resolved = getattr(context, "arguments", None) or {}
                want_kind = resolved.get("kind")
                names = sorted(
                    {
                        e.name
                        for e in catalog
                        if want_kind is None or e.kind == want_kind
                    }
                )
                return Completion(
                    values=[n for n in names if value in n.lower()][:25], hasMore=False
                )
        return None

    if catalog is not None:

        @server.tool()
        async def trunk_selfcheck(ctx: Context[Any, Any]) -> dict[str, Any]:
            """Chequeo de cobertura del catálogo por estado, emitiendo LOGS
            estructurados y PROGRESO por etapas (demuestra ambos primitivos en una
            operación real). Devuelve cuentas + aviso si dominan los candidatos."""
            from atlas.mcp.catalog import by_status

            await ctx.info(f"selfcheck: {len(catalog)} entradas en catálogo")
            await ctx.report_progress(progress=0.0, total=2.0, message="contando estados")
            counts = by_status(catalog)
            await ctx.report_progress(progress=1.0, total=2.0, message="evaluando salud")
            candidato = counts.get("candidato", 0)
            usable = counts.get("verificado", 0) + counts.get("instalado", 0)
            if candidato > usable:
                await ctx.warning(
                    f"catálogo dominado por candidatos ({candidato} vs {usable} usables)"
                )
            await ctx.report_progress(progress=2.0, total=2.0, message="listo")
            return {"by_status": counts, "usable": usable, "candidato": candidato}


class _ConfirmDecision(BaseModel):
    """Schema de Elicitation: la decisión humana estructurada (HITL)."""

    confirmed: bool


def register_workflow_capabilities(server: FastMCP) -> None:
    """Registra los client-features que SON el workflow (capacidad lista; consumidor
    pleno = SP-E): Elicitation (HITL estructurado), Sampling (offload de razonamiento
    al modelo del cliente) y Roots (ámbitos de filesystem concedidos por el cliente).

    Hoy se exponen como tools mínimas y testeadas; el workflow autónomo los consumirá
    de verdad (puntos de decisión, regulador de tokens SP-B, acceso acotado)."""
    from mcp.types import SamplingMessage, TextContent

    @server.tool()
    async def trunk_confirm(question: str, ctx: Context[Any, Any]) -> dict[str, Any]:
        """ELICITATION: pide al humano una confirmación estructurada (sí/no). El hook
        nativo de HITL — el workflow lo usará para sus puntos de decisión."""
        result = await ctx.elicit(message=question, schema=_ConfirmDecision)
        confirmed = bool(result.data.confirmed) if (
            result.action == "accept" and result.data is not None
        ) else False
        return {"action": result.action, "confirmed": confirmed}

    @server.tool()
    async def trunk_reason(
        prompt: str, ctx: Context[Any, Any], max_tokens: int = 256
    ) -> str:
        """SAMPLING: pide un completion al MODELO DEL CLIENTE (el server no integra ni
        paga modelo). Offload de razonamiento — base del regulador de tokens (SP-B)."""
        result = await ctx.session.create_message(
            messages=[
                SamplingMessage(role="user", content=TextContent(type="text", text=prompt))
            ],
            max_tokens=max_tokens,
        )
        content = result.content
        return content.text if getattr(content, "type", None) == "text" else str(content)

    @server.tool()
    async def trunk_list_roots(ctx: Context[Any, Any]) -> list[str]:
        """ROOTS: ámbitos de filesystem que el cliente concede al server. Útil cuando el
        workflow opere sobre rutas acotadas por el host."""
        result = await ctx.session.list_roots()
        return [str(r.uri) for r in result.roots]


def register_subscription_capabilities(
    server: FastMCP, *, manifest_uri: str = "catalog://manifest"
) -> set[str]:
    """SUBSCRIPTIONS del catálogo: el cliente se subscribe a `catalog://manifest` y
    recibe `resources/updated` cuando el catálogo cambia.

    Entrega la CAPACIDAD real (handlers subscribe/unsubscribe + seam de publish), no el
    watcher automático de fondo: FastMCP corre un loop síncrono y el push out-of-band
    exigiría reescribir el server a low-level (su propio proyecto). El seam
    `trunk_notify_catalog_changed` es el punto que el watcher/sync invocará al madurar.
    Devuelve el set vivo de URIs subscritas (para tests/observabilidad)."""
    from pydantic import AnyUrl

    subscribed: set[str] = set()
    low_level = server._mcp_server

    @low_level.subscribe_resource()
    async def _subscribe(uri: AnyUrl) -> None:
        subscribed.add(str(uri))

    @low_level.unsubscribe_resource()
    async def _unsubscribe(uri: AnyUrl) -> None:
        subscribed.discard(str(uri))

    @server.tool()
    async def trunk_notify_catalog_changed(ctx: Context[Any, Any]) -> dict[str, Any]:
        """Emite `resources/updated` a los subscritos del manifest. Seam de publish que
        el watcher/sync invocará cuando el catálogo cambie (hoy disparable a mano)."""
        sent: list[str] = []
        for uri in list(subscribed):
            await ctx.session.send_resource_updated(AnyUrl(uri))
            sent.append(uri)
        return {"notified": sent}

    return subscribed
