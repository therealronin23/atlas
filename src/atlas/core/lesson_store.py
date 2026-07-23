"""
Capa 4 — LessonStore: lecciones verificadas, no narrativas.

Una `Lesson` es un artefacto DURO: heurística de detección + patrón a evitar +
una `Evidence` (tipo de capa 1) que prueba que la lección es real. La ley de
entrada es una precondición de tipo: **sin `Evidence` con verdict PASS, no hay
Lesson** — el antídoto contra alimentarse de basura.

El verificador es polimórfico por procedencia, pero siempre produce `Evidence`:

- `INTERNAL_FAILURE`: prove-it — el test de regresión falla contra el código de
  antes del fix y pasa contra el actual. Sin ese rojo-antes/verde-ahora, la
  lección no demuestra que el test caza el fallo.
- `EXTERNAL_SOURCE`: gate de corroboración — ≥1 fuente autoritativa corrobora
  (el mismo gate fail-closed del MaintenanceAnalyst, que excluye tokens
  genéricos). Foros aportan señal, no autoridad.

Relación con lo existente (densidad, no maquinaria nueva): el `ErrorRegistry`
sigue siendo la captura BLANDA de fallos en runtime; un `FailureEntry` se
*promociona* a `Lesson` solo cuando se le adjunta su prueba. Dos niveles: fallo
observado → lección verificada.

NOTA (2026-06-13): esta iteración construye el núcleo store+verificador. El
cableado de CONSUMIDORES (Analyst/codegen cargan lecciones como contexto) se
difiere a la capa 3, donde codegen tendrá contexto de ejecución alcanzable
(ver docs/audits/audit_postmortem_2026-06-13.md).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from atlas.core.verify import Check, CostTier, Evidence, Verdict
from atlas.logging.merkle_logger import MerkleLogger
from atlas.memory.memory_system import ErrorRegistry


class LessonProvenance(str, Enum):
    INTERNAL_FAILURE = "internal_failure"
    EXTERNAL_SOURCE = "external_source"


@dataclass(frozen=True)
class ProveItResult:
    """Resultado del prove-it: el test de regresión corrido contra dos refs."""

    test_path: str
    fix_commit: str
    failed_before: bool  # falló contra fix_commit^ (prueba que caza el fallo)
    passes_after: bool   # pasa contra fix_commit (prueba que el fix funciona)


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str
    provenance: LessonProvenance
    detection_heuristic: str
    avoid_pattern: str
    evidence: dict[str, Any]
    regression_test_path: str | None = None
    source_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Fallos recurrentes (no éxitos puntuales): cuántas veces se ha visto el
    # MISMO fallo (ver LessonStore.record_recurring) y cuándo fue la última.
    # Defaults retrocompatibles: lecciones guardadas antes de este campo se
    # leen como occurrence_count=1, last_seen_at="" (mismo patrón que created_at).
    occurrence_count: int = 1
    last_seen_at: str = ""
    # Ciclo de vida por USO real (absorbido de Hermes-Agent curator.py,
    # 2026-07-18 — patrón determinista active→stale→archived, nunca borra).
    # recall_count/last_recalled_at se incrementan SOLO en un match real de
    # LessonRecaller.recall() (ver LessonStore.record_recall), no en cada
    # consulta — evidencia de uso, no de intento. Defaults retrocompatibles:
    # lecciones existentes se leen como recall_count=0, state="active".
    recall_count: int = 0
    last_recalled_at: str = ""
    state: str = "active"  # active | stale | archived — nunca se borra el fichero

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.value
        d["source_refs"] = list(self.source_refs)
        d["tags"] = list(self.tags)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lesson:
        return cls(
            id=data["id"],
            title=data["title"],
            provenance=LessonProvenance(data["provenance"]),
            detection_heuristic=data["detection_heuristic"],
            avoid_pattern=data["avoid_pattern"],
            evidence=data.get("evidence", {}),
            regression_test_path=data.get("regression_test_path"),
            source_refs=tuple(data.get("source_refs", ())),
            tags=tuple(data.get("tags", ())),
            created_at=data.get("created_at", ""),
            occurrence_count=data.get("occurrence_count", 1),
            last_seen_at=data.get("last_seen_at", ""),
            recall_count=data.get("recall_count", 0),
            last_recalled_at=data.get("last_recalled_at", ""),
            state=data.get("state", "active"),
        )


class LessonVerifier:
    """Produce `Evidence` (capa 1) según la procedencia. No corre nada por su
    cuenta: recibe el resultado del prove-it o de la corroboración ya
    capturados, para mantenerse testeable sin red ni subprocesos."""

    def verify_internal(self, prove_it: ProveItResult) -> Evidence:
        passed = prove_it.failed_before and prove_it.passes_after
        if passed:
            detail = f"rojo en {prove_it.fix_commit}^, verde en {prove_it.fix_commit}"
        elif not prove_it.failed_before:
            detail = "el test NO falla contra el código previo: no demuestra que cace el fallo"
        else:
            detail = "el test NO pasa contra el código actual: el fix no está probado"
        check = Check(
            name="prove_it",
            passed=passed,
            detail=f"{prove_it.test_path}: {detail}",
            cost=CostTier.SUITE,
        )
        return Evidence(
            verdict=Verdict.PASS if passed else Verdict.FAIL,
            checks=(check,),
            total_cost=CostTier.SUITE,
            verifier_ids=("lesson.prove_it",),
            reason="" if passed else detail,
        )

    def verify_external(self, *, corroborated: bool, reason: str = "") -> Evidence:
        check = Check(
            name="corroboration",
            passed=corroborated,
            detail=reason,
            cost=CostTier.STATIC,
        )
        return Evidence(
            verdict=Verdict.PASS if corroborated else Verdict.FAIL,
            checks=(check,),
            total_cost=CostTier.STATIC,
            verifier_ids=("lesson.corroboration",),
            reason="" if corroborated else (reason or "sin fuente autoritativa que corrobore"),
        )


class LessonRejected(Exception):
    """add() rechazó una lección sin Evidence PASS — la ley de entrada."""


class LessonStore:
    """Store de ficheros JSON, hermano de ApprovedPatternStore/ErrorRegistry.
    La única ley: no se guarda una lección cuyo Evidence no sea PASS."""

    def __init__(self, store_path: Path, *, merkle: MerkleLogger | None = None) -> None:
        self._path = store_path
        self._path.mkdir(parents=True, exist_ok=True)
        self._merkle = merkle

    def add(self, lesson: Lesson) -> Lesson:
        if lesson.evidence.get("verdict") != Verdict.PASS.value:
            raise LessonRejected(
                f"lección {lesson.id!r} sin Evidence PASS "
                f"(verdict={lesson.evidence.get('verdict')!r}): no entra al store"
            )
        file = self._path / f"{lesson.id}.json"
        file.write_text(
            json.dumps(lesson.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if self._merkle is not None:
            self._merkle.log(
                action="lesson.recorded",
                agent="lesson_store",
                result="success",
                risk_level="safe",
                payload={
                    "id": lesson.id,
                    "provenance": lesson.provenance.value,
                    "title": lesson.title,
                },
            )
        return lesson

    def get(self, lesson_id: str) -> Lesson | None:
        file = self._path / f"{lesson_id}.json"
        if not file.is_file():
            return None
        return Lesson.from_dict(json.loads(file.read_text(encoding="utf-8")))

    def all(self) -> list[Lesson]:
        results: list[Lesson] = []
        for f in self._path.glob("*.json"):
            try:
                results.append(Lesson.from_dict(json.loads(f.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001 — un fichero corrupto no tumba el resto
                continue
        return sorted(results, key=lambda lesson: lesson.created_at, reverse=True)

    def by_provenance(self, provenance: LessonProvenance) -> list[Lesson]:
        return [lesson for lesson in self.all() if lesson.provenance is provenance]

    def search_by_tag(self, tag: str) -> list[Lesson]:
        return [lesson for lesson in self.all() if tag in lesson.tags]

    def record_recurring(
        self,
        *,
        dedup_key: str,
        title: str,
        detection_heuristic: str,
        avoid_pattern: str,
        evidence: dict[str, Any],
        source_refs: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
    ) -> Lesson | None:
        """Fallos recurrentes: si ya existe una lección con el tag
        'dedup:<dedup_key>', incrementa su occurrence_count y actualiza
        last_seen_at en el MISMO archivo (no crea uno nuevo). Si no existe,
        la crea vía LessonPromoter.ingest_external con corroborated=True —
        el dedup_key viene de un evento real detectado por el propio sistema
        (no de una fuente externa sin verificar), así que el gate fail-closed
        de ingest_external siempre se satisface aquí.

        `evidence` se acepta por firma/documentación del caso de uso (qué
        disparó este fallo recurrente) pero NO se reenvía a ingest_external:
        esa función no toma un dict de evidencia externo, construye su propio
        Evidence vía LessonVerifier.verify_external(corroborated=...). El
        detalle bruto de `evidence` queda fuera del objeto Lesson persistido;
        si en el futuro hace falta conservarlo, debe ir dentro de
        `avoid_pattern`/`detection_heuristic` o como source_ref adicional."""
        dedup_tag = f"dedup:{dedup_key}"
        existing = self.search_by_tag(dedup_tag)
        if existing:
            latest = max(existing, key=lambda lesson: lesson.created_at)
            updated = replace(
                latest,
                occurrence_count=latest.occurrence_count + 1,
                last_seen_at=datetime.now(timezone.utc).isoformat(),
            )
            file = self._path / f"{updated.id}.json"
            file.write_text(
                json.dumps(updated.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return updated

        promoter = LessonPromoter(self)
        return promoter.ingest_external(
            title=title,
            detection_heuristic=detection_heuristic,
            avoid_pattern=avoid_pattern,
            source_refs=source_refs,
            corroborated=True,
            tags=(*tags, dedup_tag),
        )

    def record_recall(self, lesson_id: str) -> Lesson | None:
        """Registra un recall REAL (match, no cada consulta): incrementa
        recall_count, marca last_recalled_at y reactiva si estaba `stale`.
        Mismo patrón replace()+rewrite que record_recurring(). None si el id
        no existe (no lanza — el caller no debe caerse por una lección ya
        purgada a mano)."""
        lesson = self.get(lesson_id)
        if lesson is None:
            return None
        updated = replace(
            lesson,
            recall_count=lesson.recall_count + 1,
            last_recalled_at=datetime.now(timezone.utc).isoformat(),
            state="active" if lesson.state == "stale" else lesson.state,
        )
        file = self._path / f"{updated.id}.json"
        file.write_text(
            json.dumps(updated.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return updated

    def apply_lifecycle_transitions(
        self,
        *,
        now: datetime | None = None,
        stale_after_days: int = 30,
        archive_after_days: int = 90,
    ) -> dict[str, int]:
        """Ciclo de vida determinista por inactividad — patrón absorbido de
        Hermes-Agent (`agent/curator.py::apply_automatic_transitions`,
        2026-07-18): active→stale tras `stale_after_days` sin recall,
        stale→archived tras `archive_after_days`, reactiva si vuelve a haber
        recall. NUNCA borra el fichero — `archived` es solo una etiqueta,
        recuperable (misma disciplina de `_graveyard`/WHY.md del repo: marcar
        y archivar, no destruir). Ancla el reloj en `last_recalled_at` si
        existe, si no en `created_at` — una lección recién creada sin recall
        aún no se marca stale por eso solo (grace floor, igual que Hermes:
        ausencia de evidencia no es evidencia de obsolescencia).

        Devuelve un contador de qué cambió, igual que la función de Hermes."""
        if now is None:
            now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(days=stale_after_days)
        archive_cutoff = now - timedelta(days=archive_after_days)

        counts = {"marked_stale": 0, "archived": 0, "reactivated": 0, "checked": 0}

        for lesson in self.all():
            counts["checked"] += 1
            anchor_raw = lesson.last_recalled_at or lesson.created_at
            try:
                anchor = datetime.fromisoformat(anchor_raw)
            except ValueError:
                continue  # timestamp corrupto: no se toca, no se rompe el pase
            if anchor.tzinfo is None:
                anchor = anchor.replace(tzinfo=timezone.utc)

            never_recalled = lesson.recall_count == 0
            if never_recalled and anchor > stale_cutoff:
                continue  # grace floor: demasiado joven para juzgarla

            if anchor <= archive_cutoff and lesson.state != "archived":
                self._set_state(lesson, "archived")
                counts["archived"] += 1
            elif anchor <= stale_cutoff and lesson.state == "active":
                self._set_state(lesson, "stale")
                counts["marked_stale"] += 1
            elif anchor > stale_cutoff and lesson.state == "stale":
                self._set_state(lesson, "active")
                counts["reactivated"] += 1

        return counts

    def _set_state(self, lesson: Lesson, state: str) -> None:
        updated = replace(lesson, state=state)
        file = self._path / f"{updated.id}.json"
        file.write_text(
            json.dumps(updated.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def stats(self) -> dict[str, Any]:
        """Conteo de lecciones: total y por procedencia."""
        lessons = self.all()
        by_provenance: dict[str, int] = {}
        for lesson in lessons:
            key = lesson.provenance.value
            by_provenance[key] = by_provenance.get(key, 0) + 1
        return {"total": len(lessons), "by_provenance": by_provenance}


class LessonPromoter:
    """Puentes productores → LessonStore. Cada uno construye la Evidence con
    `LessonVerifier` y solo persiste si PASS (la ley vive en `LessonStore.add`,
    pero promover devuelve None en vez de lanzar para no romper el lazo)."""

    def __init__(
        self,
        store: LessonStore,
        *,
        verifier: LessonVerifier | None = None,
        error_registry: ErrorRegistry | None = None,
    ) -> None:
        self._store = store
        self._verifier = verifier or LessonVerifier()
        # Capa 4 backlog t1-error-registry-lesson-promotion: opcional para no
        # romper a los llamadores existentes que no la pasan (lesson_runner,
        # deliberation_council, seed_lessons) — sin ella, promote_failure
        # sigue funcionando pero no cierra el back-link en ErrorRegistry.
        self._error_registry = error_registry

    def promote_failure(
        self,
        *,
        failure_id: str,
        title: str,
        detection_heuristic: str,
        avoid_pattern: str,
        regression_test_path: str,
        prove_it: ProveItResult,
        tags: tuple[str, ...] = (),
    ) -> Lesson | None:
        """Promociona un FailureEntry blando a Lesson dura. Sin prove-it
        rojo-antes/verde-ahora, devuelve None: no hay lección. Con
        error_registry cableado, una promoción exitosa marca la entrada de
        ErrorRegistry (buscada por `failure_id`) con `promoted_to_lesson_id`
        — el lazo de trazabilidad fallo-blando -> lección-dura."""
        evidence = self._verifier.verify_internal(prove_it)
        if evidence.verdict is not Verdict.PASS:
            return None
        lesson = Lesson(
            id=f"lesson-{uuid.uuid4().hex[:12]}",
            title=title,
            provenance=LessonProvenance.INTERNAL_FAILURE,
            detection_heuristic=detection_heuristic,
            avoid_pattern=avoid_pattern,
            evidence=evidence.to_dict(),
            regression_test_path=regression_test_path,
            source_refs=(f"failure:{failure_id}", f"fix:{prove_it.fix_commit}"),
            tags=tags,
        )
        lesson = self._store.add(lesson)
        if self._error_registry is not None:
            self._error_registry.mark_promoted(failure_id, lesson.id)
        return lesson

    def ingest_external(
        self,
        *,
        title: str,
        detection_heuristic: str,
        avoid_pattern: str,
        source_refs: tuple[str, ...],
        corroborated: bool,
        reason: str = "",
        tags: tuple[str, ...] = (),
    ) -> Lesson | None:
        """Ingesta una lección de fuente externa (paper/foro/release). Sin
        corroboración del gate fail-closed, devuelve None."""
        evidence = self._verifier.verify_external(corroborated=corroborated, reason=reason)
        if evidence.verdict is not Verdict.PASS:
            return None
        lesson = Lesson(
            id=f"lesson-{uuid.uuid4().hex[:12]}",
            title=title,
            provenance=LessonProvenance.EXTERNAL_SOURCE,
            detection_heuristic=detection_heuristic,
            avoid_pattern=avoid_pattern,
            evidence=evidence.to_dict(),
            source_refs=source_refs,
            tags=tags,
        )
        return self._store.add(lesson)
