"""Repository Intelligence V1.2 Selective Repository Retrieval Evidence.

Deterministic, revision-bound, transport-neutral advisory evidence that narrows
repository candidates for a query before any semantic review. The engine never
invokes an LLM, parses source code, or owns a language-specific retriever. It
consumes normalized per-retriever ranked candidate lists (produced by
adapter-owned retrievers) and emits hash-bound evidence with deterministic
reciprocal-rank fusion.

Retrieval evidence is advisory and binding-less. A resolved query never grants
routing, worker selection, merge, release, dispatch, or Candidate-acceptance
authority. Empty retrieval is never proof of absence.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .contracts import (
    REPOSITORY_QUERY_CLAIM_CEILING,
    CandidateMatchClass,
    EvidenceCompleteness,
    FusedCandidateV1,
    RankedCandidateV1,
    RepositoryQueryEvidenceReportV1,
    RepositoryQueryResolution,
    RetrieverIdentityV1,
    RetrieverRunV1,
    RevisionIdentity,
)
from .core import revision_identity

RETRIEVAL_SCHEMA = "reviewer.repository_query_evidence.v1"
FUSION_K = 60

DEFAULT_REQUIRED_CANDIDATES = 8

EXACT_MATCH_CLASSES = {CandidateMatchClass.EXACT.value}

_REASON_INVALID_REVISION_IDENTITY = "INVALID_REVISION_IDENTITY"
_REASON_STALE_REVISION_EVIDENCE = "STALE_REVISION_EVIDENCE"
_REASON_QUERY_ID_MISSING = "QUERY_ID_MISSING"
_REASON_QUERY_DIGEST_MISSING = "QUERY_DIGEST_MISSING"
_REASON_INDEX_IDENTITY_MISSING = "INDEX_IDENTITY_MISSING"
_REASON_RETRIEVER_INDEX_MISMATCH = "RETRIEVER_INDEX_MISMATCH"
_REASON_RETRIEVER_REVISION_MISMATCH = "RETRIEVER_REVISION_MISMATCH"
_REASON_RETRIEVER_ID_COLLISION = "RETRIEVER_ID_COLLISION"
_REASON_NO_RETRIEVERS = "NO_RETRIEVERS"
_REASON_RETRIEVER_INCOMPLETE = "RETRIEVER_INCOMPLETE"
_REASON_RETRIEVER_ERROR = "RETRIEVER_ERROR"
_REASON_EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
_REASON_CANDIDATE_DUPLICATE = "CANDIDATE_DUPLICATE"
_REASON_CANDIDATE_RANK_INVALID = "CANDIDATE_RANK_INVALID"
_REASON_CANDIDATE_REF_INVALID = "CANDIDATE_REF_INVALID"
_REASON_EMPTY_RETRIEVAL_NOT_ABSENCE = "EMPTY_RETRIEVAL_NOT_ABSENCE"
_REASON_AMBIGUOUS_CANDIDATES = "AMBIGUOUS_CANDIDATES"
_REASON_MULTIPLE_EXACT_MATCHES = "MULTIPLE_EXACT_MATCHES"
_REASON_REQUIRED_CANDIDATES_INVALID = "REQUIRED_CANDIDATES_INVALID"

_RESOLUTION_REVIEW_NEEDED = {
    RepositoryQueryResolution.AMBIGUOUS_RETRIEVAL,
    RepositoryQueryResolution.INSUFFICIENT_EVIDENCE,
}


def _canonical_source_evidence(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact JSON-like neutral inputs used for semantic recomputation.

    The verifier must be able to rerun every deterministic derivation from
    embedded evidence instead of trusting caller-editable evidence_gaps.
    """
    try:
        return json.loads(json.dumps(data, sort_keys=True, separators=(",", ":")))
    except (TypeError, ValueError) as exc:
        raise TypeError("repository query input must be JSON-serializable") from exc


