"""Issue #31: task-aware sparse retrieval + shadow test selection (follow-up to #29)."""
from __future__ import annotations

from repository_intelligence.contracts import TASK_AWARE_QUERY_CLAIM_CEILING
from repository_intelligence.retrieval import (
    analyze_repository_query,
    analyze_task_aware_query,
    normalize_task_context,
    verify_task_aware_query_evidence,
)


def _snapshot(**overrides):
    data = {"repository": "owner/repo", "pr_number": 7, "head_sha": "aaaa1111",
            "base_sha": "bbbb2222", "current_main_sha": "bbbb2222",
            "declared_base_sha": "bbbb2222", "declared_head_sha": "aaaa1111",
            "declared_main_sha": "bbbb2222"}
    data.update(overrides)
    return data


def _retriever(rid, refs, revision="idx-1"):
    return {"identity": {"retriever_id": rid, "index_id": "idx",
                           "index_revision": revision, "retriever_version": "v1"},
            "ranked_candidates": [{"candidate_ref": r, "source_rank": i + 1,
                                     "evidence_ref": f"e:{r}"} for i, r in enumerate(refs)],
            "complete": True, "source_hits": len(refs), "errors": []}


def _base(task_context=None):
    data = {"snapshot": _snapshot(), "query_id": "q:task-aware",
            "query_digest": "b" * 64,
            "index_identity": {"index_id": "idx", "index_revision": "idx-1"},
            "retrievers": [_retriever("path_lexical", ["src/a.py", "src/b.py"]),
                             _retriever("content_bm25", ["src/b.py", "src/c.py"]),
                             _retriever("history_cochange", ["src/c.py", "src/a.py"])],
            "required_candidates": 5, "collection_complete": True,
            "collection_errors": []}
    if task_context is not None:
        data["task_context"] = task_context
    return data


def test_uniform_default_preserves_canonical_report():
    base = analyze_repository_query(_base())
    wrapped = analyze_task_aware_query(_base())
    assert wrapped.task_context.task_role == "general_localization"
    assert wrapped.task_context.fusion_policy == "rrf_k60_uniform"
    assert wrapped.query_report["resolution"] == base.to_dict()["resolution"]
    assert wrapped.additive_note == "ADVISORY_ADDITIVE_TOP_K_INCOMPLETE"
    assert wrapped.claim_ceiling == TASK_AWARE_QUERY_CLAIM_CEILING
    assert verify_task_aware_query_evidence(wrapped.to_dict())


def test_weighted_policy_emits_deterministic_order():
    ctx = {"task_role": "general_localization", "fusion_policy": "rrf_k60_weighted",
           "fusion_weights": {"path_lexical": 2.0, "content_bm25": 1.0,
                                "history_cochange": 0.5}}
    first = analyze_task_aware_query(_base(ctx))
    second = analyze_task_aware_query(_base(ctx))
    assert first.to_dict() == second.to_dict()
    assert first.weighted_fusion_order
    assert verify_task_aware_query_evidence(first.to_dict())
    assert first.per_source_contribution == {"path_lexical": 2, "content_bm25": 2,
                                             "history_cochange": 2}
    assert first.missing_sources == ()


def test_missing_weighted_source_is_explicit():
    ctx = {"fusion_policy": "rrf_k60_weighted",
           "fusion_weights": {"path_lexical": 1.0, "ghost_retriever": 1.0}}
    wrapped = analyze_task_aware_query(_base(ctx))
    assert "ghost_retriever" in wrapped.missing_sources
    assert wrapped.query_report["resolution"] in ("BOUNDED_CANDIDATES", "EXACT_RESOLUTION",
                                                   "AMBIGUOUS_RETRIEVAL", "INSUFFICIENT_EVIDENCE")


def test_invalid_task_role_fails_closed_to_default():
    ctx, gaps = normalize_task_context({"task_role": "hard_prune_everything"})
    assert ctx.task_role == "general_localization"
    assert any("task_role" in g for g in gaps)


def test_test_selection_requires_shadow_mode():
    wrapped = analyze_task_aware_query(
        _base({"task_role": "test_selection", "shadow_mode": False}))
    assert any("shadow_mode" in g for g in wrapped.evidence_gaps)
    shadowed = analyze_task_aware_query(
        _base({"task_role": "test_selection", "shadow_mode": True}))
    assert not any("shadow_mode" in g
                   for g in shadowed.evidence_gaps
                   if "requires shadow_mode" in g)


def test_uniform_with_weights_rejected():
    ctx, gaps = normalize_task_context({"fusion_policy": "rrf_k60_uniform",
                                        "fusion_weights": {"a": 1.0}})
    assert ctx.fusion_policy == "rrf_k60_uniform"
    assert any("weights" in g for g in gaps)


def test_canonical_negative_controls_still_hold():
    stale = _base()
    stale["snapshot"] = _snapshot(declared_head_sha="ffff9999")
    wrapped = analyze_task_aware_query(stale)
    assert wrapped.query_report["resolution"] == "INSUFFICIENT_EVIDENCE"
    empty = _base()
    empty["retrievers"] = [_retriever("path_lexical", []),
                            _retriever("content_bm25", []),
                            _retriever("history_cochange", [])]
    wrapped_empty = analyze_task_aware_query(empty)
    assert wrapped_empty.query_report["reason_codes"] == ["EMPTY_RETRIEVAL_NOT_ABSENCE"]


def test_tampered_wrapper_fails_verification():
    wrapped = analyze_task_aware_query(_base())
    payload = wrapped.to_dict()
    payload["content_sha256"] = "0" * 64
    assert not verify_task_aware_query_evidence(payload)
    assert not verify_task_aware_query_evidence({"schema": "wrong"})


def test_no_hard_pruning_claim():
    wrapped = analyze_task_aware_query(_base())
    assert wrapped.additive_note == "ADVISORY_ADDITIVE_TOP_K_INCOMPLETE"
    assert wrapped.candidate_reduction["distinct_candidates"] >= len(
        wrapped.query_report["fused_candidates"])
