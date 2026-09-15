from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_dogfooding_corpus.py"
CORPUS = ROOT / "docs" / "dogfooding" / "corpus.v1.json"

spec = importlib.util.spec_from_file_location("validate_dogfooding_corpus", SCRIPT)
assert spec is not None and spec.loader is not None
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def _corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def _report(*, stale=False, readiness_complete="COMPLETE", cfi_complete="COMPLETE", cfi_status="NO_TERMINAL_FAILURE"):
    base = "b" * 40
    current = "c" * 40 if stale else base
    findings = ["STALE_BASE"] if stale else []
    disposition = "STALE" if stale else "REVIEW_READY"
    return {
        "claim_ceiling": "ADVISORY_EVIDENCE_ONLY",
        "review_identity": ["owner/repo", 7, "a" * 40, base, current],
        "reports": {
            "readiness": {
                "result": {
                    "disposition": disposition,
                    "findings": findings,
                    "evidence_completeness": readiness_complete,
                }
            },
            "cfi": {
                "result": {
                    "status": cfi_status,
                    "evidence_completeness": cfi_complete,
                }
            },
        },
    }


def test_canonical_corpus_validates():
    assert validator.validate_corpus(_corpus()) == []


def test_claim_ceiling_fails_closed():
    data = _corpus()
    data["claim_ceiling"] = "MERGE_READY"
    assert any("claim_ceiling" in error for error in validator.validate_corpus(data))


def test_live_fleet_case_requires_exact_head():
    data = _corpus()
    case = next(item for item in data["cases"] if item["case_id"] == "DEVSPACE-158-STALE-BASE")
    case.pop("head_sha")
    assert any("requires exact head_sha" in error for error in validator.validate_corpus(data))


def test_stale_base_requires_distinct_exact_revisions():
    data = _corpus()
    case = next(item for item in data["cases"] if item["case_id"] == "DEVSPACE-158-STALE-BASE")
    case["current_main_sha"] = case["base_sha"]
    assert any("STALE_BASE requires distinct" in error for error in validator.validate_corpus(data))


def test_unknown_evidence_class_is_rejected():
    data = _corpus()
    data["cases"][0]["evidence_class"] = "PRODUCTION_INCIDENT"
    assert any("evidence_class is invalid" in error for error in validator.validate_corpus(data))


def test_fleet_must_cover_exact_eight_repositories():
    data = _corpus()
    data["fleet"].pop()
    assert any("fleet repository set mismatch" in error for error in validator.validate_corpus(data))


def test_extract_stale_report_candidate_is_deterministic():
    report = _report(stale=True)
    first = validator.extract_report_candidates(copy.deepcopy(report))
    second = validator.extract_report_candidates(copy.deepcopy(report))
    assert first == second == [
        {
            "repository": "owner/repo",
            "pr_number": 7,
            "head_sha": "a" * 40,
            "base_sha": "b" * 40,
            "current_main_sha": "c" * 40,
            "failure_family": "STALE_BASE",
            "evidence_class": "LIVE_FLEET_DOGFOOD",
        }
    ]


def test_extract_incomplete_and_unexpected_failure_candidates():
    report = _report(
        readiness_complete="INCOMPLETE",
        cfi_complete="INCOMPLETE",
        cfi_status="UNEXPECTED_FAILURE_OBSERVED",
    )
    candidates = validator.extract_report_candidates(report)
    assert [item["failure_family"] for item in candidates] == [
        "EVIDENCE_INCOMPLETE",
        "UNEXPECTED_TERMINAL_CI_FAILURE",
    ]


def test_extract_rejects_authority_escalated_report():
    report = _report()
    report["claim_ceiling"] = "MERGE_READY"
    with pytest.raises(ValueError, match="claim ceiling"):
        validator.extract_report_candidates(report)
