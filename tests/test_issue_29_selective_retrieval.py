"""Issue #29: Selective repository retrieval evidence with deterministic fusion.

Covers the canonical ``analyze_repository_query`` /
``verify_repository_query_evidence`` operations and the issue's required
negative controls:

- stale repository/index revision identity binding;
- candidate from a different revision;
- retriever-index mismatch (substitution);
- score/rank tampering;
- incomplete coverage misreported as complete;
- exact-match evidence dropped by lower-confidence retrieval;
- duplicate candidate inflation;
- empty retrieval interpreted as proof of absence.
"""
from __future__ import annotations

import json

import pytest

from repository_intelligence.retrieval import (
    DEFAULT_REQUIRED_CANDIDATES,
    FUSION_K,
    RETRIEVAL_SCHEMA,
    analyze_repository_query,
    verify_repository_query_evidence,
)
from repository_intelligence.contracts import (
    REPOSITORY_QUERY_CLAIM_CEILING,
    RepositoryQueryResolution,
)


def _snapshot(**overrides):
    data = {
        "repository": "owner/repo",
        "pr_number": 42,
        "head_sha": "aaaa1111",
        "base_sha": "bbbb2222",
        "current_main_sha": "bbbb2222",
        "declared_base_sha": "bbbb2222",
        "declared_head_sha": "aaaa1111",
        "declared_main_sha": "bbbb2222",
    }
    data.update(overrides)
    return data


def _index_identity(revision="idx-42"):
    return {
        "index_id": "python-ast-symbols-v1",
        "index_revision": revision,
        "backend_id": "stdlib-pointer",
    }


def _candidate(ref, rank, score=None, match_class=""):
    entry = {"candidate_ref": ref, "source_rank": rank}
    if score is not None:
        entry["source_score"] = score
    if match_class:
        entry["match_class"] = match_class
    entry["evidence_ref"] = f"symbol-index:{ref}"
    return entry


def _retriever(retriever_id="exact_symbol", candidates=(), complete=True, revision="idx-42", errors=()):
    return {
        "identity": {
            "retriever_id": retriever_id,
            "index_id": "python-ast-symbols-v1",
            "index_revision": revision,
            "retriever_version": "v1",
        },
        "ranked_candidates": list(candidates),
        "complete": complete,
        "source_hits": len(candidates),
        "errors": list(errors),
    }


def _query_data(**overrides):
    data = {
        "snapshot": _snapshot(),
        "query_id": "symbols:revision_identity",
        "query_digest": "a" * 64,
        "index_identity": _index_identity(),
        "retrievers": [
            _retriever(
                candidates=[
                    _candidate("pkg/core.py::revision_identity", 1, score=1.0, match_class="EXACT")
                ]
            )
        ],
        "required_candidates": 5,
        "collection_complete": True,
        "collection_errors": [],
    }
    data.update(overrides)
    return data


def _verify_report_no_error(payload):
    assert payload.get("schema") == RETRIEVAL_SCHEMA
    return payload


def test_exact_resolution_defaults_hash_bound_and_verifiable():
    report = analyze_repository_query(_query_data())
    payload = _verify_report_no_error(report.to_dict())
    assert payload["claim_ceiling"] == REPOSITORY_QUERY_CLAIM_CEILING
    assert len(payload["content_sha256"]) == 64
    assert payload["resolution"] == "EXACT_RESOLUTION"
    assert payload["is_complete"] is True
    assert payload["semantic_review_needed"] is False
    assert payload["distinct_candidate_count"] == 1
    assert payload["exact_match_count"] == 1
    assert payload["required_candidates"] == 5
    assert payload["evidence_gaps"] == []
    assert payload["fused_candidates"][0]["fused_rank"] == 1
    assert payload["fused_candidates"][0]["exact_match"] is True
    assert verify_repository_query_evidence(payload) is True

    tampered = dict(payload)
    tampered["resolution"] = RepositoryQueryResolution.BOUNDED_CANDIDATES.value
    assert verify_repository_query_evidence(tampered) is False


def test_rrf_fusion_ranks_of_retrieved_candidates_are_deterministic():
    data = _query_data(
        retrievers=[
            _retriever(
                "exact_symbol",
                candidates=[
                    _candidate("pkg/core.py::revision_identity", 1, score=1.0,
                               match_class="EXACT"),
                    _candidate("pkg/other.py::revision_identity", 2, score=0.5,
                               match_class="LEXICAL"),
                ],
            ),
            _retriever(
                "lexical",
                candidates=[
                    _candidate("pkg/other.py::revision_identity", 1, match_class="LEXICAL"),
                    _candidate("pkg/core.py::revision_identity", 2, match_class="LEXICAL"),
                ],
            ),
        ]
    )
    payload = analyze_repository_query(data).to_dict()

    exact = payload["fused_candidates"][0]
    assert exact["candidate_ref"] == "pkg/core.py::revision_identity"
    assert exact["fused_rank"] == 1
    assert exact["exact_match"] is True
    # RRF scores: EXACT from two sources: 1/61 + 1/62
    assert exact["fused_score"] == round(1 / (FUSION_K + 1) + 1 / (FUSION_K + 2), 6)
    assert exact["matched_source_count"] == 2

    second = payload["fused_candidates"][1]
    assert second["candidate_ref"] == "pkg/other.py::revision_identity"
    assert second["fused_rank"] == 2
    assert verify_repository_query_evidence(payload) is True


def test_bounded_candidates_when_multiple_nonexact():
    data = _query_data(
        retrievers=[
            _retriever(
                "lexical",
                candidates=[
                    _candidate("pkg/a.py::A", 1, match_class="LEXICAL"),
                    _candidate("pkg/b.py::A", 2, match_class="LEXICAL"),
                ],
            )
        ]
    )
    payload = analyze_repository_query(data).to_dict()
    assert payload["resolution"] == "BOUNDED_CANDIDATES"
    assert payload["exact_match_count"] == 0
    assert payload["distinct_candidate_count"] == 2
    assert payload["semantic_review_needed"] is False
    assert payload["is_complete"] is True
    assert verify_repository_query_evidence(payload) is True


def test_ambiguous_when_exceeding_required_candidates():
    data = _query_data(
        required_candidates=2,
        retrievers=[
            _retriever(
                "lexical",
                candidates=[
                    _candidate("pkg/a.py::A", 1, match_class="LEXICAL"),
                    _candidate("pkg/b.py::A", 2, match_class="LEXICAL"),
                    _candidate("pkg/c.py::A", 3, match_class="LEXICAL"),
                ],
            )
        ],
    )
    payload = analyze_repository_query(data).to_dict()
    assert payload["resolution"] == "AMBIGUOUS_RETRIEVAL"
    assert payload["reason_codes"] == ["AMBIGUOUS_CANDIDATES"]
    assert payload["semantic_review_needed"] is True
    assert payload["distinct_candidate_count"] == 3
    assert len(payload["fused_candidates"]) == 2
    assert verify_repository_query_evidence(payload) is True


def test_multiple_exact_matches_is_ambiguous():
    data = _query_data(
        retrievers=[
            _retriever(
                candidates=[
                    _candidate("pkg/a.py::A", 1, score=0.9, match_class="EXACT"),
                    _candidate("pkg/b.py::A", 1, score=0.7, match_class="EXACT"),
                ]
            )
        ]
    )
    payload = analyze_repository_query(data).to_dict()
    assert payload["resolution"] == "AMBIGUOUS_RETRIEVAL"
    assert payload["reason_codes"] == ["MULTIPLE_EXACT_MATCHES"]
    assert payload["exact_match_count"] == 2
    assert verify_repository_query_evidence(payload) is True


def test_negative_control_invalid_revision_identity():
    report = analyze_repository_query(_query_data(snapshot=_snapshot(pr_number=0)))
    payload = report.to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert payload["reason_codes"] == ["INVALID_REVISION_IDENTITY"]
    assert payload["is_complete"] is False
    assert verify_repository_query_evidence(payload) is False


def test_negative_control_stale_revision_evidence():
    report = analyze_repository_query(
        _query_data(snapshot=_snapshot(declared_base_sha="deadbeef"))
    )
    payload = report.to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert payload["reason_codes"] == ["STALE_REVISION_EVIDENCE"]
    assert payload["is_complete"] is False


def test_negative_control_candidate_from_different_revision():
    # Retriever bound to a different index revision than the declared index.
    data = _query_data(index_identity=_index_identity("idx-42"))
    data["retrievers"] = [_retriever(revision="idx-999", candidates=[_candidate("pkg/old.py::A", 1)])]
    report = analyze_repository_query(data)
    payload = report.to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert "index_revision" in payload["evidence_gaps"][0]
    assert verify_repository_query_evidence(payload) is False


def test_negative_control_retriever_index_substitution():
    data = _query_data(index_identity=_index_identity("idx-42"))
    data["retrievers"] = [
        _retriever(
            "lexical",
            candidates=[_candidate("pkg/core.py::revision_identity", 1, match_class="LEXICAL")],
        )
    ]
    data["index_identity"] = _index_identity("idx-999")
    report = analyze_repository_query(data)
    payload = report.to_dict()
    # index_identity differs from the retriever binding -> fail closed.
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert verify_repository_query_evidence(payload) is False


def test_negative_control_score_rank_tampering_rejected_by_verifier():
    report = analyze_repository_query(_query_data())
    payload = report.to_dict()
    assert verify_repository_query_evidence(payload) is True

    tampered = json.loads(json.dumps(payload))
    tampered["fused_candidates"][0]["fused_score"] -= 1.0
    tampered["fused_candidates"][0]["per_source_refs"][0]["source_rank"] = 99
    assert verify_repository_query_evidence(tampered) is False


def test_negative_control_incomplete_retriever_misreported_as_complete():
    data = _query_data(
        retrievers=[
            _retriever(
                "lexical",
                candidates=[_candidate("pkg/a.py::A", 1)],
                complete=False,
            )
        ]
    )
    payload = analyze_repository_query(data).to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert payload["reason_codes"] == ["RETRIEVER_INCOMPLETE"]
    assert payload["is_complete"] is False

    forged = json.loads(json.dumps(payload))
    forged["retrievers"][0]["complete"] = True
    forged["retrievers"][0]["source_hits"] = 1
    forged["content_sha256"] = ""
    # recompute hash over the forged payload the way analysis would not; the
    # verifier recomputes fusion/completeness from primes and must reject the
    # completeness lie.
    import hashlib as _hashlib
    unsigned = {k: v for k, v in forged.items() if k != "content_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    forged["content_sha256"] = _hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert verify_repository_query_evidence(forged) is False


def test_negative_control_exact_match_not_dropped_by_lower_confidence_retrieval():
    # A dominant lexical retriever ranks the exact candidate below other
    # candidates. The exact candidate must still be preserved in the bounded set.
    data = _query_data(
        retrievers=[
            _retriever(
                "exact_symbol",
                candidates=[_candidate("pkg/core.py::revision_identity", 1, score=1.0,
                                       match_class="EXACT")],
            ),
            _retriever(
                "lexical",
                candidates=[
                    _candidate("pkg/decoys/decoys1.py::revision_identity", 1, match_class="LEXICAL"),
                    _candidate("pkg/decoys/decoys2.py::revision_identity", 2, match_class="LEXICAL"),
                    _candidate("pkg/core.py::revision_identity", 9, match_class="LEXICAL"),
                ],
            ),
        ],
        required_candidates=2,
    )
    payload = analyze_repository_query(data).to_dict()
    refs = [candidate["candidate_ref"] for candidate in payload["fused_candidates"]]
    assert "pkg/core.py::revision_identity" in refs
    assert payload["fused_candidates"][0]["exact_match"] is True

    forged = json.loads(json.dumps(payload))
    forged["fused_candidates"] = [c for c in forged["fused_candidates"]
                                  if c["candidate_ref"] != "pkg/core.py::revision_identity"]
    forged["content_sha256"] = ""
    import hashlib as _hashlib
    unsigned = {k: v for k, v in forged.items() if k != "content_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    forged["content_sha256"] = _hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert verify_repository_query_evidence(forged) is False


def test_negative_control_duplicate_candidate_inflation_rejected():
    data = _query_data(
        retrievers=[
            _retriever(
                candidates=[
                    _candidate("pkg/core.py::revision_identity", 1, score=1.0, match_class="EXACT"),
                    _candidate("pkg/core.py::revision_identity", 1, score=1.0, match_class="EXACT"),
                ]
            )
        ]
    )
    report = analyze_repository_query(data)
    payload = report.to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert any("duplicate candidate_ref" in gap for gap in payload["evidence_gaps"])
    assert verify_repository_query_evidence(payload) is False


def test_negative_control_empty_retrieval_is_not_proof_of_absence():
    data = _query_data(
        retrievers=[_retriever("exact_symbol", candidates=[], complete=True)]
    )
    payload = analyze_repository_query(data).to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert payload["reason_codes"] == ["EMPTY_RETRIEVAL_NOT_ABSENCE"]
    assert payload["distinct_candidate_count"] == 0
    assert payload["is_complete"] is False
    assert verify_repository_query_evidence(payload) is True


def test_query_digest_and_query_id_required():
    missing_digest = analyze_repository_query(_query_data(query_digest="")).to_dict()
    assert missing_digest["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert missing_digest["reason_codes"] == ["QUERY_DIGEST_MISSING"]

    missing_query_id = analyze_repository_query(_query_data(query_id="")).to_dict()
    assert missing_query_id["resolution"] == "INSUFFICIENT_EVIDENCE"


def test_collection_errors_block_resolution():
    report = analyze_repository_query(
        _query_data(collection_complete=True, collection_errors=["index build failed"])
    )
    payload = report.to_dict()
    assert payload["resolution"] == "INSUFFICIENT_EVIDENCE"
    assert "index build failed" in payload["evidence_gaps"]
    assert verify_repository_query_evidence(payload) is False


def test_default_required_candidates_is_eight():
    assert DEFAULT_REQUIRED_CANDIDATES == 8
    data = _query_data(required_candidates=None)
    payload = analyze_repository_query(data).to_dict()
    assert payload["required_candidates"] == DEFAULT_REQUIRED_CANDIDATES


def test_invalid_inputs_fail_closed():
    with pytest.raises(TypeError, match="mapping"):
        analyze_repository_query(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="mapping"):
        analyze_repository_query([1, 2, 3])  # type: ignore[arg-type]

    assert verify_repository_query_evidence(None) is False  # type: ignore[arg-type]
    assert verify_repository_query_evidence({}) is False
    assert verify_repository_query_evidence({"schema": RETRIEVAL_SCHEMA}) is False
    assert verify_repository_query_evidence({"schema": "wrong", "claim_ceiling": "x"}) is False