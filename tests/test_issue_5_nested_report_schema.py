import pytest
from repository_intelligence import core as ri
from repository_intelligence.contracts import (
    CLAIM_CEILING,
    EvidenceCompleteness,
    RepositoryIntelligenceReportV1,
)
from repository_intelligence.models import CheckObservation, Disposition, PRSnapshot


def _create_dummy_pr(pr_number: int = 1) -> PRSnapshot:
    return PRSnapshot(
        repository="owner/repo",
        pr_number=pr_number,
        title="Test PR",
        state="open",
        draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="base123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        changed_files=("file1.py",),
        checks=(
            CheckObservation(name="ci", status="success"),
        ),
    )


def test_valid_generated_report_roundtrips_and_verifies():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    assert ri.verify_repository_intelligence_report(payload) is True


def test_recomputed_hash_with_invalid_nested_disposition_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["disposition"] = "NOT_A_REAL_DISPOSITION"
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_invalid_nested_risk_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["risk"] = "INVALID_RISK"
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_invalid_nested_completeness_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["evidence_completeness"] = "BOGUS_COMPLETENESS"
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_non_collection_findings_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["findings"] = "not_a_list"
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_non_string_in_reasons_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["reasons"] = [123, 456]
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_invalid_overlap_shape_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["overlaps"] = "not_a_dict"
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_invalid_overlap_values_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    payload["items"][0]["overlaps"] = {"1": "not_a_list_of_strings"}
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False


def test_recomputed_hash_with_missing_top_level_fields_is_rejected():
    pr = _create_dummy_pr(1)
    report = ri.build_repository_intelligence_report([pr])
    payload = report.to_dict()
    del payload["observed_at"]
    payload["content_sha256"] = ri._content_hash(payload)
    assert ri.verify_repository_intelligence_report(payload) is False