def _content_hash(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_path(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, "path must be a non-empty string"
    if "\x00" in value:
        return None, "path contains NUL"
    if "\\" in value:
        return None, f"path must use repository POSIX separators: {value!r}"
    if value.startswith("/"):
        return None, f"absolute path rejected: {value!r}"
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, f"path is not normalized or contains traversal: {value!r}"
    normalized = posixpath.normpath(value)
    if normalized != value or normalized.startswith("../") or normalized == "..":
        return None, f"path is not a safe normalized repository path: {value!r}"
    return value, None


def _normalize_reason_codes(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    seen: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item.strip() not in seen:
            seen.append(item.strip())
    return tuple(seen)


def _normalize_completeness(raw: Any) -> tuple[EvidenceCompleteness, bool]:
    if not isinstance(raw, EvidenceCompleteness):
        for possible in EvidenceCompleteness:
            if possible.value == raw:
                return possible, True
        return EvidenceCompleteness.INCOMPLETE, False
    return raw, True


def _norm_match_class(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().upper()
    if normalized in {member.value for member in CandidateMatchClass}:
        return normalized
    return ""


def _normalize_ranked_candidates(
    raw: Any,
    *,
    retriever_id: str,
    problems: list[str],
) -> list[RankedCandidateV1]:
    if not isinstance(raw, (list, tuple)):
        problems.append(f"retriever[{retriever_id}].ranked_candidates must be a list")
        return []
    normalized: list[RankedCandidateV1] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            problems.append(
                f"retriever[{retriever_id}].ranked_candidates[{index}] must be an object"
            )
            continue
        candidate_ref = item.get("candidate_ref")
        if not isinstance(candidate_ref, str) or not candidate_ref.strip():
            problems.append(
                f"retriever[{retriever_id}].ranked_candidates[{index}] candidate_ref "
                "must be a non-empty string"
            )
            continue
        candidate_ref = candidate_ref.strip()
        if candidate_ref in seen:
            problems.append(
                f"retriever[{retriever_id}] duplicate candidate_ref: {candidate_ref}"
            )
            continue
        seen.add(candidate_ref)

        source_rank = item.get("source_rank")
        if isinstance(source_rank, bool) or not isinstance(source_rank, int) or source_rank <= 0:
            problems.append(
                f"retriever[{retriever_id}] candidate[{candidate_ref}] source_rank "
                "must be a position int > 0"
            )
            continue

        source_score = item.get("source_score")
        if source_score is not None and (
            isinstance(source_score, bool) or not isinstance(source_score, (int, float))
        ):
            problems.append(
                f"retriever[{retriever_id}] candidate[{candidate_ref}] source_score "
                "must be numeric or null"
            )
            continue

        evidence_ref = item.get("evidence_ref")
        if evidence_ref is not None and (
            not isinstance(evidence_ref, str) or not evidence_ref.strip()
        ):
            problems.append(
                f"retriever[{retriever_id}] candidate[{candidate_ref}] evidence_ref "
                "must be a non-empty string when provided"
            )
            continue

        match_class = _norm_match_class(item.get("match_class"))
        normalized.append(
            RankedCandidateV1(
                candidate_ref=candidate_ref,
                source_rank=source_rank,
                source_score=(
                    float(source_score) if isinstance(source_score, int) else source_score
                )
                if source_score is not None
                else None,
                evidence_ref=evidence_ref.strip() if isinstance(evidence_ref, str) else "",
                match_class=match_class,
            )
        )
    return normalized


def _normalize_retriever_identity(
    raw: Any,
    *,
    index_identity: RetrieverIdentityV1 | None,
    retriever_index: int,
    problems: list[str],
) -> RetrieverIdentityV1 | None:
    if not isinstance(raw, Mapping):
        problems.append(f"retrievers[{retriever_index}].identity must be an object")
        return None
    retriever_id = raw.get("retriever_id")
    if not isinstance(retriever_id, str) or not retriever_id.strip():
        problems.append(f"retrievers[{retriever_index}].identity.retriever_id invalid")
        return None
    retriever_id = retriever_id.strip()

    index_id = raw.get("index_id")
    if index_id is not None and (not isinstance(index_id, str) or not index_id.strip()):
        problems.append(f"retriever[{retriever_id}].identity.index_id invalid")
        return None
    index_revision = raw.get("index_revision")
    if index_revision is not None and (
        not isinstance(index_revision, str) or not index_revision.strip()
    ):
        problems.append(f"retriever[{retriever_id}].identity.index_revision invalid")
        return None
    backend_id = raw.get("backend_id")
    if backend_id is not None and (not isinstance(backend_id, str) or not backend_id.strip()):
        problems.append(f"retriever[{retriever_id}].identity.backend_id invalid")
        return None
    retriever_version = raw.get("retriever_version")
    if retriever_version is not None and (
        not isinstance(retriever_version, str) or not retriever_version.strip()
    ):
        problems.append(f"retriever[{retriever_id}].identity.retriever_version invalid")
        return None

    if index_identity is None:
        if index_id is None or index_revision is None:
            problems.append(
                f"retriever[{retriever_id}] index_id/index_revision required when "
                "index_identity is not declared"
            )
            return None
        effective_index_id = index_id.strip()
        effective_index_revision = index_revision.strip()
    else:
        effective_index_id = (
            index_id.strip() if index_id is not None else index_identity.index_id
        )
        effective_index_revision = (
            index_revision.strip()
            if index_revision is not None
            else index_identity.index_revision
        )

    return RetrieverIdentityV1(
        retriever_id=retriever_id,
        index_id=effective_index_id,
        index_revision=effective_index_revision,
        backend_id=backend_id.strip() if isinstance(backend_id, str) else "",
        retriever_version=retriever_version.strip()
        if isinstance(retriever_version, str)
        else "",
    )


def _normalize_retrievers(
    data: Mapping[str, Any],
    *,
    index_identity: RetrieverIdentityV1 | None,
    gaps: list[str],
) -> list[RetrieverRunV1]:
    retrievers_raw = data.get("retrievers")
    if retrievers_raw is None:
        gaps.append("retrievers missing")
        if index_identity is None:
            return []
        return [
            RetrieverRunV1(
                identity=index_identity,
                ranked_candidates=(),
                complete=False,
                errors=("retrievers missing",),
            )
        ]
    if not isinstance(retrievers_raw, (list, tuple)):
        gaps.append("retrievers must be a list")
        return []

    problems: list[str] = []
    seen_ids: set[str] = set()
    normalized: list[RetrieverRunV1] = []
    for index, raw in enumerate(retrievers_raw):
        if not isinstance(raw, Mapping):
            problems.append(f"retrievers[{index}] must be an object")
            continue
        identity = _normalize_retriever_identity(
            raw.get("identity"),
            index_identity=index_identity,
            retriever_index=index,
            problems=problems,
        )
        if identity is None:
            continue
        if identity.retriever_id in seen_ids:
            problems.append(f"retriever_id collision: {identity.retriever_id}")
            continue
        seen_ids.add(identity.retriever_id)

        if index_identity is not None:
            if identity.index_id != index_identity.index_id:
                problems.append(
                    f"retriever[{identity.retriever_id}] index_id does not match "
                    "declared index_identity"
                )
                continue
            if identity.index_revision != index_identity.index_revision:
                problems.append(
                    f"retriever[{identity.retriever_id}] index_revision does not match "
                    "declared index_identity"
                )
                continue

        run_problems: list[str] = []
        candidates = _normalize_ranked_candidates(
            raw.get("ranked_candidates"),
            retriever_id=identity.retriever_id,
            problems=run_problems,
        )
        problems.extend(run_problems)

        complete_raw = raw.get("complete", False)
        if not isinstance(complete_raw, bool):
            problems.append(f"retriever[{identity.retriever_id}] complete must be a boolean")
            complete = False
        else:
            complete = complete_raw

        errors = _normalize_reason_codes(raw.get("errors"))
        source_hits_raw = raw.get("source_hits", 0)
        if isinstance(source_hits_raw, bool) or not isinstance(source_hits_raw, int):
            problems.append(f"retriever[{identity.retriever_id}] source_hits must be an int")
            source_hits = 0
        else:
            source_hits = source_hits_raw

        coverage_note = raw.get("coverage_note")
        if coverage_note is not None and (
            not isinstance(coverage_note, str) or not coverage_note.strip()
        ):
            problems.append(f"retriever[{identity.retriever_id}] coverage_note invalid")
            coverage_note = ""
        else:
            coverage_note = coverage_note.strip() if isinstance(coverage_note, str) else ""

        latency_ms = raw.get("latency_ms")
        if latency_ms is None:
            latency = None
        elif isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
            problems.append(f"retriever[{identity.retriever_id}] latency_ms invalid")
            latency = None
        else:
            latency = latency_ms

        normalized.append(
            RetrieverRunV1(
                identity=identity,
                ranked_candidates=tuple(candidates),
                complete=complete,
                coverage_note=coverage_note,
                errors=errors,
                source_hits=source_hits,
                latency_ms=latency,
            )
        )

    gaps.extend(f"retrieval: {problem}" for problem in problems)
    return normalized


def _normalize_index_identity(
    data: Mapping[str, Any],
    *,
    gaps: list[str],
) -> RetrieverIdentityV1 | None:
    raw = data.get("index_identity")
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        gaps.append("index_identity must be an object")
        return None
    index_id = raw.get("index_id")
    if not isinstance(index_id, str) or not index_id.strip():
        gaps.append("index_identity.index_id missing or invalid")
        return None
    index_revision = raw.get("index_revision")
    if not isinstance(index_revision, str) or not index_revision.strip():
        gaps.append("index_identity.index_revision missing or invalid")
        return None
    backend_id = raw.get("backend_id")
    if backend_id is not None and (not isinstance(backend_id, str) or not backend_id.strip()):
        gaps.append("index_identity.backend_id invalid")
    return RetrieverIdentityV1(
        retriever_id="",
        index_id=index_id.strip(),
        index_revision=index_revision.strip(),
        backend_id=backend_id.strip() if isinstance(backend_id, str) else "",
    )


def _normalize_required_candidates(data: Mapping[str, Any], gaps: list[str]) -> int:
    raw = data.get("required_candidates", DEFAULT_REQUIRED_CANDIDATES)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        gaps.append("required_candidates must be a positive int")
        return DEFAULT_REQUIRED_CANDIDATES
    return raw


def _fuse_candidates(
    retrievers: Sequence[RetrieverRunV1],
    *,
    required_candidates: int,
) -> list[FusedCandidateV1]:
    """Deterministic reciprocal-rank fusion (RRF, k=60) over per-retriever ranks.

    Per-source provenance is retained. Candidates with an exact-match source are
    always preserved in the fused set (never dropped by lower-confidence
    retrieval). The result is bounded to ``required_candidates``, deduplicated
    by candidate_ref, and ordered deterministically by (fused_score desc,
    candidate_ref asc). Only the bounded advisory set is emitted.
    """
    source_map: dict[str, list[RankedCandidateV1]] = {}
    source_ids: dict[str, set[str]] = {}
    exact: set[str] = set()
    for run in retrievers:
        retriever_id = run.identity.retriever_id
        for candidate in run.ranked_candidates:
            key = candidate.candidate_ref
            source_map.setdefault(key, []).append(candidate)
            source_ids.setdefault(key, set()).add(retriever_id)
            if candidate.match_class in EXACT_MATCH_CLASSES:
                exact.add(key)

    fused: list[FusedCandidateV1] = []
    for candidate_ref, entries in source_map.items():
        fused_score = sum(1.0 / (FUSION_K + entry.source_rank) for entry in entries)
        per_source_refs = tuple(
            sorted(entries, key=lambda entry: (entry.source_rank, entry.match_class))
        )
        matched_sources = tuple(sorted(source_ids[candidate_ref]))
        fused.append(
            FusedCandidateV1(
                candidate_ref=candidate_ref,
                fused_rank=0,
                fused_score=round(fused_score, 6),
                exact_match=candidate_ref in exact,
                per_source_refs=per_source_refs,
                matched_sources=matched_sources,
                matched_source_count=len(matched_sources),
            )
        )

    fused.sort(key=lambda candidate: (-candidate.fused_score, candidate.candidate_ref))

    bounded: list[FusedCandidateV1] = []
    for candidate in fused:
        if candidate.exact_match or len(bounded) < required_candidates:
            bounded.append(candidate)
    return [
        replace(candidate, fused_rank=index) for index, candidate in enumerate(bounded, start=1)
    ]


def _derive_resolution(
    *,
    identity: RevisionIdentity,
    query_id: str,
    query_digest: str,
    gaps: Sequence[str],
    index_identity: RetrieverIdentityV1 | None,
    retrievers: Sequence[RetrieverRunV1],
    required_candidates: int,
) -> tuple[RepositoryQueryResolution, tuple[str, ...]]:
    """Derive the advisory resolution deterministically from neutral primers.

    Precedence is fail-closed: identity/query/index binding problems first,
    then collection completeness, then empty retrieval and candidate-set shape.
    """
    if not identity.is_valid:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_INVALID_REVISION_IDENTITY,
        )
    if identity.stale_evidence:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_STALE_REVISION_EVIDENCE,
        )
    if not query_id:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (_REASON_QUERY_ID_MISSING,)
    if not query_digest:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_QUERY_DIGEST_MISSING,
        )

    if index_identity is None and retrievers:
        revisions = {run.identity.index_revision for run in retrievers}
        if len(revisions) > 1:
            return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
                _REASON_RETRIEVER_REVISION_MISMATCH,
            )
    if any("index_revision does not match" in gap for gap in gaps):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_RETRIEVER_REVISION_MISMATCH,
        )
    if any("index_id does not match" in gap for gap in gaps):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_RETRIEVER_INDEX_MISMATCH,
        )
    if any("retriever_id collision" in gap for gap in gaps):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_RETRIEVER_ID_COLLISION,
        )
    if not retrievers:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (_REASON_NO_RETRIEVERS,)
    if any("source_rank must be a position int" in gap for gap in gaps):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_CANDIDATE_RANK_INVALID,
        )
    if any("duplicate candidate_ref" in gap for gap in gaps):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_CANDIDATE_DUPLICATE,
        )
    if any(not run.complete for run in retrievers):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_RETRIEVER_INCOMPLETE,
        )
    if any(run.errors for run in retrievers):
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (_REASON_RETRIEVER_ERROR,)
    if gaps:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (_REASON_EVIDENCE_INCOMPLETE,)

    distinct_refs = {
        candidate.candidate_ref for run in retrievers for candidate in run.ranked_candidates
    }
    exact_refs = {
        candidate.candidate_ref
        for run in retrievers
        for candidate in run.ranked_candidates
        if candidate.match_class in EXACT_MATCH_CLASSES
    }
    distinct_count = len(distinct_refs)
    exact_count = len(exact_refs)
    if distinct_count == 0:
        return RepositoryQueryResolution.INSUFFICIENT_EVIDENCE, (
            _REASON_EMPTY_RETRIEVAL_NOT_ABSENCE,
        )
    if exact_count > 1:
        return RepositoryQueryResolution.AMBIGUOUS_RETRIEVAL, (
            _REASON_MULTIPLE_EXACT_MATCHES,
        )
    if exact_count == 1:
        return RepositoryQueryResolution.EXACT_RESOLUTION, ()
    if distinct_count > required_candidates:
        return RepositoryQueryResolution.AMBIGUOUS_RETRIEVAL, (
            _REASON_AMBIGUOUS_CANDIDATES,
        )
    return RepositoryQueryResolution.BOUNDED_CANDIDATES, ()


