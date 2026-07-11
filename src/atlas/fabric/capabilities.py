"""Catálogo de capacidades — EN CÓDIGO a propósito (P15-R2): borrar un fixture
no puede relajar la superficie de seguridad. Los fixtures solo AÑADEN
capacidades blandas, jamás redefinen las de aquí.
"""

from __future__ import annotations

from atlas.events.schemas import Risk
from atlas.fabric.models import CapabilitySpec, DataClass


def _cap(
    capability: str,
    risk: Risk,
    data_class: DataClass,
    description: str,
    gate_id: str | None = None,
) -> CapabilitySpec:
    return CapabilitySpec(
        capability=capability,
        risk=risk,
        data_class=data_class,
        description=description,
        gate_required=gate_id is not None,
        gate_id=gate_id,
    )


# Catálogo mínimo constitucional (prompt Fase 15 §MODULE 6).
CAPABILITY_CATALOG: dict[str, CapabilitySpec] = {
    c.capability: c
    for c in [
        _cap("email.read", Risk.LOW, DataClass.PERSONAL,
             "Leer correo (nunca borra ni envía)"),
        _cap("email.draft", Risk.LOW, DataClass.PERSONAL,
             "Crear borradores; el envío es otra capacidad"),
        _cap("email.send", Risk.HIGH, DataClass.PERSONAL,
             "Enviar correo real", "gate_outbound"),
        _cap("message.read", Risk.LOW, DataClass.PERSONAL,
             "Leer mensajes (WhatsApp Business/Telegram/Slack)"),
        _cap("message.send", Risk.HIGH, DataClass.PERSONAL,
             "Enviar mensaje (WhatsApp Business/Telegram/Slack)", "gate_outbound"),
        _cap("crm.contacts.read", Risk.LOW, DataClass.PERSONAL,
             "Leer contactos CRM"),
        _cap("crm.contacts.write", Risk.MEDIUM, DataClass.PERSONAL,
             "Crear/editar contactos CRM", "gate_business_write"),
        _cap("crm.deals.read", Risk.LOW, DataClass.INTERNAL,
             "Leer oportunidades"),
        _cap("crm.deals.update", Risk.MEDIUM, DataClass.INTERNAL,
             "Actualizar oportunidades", "gate_business_write"),
        _cap("crm.bulk_export", Risk.HIGH, DataClass.PERSONAL,
             "Exportación masiva de datos CRM", "gate_data_export"),
        _cap("erp.customers.read", Risk.LOW, DataClass.PERSONAL,
             "Leer clientes ERP"),
        _cap("erp.invoices.read", Risk.LOW, DataClass.SENSITIVE,
             "Leer facturas"),
        _cap("erp.invoices.create_draft", Risk.MEDIUM, DataClass.SENSITIVE,
             "Crear factura BORRADOR (no emitida)", "gate_business_write"),
        _cap("erp.accounting.write", Risk.CRITICAL, DataClass.SENSITIVE,
             "Escribir asientos/contabilidad real", "gate_accounting"),
        _cap("files.read", Risk.LOW, DataClass.INTERNAL,
             "Leer ficheros de carpetas conectadas"),
        _cap("files.write", Risk.MEDIUM, DataClass.INTERNAL,
             "Escribir ficheros", "gate_destructive_fs"),
        _cap("browser.capture", Risk.LOW, DataClass.INTERNAL,
             "Capturar/leer páginas visibles"),
        _cap("browser.fill", Risk.MEDIUM, DataClass.PERSONAL,
             "Rellenar formularios (sin enviar)", "gate_browser_submit"),
        _cap("browser.submit", Risk.HIGH, DataClass.PERSONAL,
             "Enviar formularios web", "gate_browser_submit"),
        _cap("computer_use.execute", Risk.CRITICAL, DataClass.INTERNAL,
             "Control visual del equipo — último recurso, sesión visible",
             "gate_computer_use"),
        _cap("model.cloud_call", Risk.MEDIUM, DataClass.INTERNAL,
             "Llamar a un modelo cloud; con datos sensibles exige aprobación"),
        _cap("memory.write", Risk.MEDIUM, DataClass.PERSONAL,
             "Consolidar en memoria; requiere revisión si fuente externa",
             "gate_memory_review"),
        _cap("official.submit", Risk.CRITICAL, DataClass.SENSITIVE,
             "Presentación oficial (AEAT/registros) — JAMÁS automática",
             "gate_official_submit"),
        _cap("credential.use", Risk.CRITICAL, DataClass.CREDENTIALS,
             "Usar una credencial referenciada", "gate_credentials"),
        _cap("certificate.use", Risk.CRITICAL, DataClass.CREDENTIALS,
             "Usar certificado digital — nunca silencioso", "gate_credentials"),
        _cap("connections.manage", Risk.MEDIUM, DataClass.INTERNAL,
             "Crear/probar conexiones (mock/sandbox libres; real gateado)"),
        _cap("business_core.activate", Risk.HIGH, DataClass.INTERNAL,
             "Activar un Business Core draft", "gate_business_activation"),
    ]
}

READ_SUFFIXES = (".read", ".list", ".get", ".search", ".capture")


def get_capability(name: str) -> CapabilitySpec | None:
    return CAPABILITY_CATALOG.get(name)


def is_read_capability(name: str) -> bool:
    return name.endswith(READ_SUFFIXES)
