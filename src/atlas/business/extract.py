"""EntityCandidateExtractor — reglas deterministas sobre evidencia
ESTRUCTURADA (no NLP, no juicio de modelo). requires_review es siempre
True: ningún candidato se promociona solo (ver core_engine.promote_candidate).
"""

from __future__ import annotations

import uuid
from typing import Any

from atlas.business.models import EntityCandidate, EntityKind


def extract_contacts_from_gmail(
    contacts: list[dict[str, Any]], source_ref: str,
) -> list[EntityCandidate]:
    """contacts: [{"name": str|None, "email": str}, ...] — confianza
    determinista: 0.9 con nombre+email, 0.6 solo con email."""
    out: list[EntityCandidate] = []
    for c in contacts:
        email = c.get("email")
        if not email:
            continue
        name = c.get("name")
        confidence = 0.9 if name else 0.6
        out.append(EntityCandidate(
            candidate_id=f"cand_{uuid.uuid4().hex[:10]}",
            kind=EntityKind.CONTACT,
            label=name or email,
            confidence=confidence,
            source_refs=[source_ref],
            proposed_data={"email": email, "name": name},
            requires_review=True,
        ))
    return out


def extract_from_invoices(
    invoices: list[dict[str, Any]], source_ref: str,
) -> list[EntityCandidate]:
    """invoices: [{"role": "customer"|"supplier", "name": str,
    "tax_id": str|None, "invoice_number": str|None, "amount": float|None}]
    Confianza determinista: 0.95 con tax_id, 0.7 sin él. Cada factura con
    invoice_number produce ADEMÁS un candidato kind=invoice."""
    out: list[EntityCandidate] = []
    for inv in invoices:
        role = inv.get("role")
        kind = EntityKind.SUPPLIER if role == "supplier" else EntityKind.CUSTOMER
        name = inv["name"]
        tax_id = inv.get("tax_id")
        confidence = 0.95 if tax_id else 0.7
        out.append(EntityCandidate(
            candidate_id=f"cand_{uuid.uuid4().hex[:10]}",
            kind=kind,
            label=name,
            confidence=confidence,
            source_refs=[source_ref],
            proposed_data={"name": name, "tax_id": tax_id},
            requires_review=True,
        ))
        number = inv.get("invoice_number")
        if number:
            out.append(EntityCandidate(
                candidate_id=f"cand_{uuid.uuid4().hex[:10]}",
                kind=EntityKind.INVOICE,
                label=f"Factura {number}",
                confidence=0.96,
                source_refs=[source_ref],
                proposed_data={"invoice_number": number,
                               "amount": inv.get("amount"), "party": name},
                requires_review=True,
            ))
    return out
