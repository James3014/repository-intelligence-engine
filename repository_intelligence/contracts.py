"""Repository Intelligence Core V1 Contracts.

Pure, immutable advisory contracts for repository intelligence.
PR intelligence is bounded by PR_INTELLIGENCE_ONLY; CI evidence is bounded by CI_EVIDENCE_ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from .models import Disposition

CLAIM_CEILING = "PR_INTELLIGENCE_ONLY"
CI_EVIDENCE_CLAIM_CEILING = "CI_EVIDENCE_ONLY"
REPOSITORY_FACTS_CLAIM_CEILING = "REPOSITORY_FACTS_ONLY"
REPOSITORY_QUERY_CLAIM_CEILING = "REPOSITORY_QUERY_EVIDENCE_ONLY"


class EvidenceCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class RepositoryIntelligencePolicyV1:
    """Consumer-injected policy for generic repository intelligence."""

    protected_path_patterns: tuple[str, ...] = ()
    stale_labels: tuple[str, ...] = ("long-lived", "stale-long-lived")

    def __post_init__(self) -> None:
        if not isinstance(self.protected_path_patterns, tuple):
            object.__setattr__(self, "protected_path_patterns", tuple(self.protected_path_patterns))
        if not isinstance(self.stale_labels, tuple):
            object.__setattr__(self, "stale_labels", tuple(self.stale_labels))


TERMINAL_FAILURE_STATUSES: frozenset[str] = frozenset({
    "failure",
    "failed",
    "error",
    "cancelled",
    "timed_out",
    "action_required",
})

SUPPORTED_TERMINAL_FAILURES: frozenset[str] = TERMINAL_FAILURE_STATUSES | frozenset({"red"})


def is_terminal_failure_status(status: Any) -> bool:
    """True for canonical terminal failure statuses and supported aliases like 'red'."""
    if not isinstance(status, str):
        return False
    return status.strip().lower() in SUPPORTED_TERMINAL_FAILURES



@dataclass(frozen=True)
class RevisionIdentity:
    """Deterministic repository revision identity with stale evidence detection."""

    repository: str
    pr_number: int
    head_sha: str
    base_sha: str
    current_main_sha: str
    declared_base_sha: str | None = None
    declared_head_sha: str | None = None
    declared_main_sha: str | None = None
    stale_base: bool = False
    stale_declared_base: bool = False
    stale_declared_head: bool = False
    stale_declared_main: bool = False
    stale_evidence: bool = False
    evidence_gaps: tuple[str, ...] = ()
    is_valid: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_gaps, tuple):
            object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    @property
    def review_identity(self) -> tuple[str, int, str, str, str]:
        return (
            self.repository,
            self.pr_number,
            self.head_sha,
            self.base_sha,
            self.current_main_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "pr_number": self.pr_number,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "current_main_sha": self.current_main_sha,
            "declared_base_sha": self.declared_base_sha,
            "declared_head_sha": self.declared_head_sha,
            "declared_main_sha": self.declared_main_sha,
            "stale_base": self.stale_base,
            "stale_declared_base": self.stale_declared_base,
            "stale_declared_head": self.stale_declared_head,
            "stale_declared_main": self.stale_declared_main,
            "stale_evidence": self.stale_evidence,
            "review_identity": list(self.review_identity),
            "evidence_gaps": list(self.evidence_gaps),
            "is_valid": self.is_valid,
        }


@dataclass(frozen=True)
class ReadinessClassification:
    """Immutable advisory projection of existing reviewer classifier semantics."""

    identity: RevisionIdentity
    disposition: Disposition
    findings: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    risk: str = "MED"
    overlaps: Mapping[int, tuple[str, ...]] = field(default_factory=lambda: MappingProxyType({}))
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.COMPLETE
    evidence_gaps: tuple[str, ...] = ()
    claim_ceiling: str = CLAIM_CEILING

    def __post_init__(self) -> None:
        if isinstance(self.overlaps, MappingProxyType):
            frozen = MappingProxyType({k: tuple(v) for k, v in self.overlaps.items()})
        elif isinstance(self.overlaps, Mapping):
            frozen = MappingProxyType({k: tuple(v) for k, v in self.overlaps.items()})
        else:
            frozen = MappingProxyType({})
        object.__setattr__(self, "overlaps", frozen)
        if not isinstance(self.findings, tuple):
            object.__setattr__(self, "findings", tuple(self.findings))
        if not isinstance(self.reasons, tuple):
            object.__setattr__(self, "reasons", tuple(self.reasons))
        if not isinstance(self.evidence_gaps, tuple):
            object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    @property
    def is_review_ready(self) -> bool:
        return (
            self.identity.is_valid
            and self.disposition == Disposition.REVIEW_READY
            and self.evidence_completeness != EvidenceCompleteness.INCOMPLETE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "repository": self.identity.repository,
            "pr_number": self.identity.pr_number,
            "disposition": (
                self.disposition.value
                if hasattr(self.disposition, "value")
                else str(self.disposition)
            ),
            "findings": list(self.findings),
            "reasons": list(self.reasons),
            "risk": self.risk,
            "overlaps": {k: list(v) for k, v in sorted(self.overlaps.items())},
            "is_review_ready": self.is_review_ready,
            "evidence_completeness": self.evidence_completeness.value,
            "evidence_gaps": list(self.evidence_gaps),
            "claim_ceiling": self.claim_ceiling,
        }


@dataclass(frozen=True)
class CrossPROverlapResult:
    """Deterministic immutable projection of cross-PR overlap semantics."""

    classifications: tuple[ReadinessClassification, ...]
    overlap_pairs: tuple[tuple[int, int, tuple[str, ...]], ...] = ()
    claim_ceiling: str = CLAIM_CEILING

    def __post_init__(self) -> None:
        if not isinstance(self.classifications, tuple):
            object.__setattr__(self, "classifications", tuple(self.classifications))
        if not isinstance(self.overlap_pairs, tuple):
            object.__setattr__(self, "overlap_pairs", tuple(self.overlap_pairs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "classifications": [c.to_dict() for c in self.classifications],
            "overlap_pairs": [
                {"pr_a": a, "pr_b": b, "shared_paths": list(paths)}
                for a, b, paths in self.overlap_pairs
            ],
            "claim_ceiling": self.claim_ceiling,
        }


@dataclass(frozen=True)
class NormalizedCheckEvidence:
    """Deterministic generic check observation evidence record."""

    name: str
    status: str
    expected_failure: bool = False
    is_unexpected: bool = False
    check_run_id: int | None = None
    run_id: int | None = None
    external_id: str | None = None
    details_url: str | None = None
    html_url: str | None = None
    node_id: str | None = None
    workflow_name: str | None = None
    head_sha: str | None = None
    check_suite_id: int | None = None
    started_at: str | None = None
    completed_at: str | None = None
    artifact_identity: str | None = None
    annotation_count: int | None = None
    app_slug: str | None = None
    job_identity: str | None = None
    log_sha256: str | None = None
    log_truncated: bool | None = None
    artifact_sha256: str | None = None
    artifact_truncated: bool | None = None
    run_attempt: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "expected_failure": self.expected_failure,
            "is_unexpected": self.is_unexpected,
        }
        for attr in (
            "check_run_id",
            "run_id",
            "external_id",
            "details_url",
            "html_url",
            "node_id",
            "workflow_name",
            "head_sha",
            "check_suite_id",
            "started_at",
            "completed_at",
            "artifact_identity",
            "annotation_count",
            "app_slug",
            "job_identity",
            "log_sha256",
            "log_truncated",
            "artifact_sha256",
            "artifact_truncated",
            "run_attempt",
        ):
            val = getattr(self, attr)
            if val is not None:
                d[attr] = val
        return d


@dataclass(frozen=True)
class CIFailureFingerprint:
    """Hash-bound generic repository-intelligence CI failure evidence."""

    identity: RevisionIdentity
    fingerprint: str
    has_unexpected_failures: bool
    unexpected_failures: tuple[NormalizedCheckEvidence, ...]
    expected_failures: tuple[NormalizedCheckEvidence, ...]
    total_checks_count: int
    unexpected_count: int
    expected_count: int
    terminal_failure_count: int
    evidence_gaps: tuple[str, ...]
    is_complete: bool
    evidence_completeness: EvidenceCompleteness
    content_sha256: str
    expected_check_run_id: int | None = None
    expected_run_id: int | None = None
    expected_job_identity: str | None = None
    expected_artifact_identity: str | None = None
    schema: str = "reviewer.ci_failure_evidence.v1"
    claim_ceiling: str = CI_EVIDENCE_CLAIM_CEILING

    def __post_init__(self) -> None:
        if not isinstance(self.unexpected_failures, tuple):
            object.__setattr__(self, "unexpected_failures", tuple(self.unexpected_failures))
        if not isinstance(self.expected_failures, tuple):
            object.__setattr__(self, "expected_failures", tuple(self.expected_failures))
        if not isinstance(self.evidence_gaps, tuple):
            object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "fingerprint": self.fingerprint,
            "has_unexpected_failures": self.has_unexpected_failures,
            "unexpected_failures": [c.to_dict() for c in self.unexpected_failures],
            "expected_failures": [c.to_dict() for c in self.expected_failures],
            "total_checks_count": self.total_checks_count,
            "unexpected_count": self.unexpected_count,
            "expected_count": self.expected_count,
            "terminal_failure_count": self.terminal_failure_count,
            "expected_check_run_id": self.expected_check_run_id,
            "expected_run_id": self.expected_run_id,
            "expected_job_identity": self.expected_job_identity,
            "expected_artifact_identity": self.expected_artifact_identity,
"evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "is_complete": self.is_complete,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


class RepositoryQueryResolution(str, Enum):
    """Deterministic advisory retrieval-resolution states.

    These are binding-less advisory states for candidate narrowing only.
    They never select a worker or grant routing/acceptance authority.
    """

    EXACT_RESOLUTION = "EXACT_RESOLUTION"
    BOUNDED_CANDIDATES = "BOUNDED_CANDIDATES"
    AMBIGUOUS_RETRIEVAL = "AMBIGUOUS_RETRIEVAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CandidateMatchClass(str, Enum):
    """Advisory match classes attached to a candidate by exactly one retriever."""

    EXACT = "EXACT"
    LEXICAL = "LEXICAL"
    GRAPH = "GRAPH"
    VECTOR = "VECTOR"
    OTHER = "OTHER"


@dataclass(frozen=True)
class RetrieverIdentityV1:
    """Exact identity of one retrieval source binding a query to a revision."""

    retriever_id: str
    index_id: str
    index_revision: str
    backend_id: str = ""
    retriever_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "retriever_id": self.retriever_id,
            "index_id": self.index_id,
            "index_revision": self.index_revision,
        }
        if self.backend_id:
            d["backend_id"] = self.backend_id
        if self.retriever_version:
            d["retriever_version"] = self.retriever_version
        return d


@dataclass(frozen=True)
class RankedCandidateV1:
    """One candidate as returned by exactly one retriever source."""

    candidate_ref: str
    source_rank: int
    source_score: float | None = None
    evidence_ref: str = ""
    match_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "candidate_ref": self.candidate_ref,
            "source_rank": self.source_rank,
        }
        if self.source_score is not None:
            d["source_score"] = self.source_score
        if self.evidence_ref:
            d["evidence_ref"] = self.evidence_ref
        if self.match_class:
            d["match_class"] = self.match_class
        return d


@dataclass(frozen=True)
class RetrieverRunV1:
    """Exactly one completed (or incomplete) retrieval run bound to a revision."""

    identity: RetrieverIdentityV1
    ranked_candidates: tuple[RankedCandidateV1, ...] = ()
    complete: bool = False
    coverage_note: str = ""
    errors: tuple[str, ...] = ()
    source_hits: int = 0
    latency_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ranked_candidates", tuple(self.ranked_candidates))
        object.__setattr__(self, "errors", tuple(self.errors))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "identity": self.identity.to_dict(),
            "ranked_candidates": [c.to_dict() for c in self.ranked_candidates],
            "complete": self.complete,
            "source_hits": self.source_hits,
        }
        if self.coverage_note:
            d["coverage_note"] = self.coverage_note
        if self.errors:
            d["errors"] = list(self.errors)
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        return d


@dataclass(frozen=True)
class FusedCandidateV1:
    """One fused candidate preserving per-source provenance."""

    candidate_ref: str
    fused_rank: int
    fused_score: float
    exact_match: bool = False
    per_source_refs: tuple[RankedCandidateV1, ...] = ()
    matched_sources: tuple[str, ...] = ()
    matched_source_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "per_source_refs", tuple(self.per_source_refs))
        object.__setattr__(self, "matched_sources", tuple(self.matched_sources))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_ref": self.candidate_ref,
            "fused_rank": self.fused_rank,
            "fused_score": self.fused_score,
            "exact_match": self.exact_match,
            "per_source_refs": [r.to_dict() for r in self.per_source_refs],
            "matched_sources": list(self.matched_sources),
            "matched_source_count": self.matched_source_count,
        }


@dataclass(frozen=True)
class RepositoryQueryEvidenceReportV1:
    """Hash-bound revision-bound advisory repository-query evidence.

    The report narrows candidates before any semantic review. It never
    invokes a model, selects a worker, or grants routing/acceptance authority.
    """

    identity: RevisionIdentity
    query_id: str
    query_digest: str
    index_identity: RetrieverIdentityV1 | None
    source_evidence: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    retrievers: tuple[RetrieverRunV1, ...] = ()
    fused_candidates: tuple[FusedCandidateV1, ...] = ()
    resolution: RepositoryQueryResolution = RepositoryQueryResolution.INSUFFICIENT_EVIDENCE
    reason_codes: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.INCOMPLETE
    is_complete: bool = False
    required_candidates: int = 8
    distinct_candidate_count: int = 0
    exact_match_count: int = 0
    semantic_review_needed: bool = False
    content_sha256: str = ""
    schema: str = "reviewer.repository_query_evidence.v1"
    claim_ceiling: str = REPOSITORY_QUERY_CLAIM_CEILING

    def __post_init__(self) -> None:
        if isinstance(self.source_evidence, Mapping):
            object.__setattr__(self, "source_evidence", MappingProxyType(dict(self.source_evidence)))
        else:
            object.__setattr__(self, "source_evidence", MappingProxyType({}))
        object.__setattr__(self, "retrievers", tuple(self.retrievers))
        object.__setattr__(self, "fused_candidates", tuple(self.fused_candidates))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "query_id": self.query_id,
            "query_digest": self.query_digest,
            "index_identity": (
                self.index_identity.to_dict() if self.index_identity is not None else None
            ),
            "source_evidence": dict(self.source_evidence),
            "retrievers": [r.to_dict() for r in self.retrievers],
            "fused_candidates": [c.to_dict() for c in self.fused_candidates],
            "resolution": self.resolution.value,
            "reason_codes": list(self.reason_codes),
            "evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "is_complete": self.is_complete,
            "required_candidates": self.required_candidates,
            "distinct_candidate_count": self.distinct_candidate_count,
            "exact_match_count": self.exact_match_count,
            "semantic_review_needed": self.semantic_review_needed,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class ChangeImpactReportV1:
    """Hash-bound language-neutral downstream change-impact evidence."""

    identity: RevisionIdentity
    covered_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    dependency_edges: tuple[tuple[str, str], ...] = ()
    observed_symbols: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    direct_impacted_files: tuple[str, ...] = ()
    transitive_impacted_files: tuple[str, ...] = ()
    all_impacted_files: tuple[str, ...] = ()
    graph_complete: bool = False
    graph_errors: tuple[str, ...] = ()
    edge_count: int = 0
    graph_sha256: str = ""
    evidence_gaps: tuple[str, ...] = ()
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.INCOMPLETE
    is_complete: bool = False
    content_sha256: str = ""
    schema: str = "reviewer.change_impact.v1"
    claim_ceiling: str = CLAIM_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(self, "covered_files", tuple(self.covered_files))
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "dependency_edges", tuple(tuple(edge) for edge in self.dependency_edges))
        if isinstance(self.observed_symbols, Mapping):
            frozen = MappingProxyType({
                str(path): tuple(symbols)
                for path, symbols in self.observed_symbols.items()
            })
        else:
            frozen = MappingProxyType({})
        object.__setattr__(self, "observed_symbols", frozen)
        object.__setattr__(self, "direct_impacted_files", tuple(self.direct_impacted_files))
        object.__setattr__(self, "transitive_impacted_files", tuple(self.transitive_impacted_files))
        object.__setattr__(self, "all_impacted_files", tuple(self.all_impacted_files))
        object.__setattr__(self, "graph_errors", tuple(self.graph_errors))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    @property
    def direct_impacted_count(self) -> int:
        return len(self.direct_impacted_files)

    @property
    def transitive_impacted_count(self) -> int:
        return len(self.transitive_impacted_files)

    @property
    def total_impacted_count(self) -> int:
        return len(self.all_impacted_files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "covered_files": list(self.covered_files),
            "changed_files": list(self.changed_files),
            "dependency_edges": [
                {"consumer": consumer, "dependency": dependency}
                for consumer, dependency in self.dependency_edges
            ],
            "observed_symbols": {
                path: list(symbols)
                for path, symbols in sorted(self.observed_symbols.items())
            },
            "direct_impacted_files": list(self.direct_impacted_files),
            "transitive_impacted_files": list(self.transitive_impacted_files),
            "all_impacted_files": list(self.all_impacted_files),
            "direct_impacted_count": self.direct_impacted_count,
            "transitive_impacted_count": self.transitive_impacted_count,
            "total_impacted_count": self.total_impacted_count,
            "graph_complete": self.graph_complete,
            "graph_errors": list(self.graph_errors),
            "edge_count": self.edge_count,
            "graph_sha256": self.graph_sha256,
            "evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "is_complete": self.is_complete,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


class CIFailureTriageStatus(str, Enum):
    NO_TERMINAL_FAILURE = "NO_TERMINAL_FAILURE"
    EXPECTED_FAILURE_ONLY = "EXPECTED_FAILURE_ONLY"
    UNEXPECTED_FAILURE_OBSERVED = "UNEXPECTED_FAILURE_OBSERVED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class CIFailureIntelligenceReportV1:
    """Deterministic CI-failure triage bounded to evidence, never root cause."""

    identity: RevisionIdentity
    failure_evidence: CIFailureFingerprint
    status: CIFailureTriageStatus
    diagnosis_eligible: bool
    reason_codes: tuple[str, ...] = ()
    failed_check_names: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.INCOMPLETE
    content_sha256: str = ""
    schema: str = "reviewer.ci_failure_intelligence.v1"
    claim_ceiling: str = CI_EVIDENCE_CLAIM_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "failed_check_names", tuple(self.failed_check_names))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "failure_evidence": self.failure_evidence.to_dict(),
            "status": self.status.value,
            "diagnosis_eligible": self.diagnosis_eligible,
            "reason_codes": list(self.reason_codes),
            "failed_check_names": list(self.failed_check_names),
            "evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


class ExternalIntelligenceDecision(str, Enum):
    READY = "READY"
    NO_ACTION = "NO_ACTION"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ExternalIntelligenceAutomationEnvelopeV1:
    """Pure automation plan. It grants no dispatch, write, or merge authority."""

    identity: RevisionIdentity
    decision: ExternalIntelligenceDecision
    action_kind: str
    idempotency_key: str
    evidence_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()
    content_sha256: str = ""
    schema: str = "reviewer.external_intelligence_automation.v1"
    claim_ceiling: str = "AUTOMATION_ADVISORY_ONLY"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "decision": self.decision.value,
            "action_kind": self.action_kind,
            "idempotency_key": self.idempotency_key,
            "evidence_refs": list(self.evidence_refs),
            "reason_codes": list(self.reason_codes),
            "evidence_gaps": list(self.evidence_gaps),
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class RepositoryIntelligenceReportV1:
    """Canonical hash-bound V1 repository intelligence report."""

    repository: str
    current_main_sha: str
    observed_at: str
    items: tuple[ReadinessClassification, ...]
    evidence_completeness: EvidenceCompleteness
    evidence_gaps: tuple[str, ...]
    content_sha256: str
    schema: str = "reviewer.repository_intelligence.v1"
    claim_ceiling: str = CLAIM_CEILING

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        if not isinstance(self.evidence_gaps, tuple):
            object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "current_main_sha": self.current_main_sha,
            "observed_at": self.observed_at,
            "items": [item.to_dict() for item in self.items],
            "evidence_completeness": self.evidence_completeness.value,
            "evidence_gaps": list(self.evidence_gaps),
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


class RepositoryFactKind(str, Enum):
    """Deterministic repository fact kinds emitted by structured facts.

    Naming follows the RIE convention of explicit, machine-readable kinds.
    Each kind is advisory repository evidence, never a review verdict.
    """

    EMPTY_EXCEPTION_HANDLER = "EMPTY_EXCEPTION_HANDLER"
    BROAD_EXCEPTION_HANDLER = "BROAD_EXCEPTION_HANDLER"
    SUBPROCESS_CALL = "SUBPROCESS_CALL"
    NETWORK_ENDPOINT_ADDED = "NETWORK_ENDPOINT_ADDED"
    VISIBLE_AUTH_CHECK = "VISIBLE_AUTH_CHECK"
    RELATED_TEST_CHANGED = "RELATED_TEST_CHANGED"
    SILENT_RETRY_PATTERN = "SILENT_RETRY_PATTERN"
    HARDCODED_LOCALHOST = "HARDCODED_LOCALHOST"


class RepositoryFactStatus(str, Enum):
    """Status of one structured repository fact.

    - PROVEN: deterministic evidence exists at a bound revision.
    - NOT_OBSERVED: deterministic detectors covered the requested scope and
      found no evidence for this fact kind.
    - UNKNOWN: the fact cannot be proven deterministically here (for example,
      no detector exists for the language/kind); a scope limitation, not a
      negative finding.
    - UNRESOLVED: evidence is stale, incomplete, or invalid, so no status may
      be trusted; fails closed.
    """

    PROVEN = "PROVEN"
    NOT_OBSERVED = "NOT_OBSERVED"
    UNKNOWN = "UNKNOWN"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class RepositoryFactEvidenceV1:
    """One normalized source or diff-location evidence reference for a fact.

    ``line`` of 0 denotes file-level evidence (no specific line), used only by
    diff/path-derived facts such as ``RELATED_TEST_CHANGED``.
    """

    file_path: str
    line: int
    column: int
    evidence_ref: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True)
class RepositoryFactV1:
    """One revision-bound structured fact for a single fact kind."""

    fact_kind: RepositoryFactKind
    status: RepositoryFactStatus
    head_sha: str
    language: str
    evidence: tuple[RepositoryFactEvidenceV1, ...] = ()
    reason_codes: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "limitations", tuple(self.limitations))

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_kind": self.fact_kind.value,
            "status": self.status.value,
            "head_sha": self.head_sha,
            "language": self.language,
            "evidence": [item.to_dict() for item in self.evidence],
            "reason_codes": list(self.reason_codes),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StructuredFactsReportV1:
    """Hash-bound, revision-bound structured repository facts report.

    The report is advisory repository evidence. It grants no review approval,
    merge, release, dispatch, or Candidate-acceptance authority.
    """

    identity: RevisionIdentity
    language: str
    detector_version: str
    covered_files: tuple[str, ...]
    changed_files: tuple[str, ...]
    requested_facts: tuple[str, ...]
    detector_coverage: Mapping[str, bool] = field(
        default_factory=lambda: MappingProxyType({})
    )
    observations: tuple[Mapping[str, Any], ...] = ()
    collection_complete: bool = False
    collection_errors: tuple[str, ...] = ()
    facts: tuple[RepositoryFactV1, ...] = ()
    limitations: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    evidence_gaps: tuple[str, ...] = ()
    evidence_completeness: EvidenceCompleteness = EvidenceCompleteness.INCOMPLETE
    is_complete: bool = False
    content_sha256: str = ""
    schema: str = "reviewer.structured_facts.v1"
    claim_ceiling: str = REPOSITORY_FACTS_CLAIM_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(self, "covered_files", tuple(self.covered_files))
        object.__setattr__(self, "changed_files", tuple(self.changed_files))
        object.__setattr__(self, "requested_facts", tuple(self.requested_facts))
        if isinstance(self.detector_coverage, Mapping):
            frozen_cov = MappingProxyType({
                str(k): bool(v) for k, v in self.detector_coverage.items()
            })
        else:
            frozen_cov = MappingProxyType({})
        object.__setattr__(self, "detector_coverage", frozen_cov)
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "collection_errors", tuple(self.collection_errors))
        object.__setattr__(self, "facts", tuple(self.facts))
        if isinstance(self.limitations, Mapping):
            frozen_lims = MappingProxyType({
                str(k): tuple(v) for k, v in self.limitations.items()
            })
        else:
            frozen_lims = MappingProxyType({})
        object.__setattr__(self, "limitations", frozen_lims)
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    @property
    def fact_statuses(self) -> Mapping[str, str]:
        return MappingProxyType({
            fact.fact_kind.value: fact.status.value for fact in self.facts
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "language": self.language,
            "detector_version": self.detector_version,
            "covered_files": list(self.covered_files),
            "changed_files": list(self.changed_files),
            "requested_facts": list(self.requested_facts),
            "detector_coverage": {
                str(k): bool(v) for k, v in sorted(self.detector_coverage.items())
            },
            "observations": [dict(obs) for obs in self.observations],
            "collection_complete": self.collection_complete,
            "collection_errors": list(self.collection_errors),
            "facts": [fact.to_dict() for fact in self.facts],
            "limitations": {
                str(k): list(v)
                for k, v in sorted(self.limitations.items())
            },
            "evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "is_complete": self.is_complete,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }
