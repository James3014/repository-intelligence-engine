"""Adapter-consumer compatibility verification harness for repository_intelligence.

This test suite validates that external adapters and consumers (e.g. CLI, reviewers,
automation bots, MCP servers) can import the canonical repository_intelligence package
and exercise representative operations across all public V1.1 surfaces without requiring
any adapter-specific logic in Core.
"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from types import MappingProxyType
from typing import Any

import pytest

import repository_intelligence as ri
from repository_intelligence.contracts import (
    CI_EVIDENCE_CLAIM_CEILING,
    CLAIM_CEILING,
    CIFailureFingerprint,
    CIFailureIntelligenceReportV1,
    CIFailureTriageStatus,
    ChangeImpactReportV1,
    CrossPROverlapResult,
    Disposition,
    EvidenceCompleteness,
    ExternalIntelligenceAutomationEnvelopeV1,
    ExternalIntelligenceDecision,
    NormalizedCheckEvidence,
    ReadinessClassification,
    RepositoryIntelligencePolicyV1,
    RepositoryIntelligenceReportV1,
    RevisionIdentity,
)


# ============================================================================
# 1. Adapter Importability and Facade Surface
# ============================================================================


def test_adapter_can_import_public_facade_symbols() -> None:
    """Verify that consumer adapters can access all public operations and contracts."""
    expected_public_symbols = {
        "CLAIM_CEILING",
        "CI_EVIDENCE_CLAIM_CEILING",
        "TERMINAL_FAILURE_STATUSES",
        "Disposition",
        "EvidenceCompleteness",
        "RepositoryIntelligencePolicyV1",
        "RevisionIdentity",
        "ReadinessClassification",
        "CrossPROverlapResult",
        "NormalizedCheckEvidence",
        "CIFailureFingerprint",
        "CIFailureTriageStatus",
        "CIFailureIntelligenceReportV1",
        "ChangeImpactReportV1",
        "ExternalIntelligenceDecision",
        "ExternalIntelligenceAutomationEnvelopeV1",
        "RepositoryIntelligenceReportV1",
        "revision_identity",
        "classify_readiness",
        "analyze_cross_pr_overlap",
        "fingerprint_ci_failures",
        "verify_ci_failure_evidence",
        "analyze_change_impact",
        "verify_change_impact_report",
        "analyze_ci_failure_intelligence",
        "verify_ci_failure_intelligence_report",
        "plan_external_intelligence_automation",
        "verify_external_intelligence_automation_envelope",
        "build_repository_intelligence_report",
        "verify_repository_intelligence_report",
    }
    for symbol in expected_public_symbols:
        assert hasattr(ri, symbol), f"Public symbol {symbol} missing from repository_intelligence"


# ============================================================================
# 2. Revision Identity and Stale Evidence Detection Contract
# ============================================================================


def test_adapter_revision_identity_from_plain_dict() -> None:
    """Validate that adapters can pass plain dicts to extract revision identity."""
    raw_snapshot = {
        "repository": "owner/repo",
        "pr_number": 42,
        "head_sha": "aaaa1111",
        "base_sha": "bbbb2222",
        "current_main_sha": "bbbb2222",
        "declared_base_sha": "bbbb2222",
        "declared_head_sha": "aaaa1111",
        "declared_main_sha": "bbbb2222",
    }
    rev_id = ri.revision_identity(raw_snapshot)
    assert isinstance(rev_id, RevisionIdentity)
    assert rev_id.repository == "owner/repo"
    assert rev_id.pr_number == 42
    assert rev_id.head_sha == "aaaa1111"
    assert rev_id.base_sha == "bbbb2222"
    assert rev_id.current_main_sha == "bbbb2222"
    assert rev_id.review_identity == ("owner/repo", 42, "aaaa1111", "bbbb2222", "bbbb2222")
    assert rev_id.is_valid is True
    assert rev_id.stale_base is False
    assert rev_id.stale_evidence is False
    assert rev_id.evidence_gaps == ()

    # Serialization check
    data = rev_id.to_dict()
    assert json.loads(json.dumps(data)) == data


def test_adapter_revision_identity_stale_detection() -> None:
    """Validate detection of stale base and stale declared evidence."""
    stale_snapshot = {
        "repository": "owner/repo",
        "pr_number": 100,
        "head_sha": "head001",
        "base_sha": "base001",
        "current_main_sha": "main999",  # base differs from main
        "declared_head_sha": "head_old",  # declared head differs from actual head
    }
    rev_id = ri.revision_identity(stale_snapshot)
    assert rev_id.is_valid is True
    assert rev_id.stale_base is True
    assert rev_id.stale_declared_head is True
    assert rev_id.stale_evidence is True


def test_adapter_revision_identity_invalid_inputs() -> None:
    """Validate gap detection for malformed adapter inputs."""
    invalid_snapshot = {
        "repository": "invalid_repo_without_slash",
        "pr_number": -5,
        "head_sha": "",
        "base_sha": "",
        "current_main_sha": "",
    }
    rev_id = ri.revision_identity(invalid_snapshot)
    assert rev_id.is_valid is False
    assert len(rev_id.evidence_gaps) >= 4


# ============================================================================
# 3. Readiness Classification and Consumer Policy Contract
# ============================================================================


def test_adapter_classify_readiness_with_custom_policy() -> None:
    """Validate that adapters can inject custom policies (protected paths, stale labels)."""
    snapshot = {
        "repository": "org/service",
        "pr_number": 12,
        "head_sha": "h1234",
        "base_sha": "m5678",
        "current_main_sha": "m5678",
        "changed_files": ["src/critical/auth.py", "docs/guide.md"],
        "labels": ["custom-stale-tag"],
        "is_draft": False,
        "mergeable": True,
    }

    custom_policy = RepositoryIntelligencePolicyV1(
        protected_path_patterns=("src/critical/",),
        stale_labels=("custom-stale-tag",),
    )

    result = ri.classify_readiness(snapshot, policy=custom_policy)
    assert isinstance(result, ReadinessClassification)
    assert result.claim_ceiling == CLAIM_CEILING
    assert result.disposition == Disposition.STALE
    assert "STALE_LONG_LIVED" in result.findings
    assert "AUTHORITY_OVERLAP" in result.findings
    assert result.risk == "HIGH"
    assert result.is_review_ready is False

    # Invariants: dataclass immutability
    with pytest.raises(FrozenInstanceError):
        result.risk = "LOW"  # type: ignore[misc]

    # Serialization check
    serialized = result.to_dict()
    assert json.loads(json.dumps(serialized)) == serialized


def test_adapter_classify_readiness_ready_pr() -> None:
    """Validate clean review readiness classification."""
    snapshot = {
        "repository": "org/service",
        "pr_number": 15,
        "head_sha": "h1234",
        "base_sha": "m5678",
        "current_main_sha": "m5678",
        "changed_files": ["docs/readme.md"],
        "labels": [],
        "is_draft": False,
        "mergeable": True,
    }
    result = ri.classify_readiness(snapshot)
    assert result.disposition == Disposition.REVIEW_READY
    assert result.is_review_ready is True
    assert result.evidence_completeness == EvidenceCompleteness.COMPLETE
    assert result.evidence_gaps == ()


# ============================================================================
# 4. Cross-PR Overlap Analysis Contract
# ============================================================================


def test_adapter_cross_pr_overlap_analysis() -> None:
    """Validate multi-PR overlap detection from adapter snapshot batches."""
    pr1 = {
        "repository": "org/repo",
        "pr_number": 101,
        "head_sha": "h1",
        "base_sha": "m1",
        "current_main_sha": "m1",
        "changed_files": ["shared/api.py", "module1/code.py"],
    }
    pr2 = {
        "repository": "org/repo",
        "pr_number": 102,
        "head_sha": "h2",
        "base_sha": "m1",
        "current_main_sha": "m1",
        "changed_files": ["shared/api.py", "module2/code.py"],
    }
    pr3 = {
        "repository": "org/repo",
        "pr_number": 103,
        "head_sha": "h3",
        "base_sha": "m1",
        "current_main_sha": "m1",
        "changed_files": ["independent/file.py"],
    }

    overlap_result = ri.analyze_cross_pr_overlap([pr1, pr2, pr3])
    assert isinstance(overlap_result, CrossPROverlapResult)
    assert overlap_result.claim_ceiling == CLAIM_CEILING
    assert len(overlap_result.classifications) == 3
    assert len(overlap_result.overlap_pairs) == 1
    assert overlap_result.overlap_pairs[0] == (101, 102, ("shared/api.py",))

    # Serialization check
    data = overlap_result.to_dict()
    encoded = json.dumps(data)
    decoded = json.loads(encoded)
    assert decoded["claim_ceiling"] == CLAIM_CEILING
    assert len(decoded["overlap_pairs"]) == 1
    assert decoded["overlap_pairs"][0]["shared_paths"] == ["shared/api.py"]


# ============================================================================
# 5. CI Failure Fingerprinting & Verification Contract
# ============================================================================


def test_adapter_ci_failure_fingerprint_and_verification() -> None:
    """Validate CI failure fingerprint calculation and verification roundtrip."""
    snapshot = {
        "repository": "org/repo",
        "pr_number": 77,
        "head_sha": "head777",
        "base_sha": "main000",
        "current_main_sha": "main000",
        "checks": [
            {
                "name": "lint",
                "status": "success",
                "head_sha": "head777",
                "check_run_id": 1001,
            },
            {
                "name": "pytest",
                "status": "failure",
                "head_sha": "head777",
                "check_run_id": 1002,
                "workflow_name": "CI",
            },
            {
                "name": "flaky-e2e",
                "status": "failure",
                "expected_failure": True,
                "head_sha": "head777",
                "check_run_id": 1003,
            },
        ],
        "collection_complete": True,
        "collection_errors": [],
    }

    fp = ri.fingerprint_ci_failures(snapshot)
    assert isinstance(fp, CIFailureFingerprint)
    assert fp.claim_ceiling == CI_EVIDENCE_CLAIM_CEILING
    assert fp.total_checks_count == 3
    assert fp.unexpected_count == 1
    assert fp.expected_count == 1
    assert fp.terminal_failure_count == 2
    assert fp.has_unexpected_failures is True
    assert fp.is_complete is True
    assert fp.evidence_completeness == EvidenceCompleteness.COMPLETE
    assert len(fp.content_sha256) == 64

    # Verify through public contract
    payload = fp.to_dict()
    assert ri.verify_ci_failure_evidence(payload) is True

    # Tampering test: modified status must fail verification
    tampered = dict(payload)
    tampered["unexpected_count"] = 0
    assert ri.verify_ci_failure_evidence(tampered) is False


# ============================================================================
# 6. Change Impact Analysis & Verification Contract
# ============================================================================


def test_adapter_change_impact_analysis_and_verification() -> None:
    """Validate language-neutral change impact analysis and verifier."""
    graph_evidence = {
        "snapshot": {
            "repository": "org/repo",
            "pr_number": 50,
            "head_sha": "h50",
            "base_sha": "m50",
            "current_main_sha": "m50",
            "changed_files": ["pkg/leaf.py"],
        },
        "covered_files": ["pkg/leaf.py", "pkg/mid.py", "pkg/root.py", "pkg/unrelated.py"],
        "dependency_edges": [
            {"consumer": "pkg/mid.py", "dependency": "pkg/leaf.py"},
            {"consumer": "pkg/root.py", "dependency": "pkg/mid.py"},
        ],
        "observed_symbols": {
            "pkg/leaf.py": ["compute_value"],
        },
        "graph_complete": True,
        "graph_errors": [],
    }

    report = ri.analyze_change_impact(graph_evidence)
    assert isinstance(report, ChangeImpactReportV1)
    assert report.claim_ceiling == CLAIM_CEILING
    assert report.direct_impacted_files == ("pkg/mid.py",)
    assert report.transitive_impacted_files == ("pkg/root.py",)
    assert report.all_impacted_files == ("pkg/leaf.py", "pkg/mid.py", "pkg/root.py")
    assert report.direct_impacted_count == 1
    assert report.transitive_impacted_count == 1
    assert report.total_impacted_count == 3
    assert report.is_complete is True
    assert report.evidence_completeness == EvidenceCompleteness.COMPLETE

    payload = report.to_dict()
    assert ri.verify_change_impact_report(payload) is True

    # Tampered count must fail verifier
    tampered = dict(payload)
    tampered["direct_impacted_count"] = 99
    assert ri.verify_change_impact_report(tampered) is False


# ============================================================================
# 7. CI Failure Intelligence (CFI) Contract
# ============================================================================


def test_adapter_ci_failure_intelligence_triage() -> None:
    """Validate CI failure intelligence triage and verifier."""
    snapshot = {
        "repository": "org/repo",
        "pr_number": 88,
        "head_sha": "h88",
        "base_sha": "m88",
        "current_main_sha": "m88",
        "checks": [
            {
                "name": "unit-tests",
                "status": "failure",
                "head_sha": "h88",
                "check_run_id": 9901,
            }
        ],
        "collection_complete": True,
        "collection_errors": [],
    }

    cfi_report = ri.analyze_ci_failure_intelligence(snapshot)
    assert isinstance(cfi_report, CIFailureIntelligenceReportV1)
    assert cfi_report.claim_ceiling == CI_EVIDENCE_CLAIM_CEILING
    assert cfi_report.status == CIFailureTriageStatus.UNEXPECTED_FAILURE_OBSERVED
    assert cfi_report.diagnosis_eligible is True
    assert cfi_report.failed_check_names == ("unit-tests",)
    assert cfi_report.reason_codes == ("UNEXPECTED_TERMINAL_FAILURE",)

    payload = cfi_report.to_dict()
    assert ri.verify_ci_failure_intelligence_report(payload) is True

    # Tampering eligibility must fail verifier
    tampered = dict(payload)
    tampered["diagnosis_eligible"] = False
    assert ri.verify_ci_failure_intelligence_report(tampered) is False


# ============================================================================
# 8. External Intelligence Automation (EIA) Envelope Contract
# ============================================================================


def test_adapter_external_intelligence_automation_plan() -> None:
    """Validate EIA envelope planning and verifier."""
    snapshot = {
        "repository": "org/repo",
        "pr_number": 99,
        "head_sha": "h99",
        "base_sha": "m99",
        "current_main_sha": "m99",
        "checks": [
            {
                "name": "integration-tests",
                "status": "failure",
                "head_sha": "h99",
                "check_run_id": 5555,
            }
        ],
        "collection_complete": True,
        "collection_errors": [],
    }

    envelope = ri.plan_external_intelligence_automation({"snapshot": snapshot})
    assert isinstance(envelope, ExternalIntelligenceAutomationEnvelopeV1)
    assert envelope.claim_ceiling == "AUTOMATION_ADVISORY_ONLY"
    assert envelope.decision == ExternalIntelligenceDecision.READY
    assert envelope.action_kind == "CI_FAILURE_DIAGNOSIS"
    assert len(envelope.idempotency_key) == 64
    assert len(envelope.evidence_refs) == 1

    payload = envelope.to_dict()
    assert ri.verify_external_intelligence_automation_envelope(payload) is True

    # Stale identity blocks automation
    stale_snapshot = dict(snapshot, base_sha="stale_base_sha")
    stale_envelope = ri.plan_external_intelligence_automation({"snapshot": stale_snapshot})
    assert stale_envelope.decision == ExternalIntelligenceDecision.BLOCKED
    assert stale_envelope.action_kind == "NONE"
    assert "IDENTITY_STALE_FOR_AUTOMATION" in stale_envelope.reason_codes
    assert ri.verify_external_intelligence_automation_envelope(stale_envelope.to_dict()) is True


# ============================================================================
# 9. Repository Intelligence Report Aggregation Contract
# ============================================================================


def test_adapter_build_repository_intelligence_report() -> None:
    """Validate full repository-level report generation and verification."""
    pr1 = {
        "repository": "org/repo",
        "pr_number": 1,
        "head_sha": "h1",
        "base_sha": "main_sha",
        "current_main_sha": "main_sha",
        "changed_files": ["app/main.py"],
        "observed_at": "2026-08-30T12:00:00Z",
    }
    pr2 = {
        "repository": "org/repo",
        "pr_number": 2,
        "head_sha": "h2",
        "base_sha": "main_sha",
        "current_main_sha": "main_sha",
        "changed_files": ["app/utils.py"],
        "observed_at": "2026-08-30T12:01:00Z",
    }

    report = ri.build_repository_intelligence_report([pr1, pr2])
    assert isinstance(report, RepositoryIntelligenceReportV1)
    assert report.claim_ceiling == CLAIM_CEILING
    assert report.repository == "org/repo"
    assert report.current_main_sha == "main_sha"
    assert report.observed_at == "2026-08-30T12:01:00Z"
    assert len(report.items) == 2
    assert report.evidence_completeness == EvidenceCompleteness.COMPLETE
    assert report.evidence_gaps == ()

    payload = report.to_dict()
    assert ri.verify_repository_intelligence_report(payload) is True


# ============================================================================
# 10. Adapter Decoupling & Pure In-Memory Invariants
# ============================================================================


def test_adapter_mapping_compatibility() -> None:
    """Validate that custom adapter mapping types (e.g. dict, MappingProxyType) are consumed."""
    custom_dict = {
        "repository": "custom/repo",
        "pr_number": 300,
        "head_sha": "head_cust",
        "base_sha": "main_cust",
        "current_main_sha": "main_cust",
        "declared_base_sha": "main_cust",
        "declared_head_sha": "head_cust",
        "declared_main_sha": "main_cust",
        "changed_files": ["custom.txt"],
        "labels": [],
        "draft": False,
        "mergeable": True,
        "checks": [],
        "collection_complete": True,
        "collection_errors": [],
    }
    rev_id = ri.revision_identity(custom_dict)
    assert rev_id.is_valid is True
    assert rev_id.repository == "custom/repo"

    classification = ri.classify_readiness(MappingProxyType(custom_dict))
    assert classification.is_review_ready is True
    assert classification.disposition == Disposition.REVIEW_READY
