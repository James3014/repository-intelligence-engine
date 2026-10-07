"""Issue #56: deterministic source-to-knowledge applicability evidence."""
from __future__ import annotations

import copy
import hashlib
import json

import repository_intelligence as ri


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def _rehash(payload):
    unsigned = copy.deepcopy(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _base_evidence():
    return {
        "snapshot": {
            "repository": "owner/repo",
            "pr_number": 56,
            "head_sha": "head56",
            "base_sha": "main56",
            "current_main_sha": "main56",
        },
        "knowledge_artifacts": [
            {
                "artifact_id": "exact-current",
                "path": "knowledge/current.md",
                "source_refs": [
                    {
                        "source_path": "src/current.py",
                        "expected_content_sha256": A,
                    }
                ],
                "covers": [],
            },
            {
                "artifact_id": "exact-stale",
                "path": "knowledge/stale.md",
                "source_refs": [
                    {
                        "source_path": "src/stale.py",
                        "expected_content_sha256": A,
                    }
                ],
                "covers": [],
            },
            {
                "artifact_id": "covered",
                "path": "knowledge/covered.md",
                "source_refs": [],
                "covers": ["src/service/**"],
            },
        ],
        "changes": [
            {"kind": "MODIFY", "path": "src/stale.py"},
            {"kind": "MODIFY", "path": "src/service/worker.py"},
            {"kind": "MODIFY", "path": "src/uncovered.py"},
            {"kind": "MODIFY", "path": "examples/irrelevant.py"},
        ],
        "observed_source_sha256": {
            "src/current.py": A,
            "src/stale.py": B,
            "src/service/worker.py": C,
            "src/uncovered.py": D,
            "examples/irrelevant.py": A,
        },
        "in_scope": ["src/**"],
        "collection_complete": True,
        "collection_errors": [],
    }


def test_exact_current_stale_coverage_uncovered_and_out_of_scope():
    report = ri.analyze_knowledge_applicability(_base_evidence())
    payload = report.to_dict()

    statuses = {
        item["artifact_id"]: item["status"] for item in payload["relations"]
    }
    assert statuses == {
        "covered": "AFFECTED_BY_COVERAGE",
        "exact-current": "CURRENT",
        "exact-stale": "STALE_EXACT_SOURCE",
    }
    assert payload["uncovered_changes"] == ["src/uncovered.py"]
    assert "examples/irrelevant.py" not in payload["uncovered_changes"]
    assert payload["is_complete"] is True
    assert ri.verify_knowledge_applicability_report(payload) is True


def test_missing_source_identity_is_unknown_and_report_incomplete():
    evidence = _base_evidence()
    evidence["knowledge_artifacts"] = [
        {
            "artifact_id": "missing",
            "path": "knowledge/missing.md",
            "source_refs": [
                {
                    "source_path": "src/missing.py",
                    "expected_content_sha256": A,
                }
            ],
            "covers": [],
        }
    ]
    evidence["changes"] = []
    evidence["observed_source_sha256"] = {}

    report = ri.analyze_knowledge_applicability(evidence).to_dict()
    relation = report["relations"][0]
    assert relation["status"] == "UNKNOWN"
    assert relation["reason_codes"] == [
        "SOURCE_IDENTITY_UNOBSERVED:src/missing.py"
    ]
    assert report["is_complete"] is False


def test_rename_and_delete_make_old_exact_sources_stale():
    evidence = _base_evidence()
    evidence["knowledge_artifacts"] = [
        {
            "artifact_id": "renamed",
            "path": "knowledge/renamed.md",
            "source_refs": [
                {
                    "source_path": "src/old.py",
                    "expected_content_sha256": A,
                }
            ],
            "covers": [],
        },
        {
            "artifact_id": "deleted",
            "path": "knowledge/deleted.md",
            "source_refs": [
                {
                    "source_path": "src/deleted.py",
                    "expected_content_sha256": B,
                }
            ],
            "covers": [],
        },
    ]
    evidence["changes"] = [
        {"kind": "RENAME", "old_path": "src/old.py", "path": "src/new.py"},
        {"kind": "DELETE", "old_path": "src/deleted.py", "path": ""},
    ]
    evidence["observed_source_sha256"] = {
        "src/new.py": A,
    }

    report = ri.analyze_knowledge_applicability(evidence).to_dict()
    statuses = {item["artifact_id"]: item["status"] for item in report["relations"]}
    assert statuses == {
        "deleted": "STALE_EXACT_SOURCE",
        "renamed": "STALE_EXACT_SOURCE",
    }
    assert "src/new.py" in report["uncovered_changes"]


def test_broad_cover_is_review_needed_not_semantic_staleness():
    evidence = _base_evidence()
    evidence["knowledge_artifacts"] = [
        {
            "artifact_id": "broad",
            "path": "knowledge/broad.md",
            "source_refs": [],
            "covers": ["src/**"],
        }
    ]
    evidence["changes"] = [{"kind": "MODIFY", "path": "src/unrelated.py"}]
    evidence["observed_source_sha256"] = {"src/unrelated.py": A}

    relation = ri.analyze_knowledge_applicability(evidence).to_dict()["relations"][0]
    assert relation["status"] == "AFFECTED_BY_COVERAGE"
    assert relation["reason_codes"] == [
        "COVERED_PATH_CHANGED:src/unrelated.py"
    ]
    assert all("STALE" not in reason for reason in relation["reason_codes"])


def test_replay_is_deterministic_and_hash_stable():
    first = ri.analyze_knowledge_applicability(_base_evidence()).to_dict()
    second = ri.analyze_knowledge_applicability(_base_evidence()).to_dict()
    assert first == second
    assert first["content_sha256"] == second["content_sha256"]


def test_tampered_derived_relation_rejected_even_with_recomputed_hash():
    payload = ri.analyze_knowledge_applicability(_base_evidence()).to_dict()
    forged = copy.deepcopy(payload)
    forged["relations"][0]["status"] = "CURRENT"
    _rehash(forged)
    assert ri.verify_knowledge_applicability_report(forged) is False


def test_tampered_reason_rejected_even_with_recomputed_hash():
    payload = ri.analyze_knowledge_applicability(_base_evidence()).to_dict()
    forged = copy.deepcopy(payload)
    forged["relations"][0]["reason_codes"] = ["SEMANTICALLY_WRONG"]
    _rehash(forged)
    assert ri.verify_knowledge_applicability_report(forged) is False


def test_substituted_source_identity_without_derived_rebind_is_rejected():
    payload = ri.analyze_knowledge_applicability(_base_evidence()).to_dict()
    forged = copy.deepcopy(payload)
    forged["observed_source_sha256"]["src/stale.py"] = A
    _rehash(forged)
    assert ri.verify_knowledge_applicability_report(forged) is False


def test_invalid_or_stale_revision_fails_closed():
    evidence = _base_evidence()
    evidence["snapshot"]["declared_head_sha"] = "different"
    report = ri.analyze_knowledge_applicability(evidence).to_dict()
    assert report["is_complete"] is False
    assert "REVISION_IDENTITY_INVALID_OR_STALE" in report["evidence_gaps"]
    assert all(item["status"] == "UNKNOWN" for item in report["relations"])


def test_missing_scope_fails_closed_and_reports_no_uncovered_claim():
    evidence = _base_evidence()
    evidence["in_scope"] = []
    report = ri.analyze_knowledge_applicability(evidence).to_dict()
    assert report["is_complete"] is False
    assert "IN_SCOPE_MISSING" in report["evidence_gaps"]
    assert report["uncovered_changes"] == []
