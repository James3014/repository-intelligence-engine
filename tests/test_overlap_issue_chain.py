from __future__ import annotations

from repository_intelligence import overlap
from repository_intelligence.classifier import classify
from repository_intelligence.models import Disposition, PRSnapshot


def _pr(number, issues, files=None):
    return classify(
        PRSnapshot(
            "o/r", number, "t", "open", False, True, "main", "b", f"h{number}",
            f"h{number}", "b", changed_files=tuple(files or (f"f{number}.py",)),
            issue_numbers=tuple(issues),
        )
    )


def test_single_pr_with_repeated_issue_number_is_not_a_chain():
    a = _pr(1, (7, 7))
    assert a.disposition == Disposition.REVIEW_READY
    overlap.detect([a])
    assert "SAME_ISSUE_CHAIN" not in a.findings
    assert a.disposition == Disposition.REVIEW_READY


def test_pr_repeating_an_issue_next_to_an_unrelated_pr_is_not_a_chain():
    a, b = _pr(1, (7, 7, 7)), _pr(2, (8,))
    overlap.detect([a, b])
    assert "SAME_ISSUE_CHAIN" not in a.findings + b.findings
    assert a.disposition == b.disposition == Disposition.REVIEW_READY


def test_two_prs_sharing_issues_get_one_chain_finding_each():
    a, b = _pr(1, (7, 8)), _pr(2, (8, 7, 7))
    overlap.detect([a, b])
    for c in (a, b):
        assert c.findings.count("SAME_ISSUE_CHAIN") == 1
        assert c.reasons.count("multiple active PRs share an Issue") == 1
        assert c.disposition == Disposition.WAIT_REBIND


def test_real_chain_between_two_prs_is_still_detected():
    a, b, c = _pr(1, (7,)), _pr(2, (7,)), _pr(3, (9,))
    overlap.detect([a, b, c])
    assert a.findings.count("SAME_ISSUE_CHAIN") == b.findings.count("SAME_ISSUE_CHAIN") == 1
    assert a.disposition == b.disposition == Disposition.WAIT_REBIND
    assert "SAME_ISSUE_CHAIN" not in c.findings and c.disposition == Disposition.REVIEW_READY
