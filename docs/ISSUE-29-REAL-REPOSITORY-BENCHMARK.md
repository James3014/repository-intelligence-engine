# Issue #29 real-repository retrieval benchmark

- repository HEAD: 3591e6de2f9b174b92db0aed9433bb8d093b2c06
- observed origin/main: eb74d8daafb1e01a1fef9d2d09239a3077cd537c
- real AST symbol candidates: 116
- frozen queries: 5
- semantic-review rate is the semantic_review_needed proxy; no LLM was invoked.

| mode | Top-8 recall | candidate reduction | mean latency | semantic review rate |
|---|---:|---:|---:|---:|
| deterministic_exact | 100.0% | 99.1% | 0.089 ms | 0.0% |
| lexical | 100.0% | 93.3% | 0.256 ms | 80.0% |
| hybrid | 100.0% | 93.3% | 0.265 ms | 0.0% |

This is bounded offline evidence over this repository only. It does not establish
semantic-review correctness, routing fitness, or production authority.

Raw JSON:
{
  "case_count": 5,
  "index_size": 116,
  "repository_head": "3591e6de2f9b174b92db0aed9433bb8d093b2c06",
  "repository_main": "eb74d8daafb1e01a1fef9d2d09239a3077cd537c",
  "rows": [
    {
      "candidate_reduction": 0.9913793103448276,
      "distinct_candidate_count": 1,
      "fused": [
        "repository_intelligence/core.py::revision_identity"
      ],
      "latency_ms": 0.1745839836075902,
      "mode": "deterministic_exact",
      "query": "find revision_identity implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/core.py::revision_identity",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9396551724137931,
      "distinct_candidate_count": 7,
      "fused": [
        "repository_intelligence/core.py::revision_identity",
        "repository_intelligence/contracts.py::review_identity",
        "repository_intelligence/models.py::review_identity",
        "repository_intelligence/eia.py::_identity_from_payload",
        "repository_intelligence/facts.py::_identity_from_payload",
        "repository_intelligence/retrieval.py::_normalize_index_identity",
        "repository_intelligence/retrieval.py::_normalize_retriever_identity"
      ],
      "latency_ms": 0.17399998614564538,
      "mode": "lexical",
      "query": "find revision_identity implementation",
      "resolution": "BOUNDED_CANDIDATES",
      "semantic_review_needed": false,
      "target": "repository_intelligence/core.py::revision_identity",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9396551724137931,
      "distinct_candidate_count": 7,
      "fused": [
        "repository_intelligence/core.py::revision_identity",
        "repository_intelligence/contracts.py::review_identity",
        "repository_intelligence/models.py::review_identity",
        "repository_intelligence/eia.py::_identity_from_payload",
        "repository_intelligence/facts.py::_identity_from_payload",
        "repository_intelligence/retrieval.py::_normalize_index_identity",
        "repository_intelligence/retrieval.py::_normalize_retriever_identity"
      ],
      "latency_ms": 0.15633401926606894,
      "mode": "hybrid",
      "query": "find revision_identity implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/core.py::revision_identity",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9913793103448276,
      "distinct_candidate_count": 1,
      "fused": [
        "repository_intelligence/retrieval.py::analyze_repository_query"
      ],
      "latency_ms": 0.07420795736834407,
      "mode": "deterministic_exact",
      "query": "find analyze_repository_query implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/retrieval.py::analyze_repository_query",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 40,
      "fused": [
        "repository_intelligence/retrieval.py::analyze_repository_query",
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/impact.py::analyze_change_impact",
        "repository_intelligence/cfi.py::analyze_ci_failure_intelligence",
        "repository_intelligence/retrieval.py::verify_repository_query_evidence",
        "repository_intelligence/core.py::analyze_cross_pr_overlap",
        "repository_intelligence/classifier.py::add",
        "repository_intelligence/classifier.py::classify"
      ],
      "latency_ms": 0.36449998151510954,
      "mode": "lexical",
      "query": "find analyze_repository_query implementation",
      "resolution": "AMBIGUOUS_RETRIEVAL",
      "semantic_review_needed": true,
      "target": "repository_intelligence/retrieval.py::analyze_repository_query",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 40,
      "fused": [
        "repository_intelligence/retrieval.py::analyze_repository_query",
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/impact.py::analyze_change_impact",
        "repository_intelligence/cfi.py::analyze_ci_failure_intelligence",
        "repository_intelligence/retrieval.py::verify_repository_query_evidence",
        "repository_intelligence/core.py::analyze_cross_pr_overlap",
        "repository_intelligence/classifier.py::add",
        "repository_intelligence/classifier.py::classify"
      ],
      "latency_ms": 0.36624999484047294,
      "mode": "hybrid",
      "query": "find analyze_repository_query implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/retrieval.py::analyze_repository_query",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9913793103448276,
      "distinct_candidate_count": 1,
      "fused": [
        "repository_intelligence/facts.py::analyze_structured_facts"
      ],
      "latency_ms": 0.06679201032966375,
      "mode": "deterministic_exact",
      "query": "find analyze_structured_facts implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/facts.py::analyze_structured_facts",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 20,
      "fused": [
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/facts.py::verify_structured_facts_report",
        "repository_intelligence/facts.py::_classify_facts",
        "repository_intelligence/facts.py::_content_hash",
        "repository_intelligence/facts.py::_derive_completeness",
        "repository_intelligence/facts.py::_derive_limitations",
        "repository_intelligence/facts.py::_normalize_errors",
        "repository_intelligence/facts.py::_normalize_path"
      ],
      "latency_ms": 0.21900003775954247,
      "mode": "lexical",
      "query": "find analyze_structured_facts implementation",
      "resolution": "AMBIGUOUS_RETRIEVAL",
      "semantic_review_needed": true,
      "target": "repository_intelligence/facts.py::analyze_structured_facts",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 20,
      "fused": [
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/facts.py::verify_structured_facts_report",
        "repository_intelligence/facts.py::_classify_facts",
        "repository_intelligence/facts.py::_content_hash",
        "repository_intelligence/facts.py::_derive_completeness",
        "repository_intelligence/facts.py::_derive_limitations",
        "repository_intelligence/facts.py::_normalize_errors",
        "repository_intelligence/facts.py::_normalize_path"
      ],
      "latency_ms": 0.2399170189164579,
      "mode": "hybrid",
      "query": "find analyze_structured_facts implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/facts.py::analyze_structured_facts",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9913793103448276,
      "distinct_candidate_count": 1,
      "fused": [
        "repository_intelligence/impact.py::analyze_change_impact"
      ],
      "latency_ms": 0.06679195212200284,
      "mode": "deterministic_exact",
      "query": "find analyze_change_impact implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/impact.py::analyze_change_impact",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 14,
      "fused": [
        "repository_intelligence/impact.py::analyze_change_impact",
        "repository_intelligence/impact.py::verify_change_impact_report",
        "repository_intelligence/impact.py::_compute_impact",
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/impact.py::_content_hash",
        "repository_intelligence/impact.py::_graph_hash",
        "repository_intelligence/impact.py::_normalize_edges",
        "repository_intelligence/impact.py::_normalize_path"
      ],
      "latency_ms": 0.17920898972079158,
      "mode": "lexical",
      "query": "find analyze_change_impact implementation",
      "resolution": "AMBIGUOUS_RETRIEVAL",
      "semantic_review_needed": true,
      "target": "repository_intelligence/impact.py::analyze_change_impact",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 14,
      "fused": [
        "repository_intelligence/impact.py::analyze_change_impact",
        "repository_intelligence/impact.py::verify_change_impact_report",
        "repository_intelligence/impact.py::_compute_impact",
        "repository_intelligence/facts.py::analyze_structured_facts",
        "repository_intelligence/impact.py::_content_hash",
        "repository_intelligence/impact.py::_graph_hash",
        "repository_intelligence/impact.py::_normalize_edges",
        "repository_intelligence/impact.py::_normalize_path"
      ],
      "latency_ms": 0.19754201639443636,
      "mode": "hybrid",
      "query": "find analyze_change_impact implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/impact.py::analyze_change_impact",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9913793103448276,
      "distinct_candidate_count": 1,
      "fused": [
        "repository_intelligence/retrieval.py::verify_repository_query_evidence"
      ],
      "latency_ms": 0.06445904728025198,
      "mode": "deterministic_exact",
      "query": "find verify_repository_query_evidence implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/retrieval.py::verify_repository_query_evidence",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 40,
      "fused": [
        "repository_intelligence/retrieval.py::verify_repository_query_evidence",
        "repository_intelligence/core.py::verify_ci_failure_evidence",
        "repository_intelligence/core.py::verify_repository_intelligence_report",
        "repository_intelligence/retrieval.py::analyze_repository_query",
        "repository_intelligence/facts.py::verify_structured_facts_report",
        "repository_intelligence/impact.py::verify_change_impact_report",
        "repository_intelligence/retrieval.py::_canonical_source_evidence",
        "repository_intelligence/cfi.py::verify_ci_failure_intelligence_report"
      ],
      "latency_ms": 0.34149998100474477,
      "mode": "lexical",
      "query": "find verify_repository_query_evidence implementation",
      "resolution": "AMBIGUOUS_RETRIEVAL",
      "semantic_review_needed": true,
      "target": "repository_intelligence/retrieval.py::verify_repository_query_evidence",
      "top8_hit": true
    },
    {
      "candidate_reduction": 0.9310344827586207,
      "distinct_candidate_count": 40,
      "fused": [
        "repository_intelligence/retrieval.py::verify_repository_query_evidence",
        "repository_intelligence/core.py::verify_ci_failure_evidence",
        "repository_intelligence/core.py::verify_repository_intelligence_report",
        "repository_intelligence/retrieval.py::analyze_repository_query",
        "repository_intelligence/facts.py::verify_structured_facts_report",
        "repository_intelligence/impact.py::verify_change_impact_report",
        "repository_intelligence/retrieval.py::_canonical_source_evidence",
        "repository_intelligence/cfi.py::verify_ci_failure_intelligence_report"
      ],
      "latency_ms": 0.3664999967440963,
      "mode": "hybrid",
      "query": "find verify_repository_query_evidence implementation",
      "resolution": "EXACT_RESOLUTION",
      "semantic_review_needed": false,
      "target": "repository_intelligence/retrieval.py::verify_repository_query_evidence",
      "top8_hit": true
    }
  ],
  "summary": {
    "deterministic_exact": {
      "cases": 5,
      "mean_candidate_reduction": 0.9913793103448276,
      "mean_latency_ms": 0.08936699014157057,
      "semantic_review_rate": 0.0,
      "top8_recall": 1.0
    },
    "hybrid": {
      "cases": 5,
      "mean_candidate_reduction": 0.9327586206896552,
      "mean_latency_ms": 0.2653086092323065,
      "semantic_review_rate": 0.0,
      "top8_recall": 1.0
    },
    "lexical": {
      "cases": 5,
      "mean_candidate_reduction": 0.9327586206896552,
      "mean_latency_ms": 0.25564179522916675,
      "semantic_review_rate": 0.8,
      "top8_recall": 1.0
    }
  }
}
