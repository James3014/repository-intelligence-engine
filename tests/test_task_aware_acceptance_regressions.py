"""Semantic tampering must fail even when the attacker recomputes a hash."""
import copy
import hashlib
import json

from repository_intelligence.retrieval import (
    analyze_task_aware_query,
    normalize_task_context,
    verify_repository_query_evidence,
    verify_task_aware_query_evidence,
)


def _input():
    return {
        "snapshot": {"repository": "o/r", "pr_number": 1, "head_sha": "h", "base_sha": "b", "current_main_sha": "b"},
        "query_id": "q", "query_digest": "a" * 64,
        "index_identity": {"index_id": "idx", "index_revision": "i"},
        "retrievers": [{"identity": {"retriever_id": "path", "index_id": "idx", "index_revision": "i", "retriever_version": "v"},
                        "ranked_candidates": [{"candidate_ref": "a.py", "source_rank": 1, "evidence_ref": "e"}],
                        "complete": True, "source_hits": 1, "errors": []}],
        "required_candidates": 1, "collection_complete": True, "collection_errors": [],
        "task_context": {"fusion_policy": "rrf_k60_weighted", "fusion_weights": {"path": 1.0}},
    }


def test_weighted_wrapper_preserves_canonical_payload_and_verifies():
    report = analyze_task_aware_query(_input()).to_dict()
    assert verify_repository_query_evidence(report["query_report"])
    assert verify_task_aware_query_evidence(report)


def test_rehashed_forged_order_and_contributions_rejected():
    original = analyze_task_aware_query(_input()).to_dict()
    for field, value in (("weighted_fusion_order", ["foreign.py"]), ("per_source_contribution", {"path": 500}), ("additive_note", "HARD_PRUNE")):
        report = copy.deepcopy(original)
        report[field] = value
        report.pop("content_sha256")
        report["content_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert not verify_task_aware_query_evidence(report)


def test_nonfinite_fusion_weights_do_not_enter_rank_arithmetic():
    for value in (float("nan"), float("inf"), True):
        _, gaps = normalize_task_context({"fusion_policy": "rrf_k60_weighted", "fusion_weights": {"path": value}})
        assert gaps


def test_weighted_bound_preserves_every_exact_candidate():
    data = _input()
    data["retrievers"][0]["ranked_candidates"] = [
        {"candidate_ref": "approx.py", "source_rank": 1, "evidence_ref": "a"},
        {"candidate_ref": "exact1.py", "source_rank": 2, "evidence_ref": "b", "match_class": "EXACT"},
        {"candidate_ref": "exact2.py", "source_rank": 3, "evidence_ref": "c", "match_class": "EXACT"},
    ]
    data["retrievers"][0]["source_hits"] = 3
    report = analyze_task_aware_query(data)
    assert set(report.weighted_fusion_order) == {"exact1.py", "exact2.py"}
