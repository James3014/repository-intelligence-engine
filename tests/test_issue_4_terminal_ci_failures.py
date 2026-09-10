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