def _derive_completeness(
    *,
    identity: RevisionIdentity,
    gaps: Sequence[str],
    required_candidates: int,
    resolution: RepositoryQueryResolution,
) -> EvidenceCompleteness:
    incomplete = (
        not identity.is_valid
        or identity.stale_evidence
        or bool(required_candidates <= 0)
    )
    if incomplete:
        return EvidenceCompleteness.INCOMPLETE
    if resolution in {
        RepositoryQueryResolution.EXACT_RESOLUTION,
        RepositoryQueryResolution.BOUNDED_CANDIDATES,
    }:
        return EvidenceCompleteness.COMPLETE
    if not gaps:
        return EvidenceCompleteness.COMPLETE
    return EvidenceCompleteness.INCOMPLETE


def analyze_repository_query(data: Mapping[str, Any]) -> RepositoryQueryEvidenceReportV1:
    """Emit hash-bound, revision-bound advisory repository-query evidence.

    Required input shape::

        {
          "snapshot": {repository/pr_number/base_sha/head_sha/current_main_sha,
                       changed_files, declared_*_sha...},
          "query_id": "search:...",
          "query_digest": "sha256-hex",  # optional
          "index_identity": {            # optional declared binding
             "index_id": "python-ast-symbols-v1",
             "index_revision": "sha-or-rev",
             "backend_id": "stdlib-pointer",
          },
          "retrievers": [
            {
              "identity": {"retriever_id": "exact_symbol", "index_id": "...",
                           "index_revision": "...", "retriever_version": "v1"},
              "ranked_candidates": [
                {"candidate_ref": "src/a.py::Foo", "source_rank": 1,
                 "source_score": 10.0, "evidence_ref": "symbol-index:a.py:Foo",
                 "match_class": "EXACT"}
              ],
              "complete": true,
              "errors": [],
              "source_hits": 1
            }
          ],
          "required_candidates": 5,   # optional, default 8
          "collection_complete": true,
          "collection_errors": []
        }

    The engine fuses caller-supplied ranked candidate lists deterministically
    (RRF, k=60), preserves every exact-match candidate, bounds the fused set to
    ``required_candidates``, and derives a resolution. Empty retrieval yields
    ``EMPTY_RETRIEVAL_NOT_ABSENCE`` (never proof of absence). Repeated/partial
    retrieval evidence stays explicit as evidence gaps.
    """
    if not isinstance(data, Mapping):
        raise TypeError("repository query input must be a mapping")

    source_evidence = _canonical_source_evidence(data)
    data = source_evidence

    gaps: list[str] = []
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, Mapping):
        gaps.append("snapshot must be a mapping")
        snapshot = {}
    identity = revision_identity(snapshot)
    gaps.extend(identity.evidence_gaps)
    if identity.stale_evidence:
        gaps.append("stale identity evidence")

    query_id = data.get("query_id")
    if not isinstance(query_id, str) or not query_id.strip():
        gaps.append("query_id missing or invalid")
        query_id = ""
    else:
        query_id = query_id.strip()

    query_digest = data.get("query_digest")
    if not isinstance(query_digest, str) or not query_digest.strip():
        gaps.append("query_digest missing or invalid")
        query_digest = ""
    else:
        query_digest = query_digest.strip()

    index_identity = _normalize_index_identity(data, gaps=gaps)
    retrievers = _normalize_retrievers(data, index_identity=index_identity, gaps=gaps)
    required_candidates = _normalize_required_candidates(data, gaps=gaps)

    collection_complete_raw = data.get("collection_complete", False)
    if not isinstance(collection_complete_raw, bool):
        gaps.append("collection_complete must be a boolean")
        collection_complete = False
    else:
        collection_complete = collection_complete_raw
    if not collection_complete:
        gaps.append("collection_incomplete")
    caller_errors = _normalize_reason_codes(data.get("collection_errors"))
    for message in caller_errors:
        gaps.append(message)

    deduped_gaps = tuple(dict.fromkeys(str(gap) for gap in gaps))

    fused_candidates = _fuse_candidates(
        retrievers, required_candidates=required_candidates
    )
    resolution, reason_codes = _derive_resolution(
        identity=identity,
        query_id=query_id,
        query_digest=query_digest,
        gaps=deduped_gaps,
        index_identity=index_identity,
        retrievers=retrievers,
        required_candidates=required_candidates,
    )

    distinct_candidates = len({
        candidate.candidate_ref
        for run in retrievers
        for candidate in run.ranked_candidates
    })
    exact_count = len({
        candidate.candidate_ref
        for run in retrievers
        for candidate in run.ranked_candidates
        if candidate.match_class in EXACT_MATCH_CLASSES
    })

    completeness = _derive_completeness(
        identity=identity,
        gaps=deduped_gaps,
        required_candidates=required_candidates,
        resolution=resolution,
    )

    report = RepositoryQueryEvidenceReportV1(
        identity=identity,
        query_id=query_id,
        query_digest=query_digest,
        index_identity=index_identity,
        source_evidence=source_evidence,
        retrievers=tuple(retrievers),
        fused_candidates=tuple(fused_candidates),
        resolution=resolution,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        evidence_gaps=deduped_gaps,
        evidence_completeness=completeness,
        is_complete=completeness is EvidenceCompleteness.COMPLETE
        and resolution in {
            RepositoryQueryResolution.EXACT_RESOLUTION,
            RepositoryQueryResolution.BOUNDED_CANDIDATES,
        },
        required_candidates=required_candidates,
        distinct_candidate_count=distinct_candidates,
        exact_match_count=exact_count,
        semantic_review_needed=resolution in _RESOLUTION_REVIEW_NEEDED,
        content_sha256="",
        claim_ceiling=REPOSITORY_QUERY_CLAIM_CEILING,
    )
    return replace(report, content_sha256=_content_hash(report.to_dict()))


def verify_repository_query_evidence(payload: Mapping[str, Any]) -> bool:
    """Recompute the full report from embedded neutral source evidence.

    The source evidence is the canonical JSON-like input actually consumed by
    analyze_repository_query. Re-running the analyzer prevents a caller from
    deleting collection/normalization gaps, changing a derived disposition,
    and merely recomputing the outer content hash.
    """
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != RETRIEVAL_SCHEMA:
        return False
    if payload.get("claim_ceiling") != REPOSITORY_QUERY_CLAIM_CEILING:
        return False

    source_evidence = payload.get("source_evidence")
    if not isinstance(source_evidence, Mapping):
        return False

    try:
        recomputed = analyze_repository_query(source_evidence).to_dict()
    except (TypeError, ValueError):
        return False

    if dict(payload) != recomputed:
        return False

    if (
        recomputed["resolution"] == RepositoryQueryResolution.INSUFFICIENT_EVIDENCE.value
        and recomputed["reason_codes"] != [_REASON_EMPTY_RETRIEVAL_NOT_ABSENCE]
    ):
        return False
    return True
