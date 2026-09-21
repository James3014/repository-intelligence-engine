"""Real-repository selective-retrieval benchmark for Issue #29.

Scans this checkout with stdlib AST, then compares deterministic exact-symbol,
lexical, and hybrid retrieval through the canonical RRF engine.

No LLM is called. semantic_review_needed is the bounded downstream-review
proxy. Results are advisory benchmark evidence only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASES = (
    ("find revision_identity implementation", "repository_intelligence/core.py::revision_identity"),
    ("find analyze_repository_query implementation", "repository_intelligence/retrieval.py::analyze_repository_query"),
    ("find analyze_structured_facts implementation", "repository_intelligence/facts.py::analyze_structured_facts"),
    ("find analyze_change_impact implementation", "repository_intelligence/impact.py::analyze_change_impact"),
    ("find verify_repository_query_evidence implementation", "repository_intelligence/retrieval.py::verify_repository_query_evidence"),
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def tokens(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-zA-Z0-9]+|_", text.lower()) if part}


def symbol_index() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted((ROOT / "repository_intelligence").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append((f"{rel}::{node.name}", node.name))
    return sorted(set(out))


def exact_candidates(query: str, corpus: list[tuple[str, str]]) -> list[dict]:
    query_words = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", query))
    matches = [(ref, name) for ref, name in corpus if name in query_words]
    return [
        {
            "candidate_ref": ref,
            "source_rank": rank,
            "source_score": 1.0,
            "evidence_ref": f"ast-symbol:{ref}",
            "match_class": "EXACT",
        }
        for rank, (ref, _name) in enumerate(matches, start=1)
    ]


def lexical_candidates(query: str, corpus: list[tuple[str, str]]) -> list[dict]:
    q = tokens(query)
    scored: list[tuple[float, str]] = []
    for ref, name in corpus:
        c = tokens(ref + " " + name)
        overlap = len(q & c)
        if not overlap:
            continue
        score = overlap / max(1, len(q | c))
        scored.append((score, ref))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        {
            "candidate_ref": ref,
            "source_rank": rank,
            "source_score": round(score, 6),
            "evidence_ref": f"lexical:{ref}",
            "match_class": "LEXICAL",
        }
        for rank, (score, ref) in enumerate(scored[:40], start=1)
    ]


def retriever(retriever_id: str, revision: str, candidates: list[dict]) -> dict:
    return {
        "identity": {
            "retriever_id": retriever_id,
            "index_id": "real-repo-ast-symbols-v1",
            "index_revision": revision,
            "retriever_version": "issue-29-benchmark-v1",
        },
        "ranked_candidates": candidates,
        "complete": True,
        "source_hits": len(candidates),
        "errors": [],
    }


def snapshot() -> dict:
    head = git("rev-parse", "HEAD")
    main = git("rev-parse", "origin/main")
    base = git("merge-base", "HEAD", "origin/main")
    return {
        "repository": "James3014/repository-intelligence-engine",
        "pr_number": 30,
        "head_sha": head,
        "base_sha": base,
        "current_main_sha": main,
        "declared_head_sha": head,
        "declared_base_sha": base,
        "declared_main_sha": main,
    }


def run_mode(mode: str, query: str, corpus: list[tuple[str, str]], snap: dict) -> dict:
    from repository_intelligence.retrieval import analyze_repository_query, verify_repository_query_evidence

    exact = exact_candidates(query, corpus)
    lexical = lexical_candidates(query, corpus)
    if mode == "deterministic_exact":
        runs = [retriever("exact_symbol", snap["head_sha"], exact)]
    elif mode == "lexical":
        runs = [retriever("lexical", snap["head_sha"], lexical)]
    elif mode == "hybrid":
        runs = [
            retriever("exact_symbol", snap["head_sha"], exact),
            retriever("lexical", snap["head_sha"], lexical),
        ]
    else:
        raise ValueError(mode)

    payload = {
        "snapshot": snap,
        "query_id": query,
        "query_digest": hashlib.sha256(query.encode()).hexdigest(),
        "index_identity": {
            "index_id": "real-repo-ast-symbols-v1",
            "index_revision": snap["head_sha"],
            "backend_id": "stdlib-ast-real-repo",
        },
        "retrievers": runs,
        "required_candidates": 8,
        "collection_complete": True,
        "collection_errors": [],
    }
    start = time.perf_counter()
    report = analyze_repository_query(payload).to_dict()
    elapsed_ms = (time.perf_counter() - start) * 1000
    if not verify_repository_query_evidence(report):
        raise RuntimeError(f"unverifiable report for {mode}:{query}")
    return {
        "resolution": report["resolution"],
        "semantic_review_needed": report["semantic_review_needed"],
        "fused": [c["candidate_ref"] for c in report["fused_candidates"]],
        "distinct_candidate_count": report["distinct_candidate_count"],
        "latency_ms": elapsed_ms,
    }


def benchmark() -> dict:
    corpus = symbol_index()
    snap = snapshot()
    modes = ("deterministic_exact", "lexical", "hybrid")
    rows: list[dict] = []
    for query, target in CASES:
        for mode in modes:
            result = run_mode(mode, query, corpus, snap)
            result.update(
                mode=mode,
                query=query,
                target=target,
                top8_hit=target in result["fused"][:8],
                candidate_reduction=1.0 - (len(result["fused"]) / len(corpus)),
            )
            rows.append(result)

    summary = {}
    for mode in modes:
        group = [row for row in rows if row["mode"] == mode]
        summary[mode] = {
            "cases": len(group),
            "top8_recall": sum(row["top8_hit"] for row in group) / len(group),
            "mean_candidate_reduction": mean(row["candidate_reduction"] for row in group),
            "mean_latency_ms": mean(row["latency_ms"] for row in group),
            "semantic_review_rate": sum(row["semantic_review_needed"] for row in group) / len(group),
        }
    return {
        "repository_head": snap["head_sha"],
        "repository_main": snap["current_main_sha"],
        "index_size": len(corpus),
        "case_count": len(CASES),
        "summary": summary,
        "rows": rows,
    }


def markdown(result: dict) -> str:
    lines = [
        "# Issue #29 real-repository retrieval benchmark",
        "",
        f"- repository HEAD: {result['repository_head']}",
        f"- observed origin/main: {result['repository_main']}",
        f"- real AST symbol candidates: {result['index_size']}",
        f"- frozen queries: {result['case_count']}",
        "- semantic-review rate is the semantic_review_needed proxy; no LLM was invoked.",
        "",
        "| mode | Top-8 recall | candidate reduction | mean latency | semantic review rate |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, row in result["summary"].items():
        lines.append(
            f"| {mode} | {row['top8_recall']:.1%} | "
            f"{row['mean_candidate_reduction']:.1%} | {row['mean_latency_ms']:.3f} ms | "
            f"{row['semantic_review_rate']:.1%} |"
        )
    lines += [
        "",
        "This is bounded offline evidence over this repository only. It does not establish",
        "semantic-review correctness, routing fitness, or production authority.",
        "",
        "Raw JSON:",
        json.dumps(result, indent=2, sort_keys=True),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = benchmark()
    text = markdown(result)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
