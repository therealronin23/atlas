"""Catálogo de kinds del Business Core — reexporta EntityKind (autoridad:
schemas/business_entity.schema.json) y agrupa los kinds por vista CRM/ERP
para que la UI/API no dupliquen la lista."""

from __future__ import annotations

from atlas.business.models import EntityKind

__all__ = ["CRM_KINDS", "ERP_KINDS", "SHARED_KINDS", "EntityKind"]

CRM_KINDS: frozenset[EntityKind] = frozenset({
    EntityKind.CUSTOMER, EntityKind.CONTACT, EntityKind.COMPANY,
    EntityKind.OPPORTUNITY, EntityKind.TASK, EntityKind.COMMUNICATION,
    EntityKind.NOTE, EntityKind.QUOTE,
})

ERP_KINDS: frozenset[EntityKind] = frozenset({
    EntityKind.SUPPLIER, EntityKind.PRODUCT, EntityKind.SERVICE,
    EntityKind.ORDER, EntityKind.INVOICE, EntityKind.RECEIPT,
    EntityKind.DELIVERY_NOTE, EntityKind.STOCK_ITEM, EntityKind.PAYMENT,
})

# Kinds que no pertenecen exclusivamente a una vista (documentos, casos,
# proyectos, evidencia, riesgo, eventos genéricos).
SHARED_KINDS: frozenset[EntityKind] = frozenset(EntityKind) - CRM_KINDS - ERP_KINDS
