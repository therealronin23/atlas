"""Read-only comparison of incremental review evidence with an accepted base.

Exact opaque ``dedupe_key`` equality is the only correlation this module
performs.  It deliberately does not manufacture a cross-revision heuristic,
write a finding journal, or infer that a missing later observation resolves a
prior finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from atlas.core.verify import Verdict
from atlas.engineering.baselines import BaselineFindingState, IncrementalReviewSelection
from atlas.engineering.findings import EngineeringFinding
from atlas.engineering.review import EngineeringReviewReport


class IncrementalFindingRelationStatus(str, Enum):
    """The observational relationship of a finding to the accepted base."""

    NEW = "NEW"
    REOBSERVED = "REOBSERVED"
    NOT_REOBSERVED = "NOT_REOBSERVED"


@dataclass(frozen=True)
class IncrementalFindingRelation:
    """One exact-key comparison with no lifecycle implication."""

    status: IncrementalFindingRelationStatus
    dedupe_key: str
    prior: BaselineFindingState | None
    current: EngineeringFinding | None


@dataclass(frozen=True)
class IncrementalFindingNormalization:
    """A deterministic, read-only comparison for one completed review."""

    selection: IncrementalReviewSelection
    review_verdict: Verdict
    relations: tuple[IncrementalFindingRelation, ...]


class EngineeringIncrementalFindingNormalizer:
    """Compare a report with a selected accepted baseline conservatively.

    A caller still owns authorization for every lifecycle transition.  In
    particular, ``NOT_REOBSERVED`` only says that this bounded review did not
    emit an exact matching key; it is never a synonym for ``RESOLVED``.
    """

    def normalize(
        self,
        *,
        report: EngineeringReviewReport,
        selection: IncrementalReviewSelection,
    ) -> IncrementalFindingNormalization:
        self._validate_prior(selection.prior_finding_state)
        current = self._current_by_key(report)
        prior = {state.dedupe_key: state for state in selection.prior_finding_state}
        relations: list[IncrementalFindingRelation] = []

        for dedupe_key in sorted(current):
            finding = current[dedupe_key]
            prior_state = prior.pop(dedupe_key, None)
            relations.append(
                IncrementalFindingRelation(
                    status=(
                        IncrementalFindingRelationStatus.REOBSERVED
                        if prior_state is not None
                        else IncrementalFindingRelationStatus.NEW
                    ),
                    dedupe_key=dedupe_key,
                    prior=prior_state,
                    current=finding,
                )
            )
        for dedupe_key in sorted(prior):
            relations.append(
                IncrementalFindingRelation(
                    status=IncrementalFindingRelationStatus.NOT_REOBSERVED,
                    dedupe_key=dedupe_key,
                    prior=prior[dedupe_key],
                    current=None,
                )
            )
        return IncrementalFindingNormalization(
            selection=selection,
            review_verdict=report.verdict,
            relations=tuple(relations),
        )

    @staticmethod
    def _validate_prior(states: tuple[BaselineFindingState, ...]) -> None:
        keys = [state.dedupe_key for state in states]
        if len(keys) != len(set(keys)):
            raise ValueError("accepted baseline contains duplicate finding dedupe_key")

    @staticmethod
    def _current_by_key(report: EngineeringReviewReport) -> dict[str, EngineeringFinding]:
        request = report.request
        current: dict[str, EngineeringFinding] = {}
        for finding in report.findings:
            if (
                finding.repository != request.repository
                or finding.base_revision != request.base_revision
                or finding.candidate_revision != request.candidate_revision
            ):
                raise ValueError("current finding is outside review revision context")
            # ``EngineeringFindingStore.record()`` can intentionally return a
            # previously journaled finding for the same deterministic key.  Its
            # original run/task provenance must remain intact instead of being
            # rewritten to impersonate the current review invocation.
            if finding.dedupe_key in current:
                raise ValueError("duplicate current finding dedupe_key")
            current[finding.dedupe_key] = finding
        return current
