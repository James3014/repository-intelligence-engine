import pytest
from repository_intelligence.classifier import classify
from repository_intelligence.core import classify_readiness
from repository_intelligence.contracts import TERMINAL_FAILURE_STATUSES
from repository_intelligence.models import CheckObservation, Disposition, PRSnapshot


def _create_snapshot_with_check(status: str, expected_failure: bool = False) -> PRSnapshot:
    return PRSnapshot(
        repository="owner/repo",
        pr_number=1,
        title="Test PR",
        state="open",
        draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        checks=(
            CheckObservation(
                name="test-check",
                status=status,
                expected_failure=expected_failure,
            ),
        ),
    )


@pytest.mark.parametrize(
    "status",
    sorted(list(TERMINAL_FAILURE_STATUSES) + ["red", "ERROR", "Cancelled", "TIMED_OUT", "Action_Required"]),
)
def test_unexpected_terminal_failures_produce_unexpected_failure_finding(status: str):
    pr = _create_snapshot_with_check(status, expected_failure=False)
    classification = classify(pr)
    assert "UNEXPECTED_FAILURE" in classification.findings
    assert "EXPECTED_FAILURE" not in classification.findings
    assert classification.disposition == Disposition.REVIEW_READY

    # Also verify through pure core classify_readiness
    readiness = classify_readiness(pr)
    assert "UNEXPECTED_FAILURE" in readiness.findings
    assert "EXPECTED_FAILURE" not in readiness.findings
    assert readiness.disposition == Disposition.REVIEW_READY


@pytest.mark.parametrize(
    "status",
    sorted(list(TERMINAL_FAILURE_STATUSES) + ["red", "ERROR", "Cancelled", "TIMED_OUT", "Action_Required"]),
)
def test_expected_terminal_failures_produce_expected_failure_finding(status: str):
    pr = _create_snapshot_with_check(status, expected_failure=True)
    classification = classify(pr)
    assert "EXPECTED_FAILURE" in classification.findings
    assert "UNEXPECTED_FAILURE" not in classification.findings
    assert classification.disposition == Disposition.REVIEW_READY

    # Also verify through pure core classify_readiness
    readiness = classify_readiness(pr)
    assert "EXPECTED_FAILURE" in readiness.findings
    assert "UNEXPECTED_FAILURE" not in readiness.findings
    assert readiness.disposition == Disposition.REVIEW_READY


@pytest.mark.parametrize(
    "status",
    ["success", "in_progress", "queued", "neutral", "skipped"],
)
def test_non_terminal_statuses_do_not_produce_failure_findings(status: str):
    pr = _create_snapshot_with_check(status, expected_failure=False)
    classification = classify(pr)
    assert "UNEXPECTED_FAILURE" not in classification.findings
    assert "EXPECTED_FAILURE" not in classification.findings
    assert classification.disposition == Disposition.REVIEW_READY


from repository_intelligence.core import fingerprint_ci_failures


def _create_rich_snapshot_with_check(
    status: str,
    expected_failure: bool = False,
    head_sha: str = "head123",
    check_run_id: int = 1001,
) -> PRSnapshot:
    return PRSnapshot(
        repository="owner/repo",
        pr_number=1,
        title="Test PR",
        state="open",
        draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        checks=(
            CheckObservation(
                name="build-check",
                status=status,
                expected_failure=expected_failure,
                head_sha=head_sha,
                check_run_id=check_run_id,
                run_id=2001,
            ),
        ),
    )


@pytest.mark.parametrize(
    "status",
    sorted(list(TERMINAL_FAILURE_STATUSES) + ["red", "RED", "Red", "ERROR", "Cancelled", "TIMED_OUT", "Action_Required"]),
)
def test_cross_entrypoint_unexpected_failure_consistency(status: str):
    pr = _create_rich_snapshot_with_check(status, expected_failure=False)
    # 1. Advisory classification
    readiness = classify_readiness(pr)
    assert "UNEXPECTED_FAILURE" in readiness.findings
    assert "EXPECTED_FAILURE" not in readiness.findings
    assert readiness.disposition == Disposition.REVIEW_READY

    # 2. CI failure fingerprinting
    fp = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    assert fp.has_unexpected_failures is True
    assert len(fp.unexpected_failures) == 1
    assert len(fp.expected_failures) == 0
    assert fp.unexpected_failures[0].name == "build-check"
    assert fp.unexpected_count == 1
    assert fp.expected_count == 0


@pytest.mark.parametrize(
    "status",
    sorted(list(TERMINAL_FAILURE_STATUSES) + ["red", "RED", "Red", "ERROR", "Cancelled", "TIMED_OUT", "Action_Required"]),
)
def test_cross_entrypoint_expected_failure_consistency(status: str):
    pr = _create_rich_snapshot_with_check(status, expected_failure=True)
    # 1. Advisory classification
    readiness = classify_readiness(pr)
    assert "EXPECTED_FAILURE" in readiness.findings
    assert "UNEXPECTED_FAILURE" not in readiness.findings
    assert readiness.disposition == Disposition.REVIEW_READY

    # 2. CI failure fingerprinting
    fp = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    assert fp.has_unexpected_failures is False
    assert len(fp.unexpected_failures) == 0
    assert len(fp.expected_failures) == 1
    assert fp.expected_failures[0].name == "build-check"
    assert fp.unexpected_count == 0
    assert fp.expected_count == 1


@pytest.mark.parametrize(
    "status",
    ["success", "in_progress", "queued", "neutral", "skipped"],
)
def test_cross_entrypoint_non_terminal_consistency(status: str):
    pr = _create_rich_snapshot_with_check(status, expected_failure=False)
    readiness = classify_readiness(pr)
    assert "UNEXPECTED_FAILURE" not in readiness.findings
    assert "EXPECTED_FAILURE" not in readiness.findings

    fp = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    assert fp.has_unexpected_failures is False
    assert len(fp.unexpected_failures) == 0
    assert len(fp.expected_failures) == 0


def test_fingerprint_deterministic_and_idempotent():
    pr = _create_rich_snapshot_with_check("red", expected_failure=False)
    fp1 = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    fp2 = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    assert fp1.fingerprint == fp2.fingerprint
    assert fp1.content_sha256 == fp2.content_sha256
    assert len(fp1.fingerprint) == 64


def test_fingerprint_foreign_evidence_gaps_for_red_status():
    pr = _create_rich_snapshot_with_check("red", expected_failure=False, check_run_id=9999)
    fp = fingerprint_ci_failures(pr, expected_check_run_id=1001)
    assert "foreign check identity" in fp.evidence_gaps
    assert fp.is_complete is False
