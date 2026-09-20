"""Deterministic RRF retrieval benchmark for Issue #29.

Exercises ``analyze_repository_query`` / ``verify_repository_query_evidence``
with synthetic retriever workloads and prints wall-clock and throughput
figures. Purely advisory; never authoritative for production claims.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _snapshot():
    return {
        "repository": "owner/repo",
        "pr_number": 217,
        "head_sha": "aaaabbbb",
        "base_sha": "ccccdddd",
        "current_main_sha": "ccccdddd",
    }


def _index_identity():
    return {
        "index_id": "python-ast-symbols-v1",
        "index_revision": "rev-42",
        "backend_id": "stdlib-pointer",
    }


def _build_query(retrievers, required=8):
    return {
        "snapshot": _snapshot(),
        "query_id": "symbols:foo",
        "query_digest": "a" * 64,
        "index_identity": _index_identity(),
        "retrievers": retrievers,
        "required_candidates": required,
        "collection_complete": True,
        "collection_errors": [],
    }


def _retriever(retriever_id, candidates):
    return {
        "identity": {
            "retriever_id": retriever_id,
            "index_id": "python-ast-symbols-v1",
            "index_revision": "rev-42",
            "retriever_version": "v1",
        },
        "ranked_candidates": candidates,
        "complete": True,
        "source_hits": len(candidates),
        "errors": [],
    }


def _retrievers(retriever_count, candidates_per_retriever):
    out = []
    for retriever_index in range(retriever_count):
        candidates = []
        for candidate_index in range(candidates_per_retriever):
            candidates.append(
                {
                    "candidate_ref": f"pkg/mod{retriever_index}.py::sym{candidate_index}",
                    "source_rank": candidate_index + 1,
                    "source_score": 1.0 - candidate_index * 0.001,
                    "evidence_ref": f"symbol-index:mod{retriever_index}:sym{candidate_index}",
                    "match_class": "EXACT" if candidate_index == 0 else "LEXICAL",
                }
            )
        out.append(_retriever(f"retriever_{retriever_index}", candidates))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrievers", type=int, default=8)
    parser.add_argument("--candidates", type=int, default=200)
    parser.add_argument("--required", type=int, default=8)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)

    from repository_intelligence.retrieval import (
        analyze_repository_query,
        verify_repository_query_evidence,
    )

    query = _build_query(
        _retrievers(args.retrievers, args.candidates),
        required=args.required,
    )

    payload = None
    analyze_start = time.perf_counter()
    for _ in range(args.runs):
        payload = analyze_repository_query(query).to_dict()
    analyze_elapsed = time.perf_counter() - analyze_start

    verified = all(
        verify_repository_query_evidence(payload)
        for _ in range(args.runs)
    )
    verify_start = time.perf_counter()
    for _ in range(args.runs):
        verify_repository_query_evidence(payload)
    verify_elapsed = time.perf_counter() - verify_start

    per_run = (analyze_elapsed + verify_elapsed) / args.runs
    print(
        f"retrievers={args.retrievers} candidates={args.candidates} "
        f"required={args.required} runs={args.runs}"
    )
    print(f"resolution={payload['resolution']} "
          f"distinct={payload['distinct_candidate_count']} "
          f"fused={len(payload['fused_candidates'])} verified={verified}")
    print(f"mean run (analyze+verify) {per_run * 1000:.3f} ms")

    _ = payload
    return 0


if __name__ == "__main__":
    raise SystemExit(main())