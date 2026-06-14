"""
KnowledgeVerifier — grounding de KnowledgeArtifact (capa 1, CostTier.STATIC).

Tres checks:
  (a) provenance bien formada: url|endpoint, fetched_at ISO 8601, raw_sha256 no vacío.
  (b) hash coincide: sha256(raw_payload) == provenance['raw_sha256'].
  (c) content no vacío.

PASS solo si los tres pasan; si no, FAIL con reason explícito.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from atlas.core.verify import Check, CostTier, Evidence, Verdict
from atlas.knowledge.artifact import KnowledgeArtifact


class KnowledgeVerifier:
    verifier_id = "knowledge_grounding"
    cost = CostTier.STATIC

    def verify(self, artifact: KnowledgeArtifact, raw_payload: str) -> Evidence:
        checks: list[Check] = []

        # (a) provenance bien formada
        prov = artifact.provenance
        reasons_a: list[str] = []

        has_origin = bool(prov.get("url") or prov.get("endpoint"))
        if not has_origin:
            reasons_a.append("falta url o endpoint en provenance")

        fetched_at = prov.get("fetched_at", "")
        if not fetched_at:
            reasons_a.append("falta fetched_at en provenance")
        else:
            try:
                datetime.fromisoformat(str(fetched_at))
            except ValueError:
                reasons_a.append(f"fetched_at no es ISO 8601 válido: {fetched_at!r}")

        raw_sha256 = prov.get("raw_sha256", "")
        if not raw_sha256:
            reasons_a.append("falta raw_sha256 en provenance")

        check_a = Check(
            name="provenance_wellformed",
            passed=not reasons_a,
            detail="; ".join(reasons_a),
            cost=CostTier.STATIC,
        )
        checks.append(check_a)

        # (b) hash coincide con raw_payload
        computed = hashlib.sha256(raw_payload.encode()).hexdigest()
        hash_ok = computed == str(raw_sha256)
        check_b = Check(
            name="hash_match",
            passed=hash_ok,
            detail="" if hash_ok else f"esperado={raw_sha256!r} calculado={computed!r}",
            cost=CostTier.STATIC,
        )
        checks.append(check_b)

        # (c) content no vacío
        content = artifact.content
        content_ok = bool(content) and content != {} and content != ""
        check_c = Check(
            name="content_nonempty",
            passed=content_ok,
            detail="" if content_ok else "content está vacío o es None",
            cost=CostTier.STATIC,
        )
        checks.append(check_c)

        all_pass = check_a.passed and check_b.passed and check_c.passed
        failed = [c for c in checks if not c.passed]
        reason = "; ".join(c.detail for c in failed) if failed else ""

        return Evidence(
            verdict=Verdict.PASS if all_pass else Verdict.FAIL,
            checks=tuple(checks),
            total_cost=CostTier.STATIC,
            verifier_ids=(self.verifier_id,),
            reason=reason,
        )
