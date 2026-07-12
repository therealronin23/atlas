"""LegacyLinkLayer — vincular sistemas legacy antes de reemplazarlos.
Canonicidad SIEMPRE explícita; sincronización SIEMPRE apagada por defecto."""

from __future__ import annotations

from atlas.business.models import (
    Canonicality,
    CanonicalityMode,
    LegacyLink,
    LegacyLinkMode,
)


class SyncNotApprovedError(ValueError):
    """Se intentó activar sync sin aprobación humana explícita."""


def propose_link(system: str, mode: LegacyLinkMode) -> LegacyLink:
    """Un link recién propuesto nace SIEMPRE con sync_enabled=False,
    sin importar el modo pedido."""
    return LegacyLink(system=system, mode=mode, sync_enabled=False)


def canonicality_for_link(link: LegacyLink) -> Canonicality:
    """Deriva la política de canonicidad explícita a partir del modo del
    link: mirror/migration mantienen el sistema legacy como fuente de
    verdad hasta que un humano decida lo contrario."""
    if link.mode is LegacyLinkMode.MIGRATION:
        mode = CanonicalityMode.HYBRID_CANONICAL
    else:
        mode = CanonicalityMode.EXTERNAL_CANONICAL
    return Canonicality(mode=mode, source_of_truth=link.system)


def enable_sync(link: LegacyLink, *, human_approved: bool) -> LegacyLink:
    """Solo un humano puede encender la sincronización parcial."""
    if not human_approved:
        raise SyncNotApprovedError(
            f"sync de {link.system} requiere aprobación humana explícita"
        )
    return link.model_copy(update={"sync_enabled": True})
