"""mergeable=None is an evidence gap, never REVIEW_READY (RIE-2)."""
from __future__ import annotations

import pytest

from repository_intelligence.classifier import classify
from repository_intelligence.core import classify_readiness
from repository_intelligence.models import Disposition, PRSnapshot


def _snapshot(mergeable, **overrides) -> PRSnapshot:
    fields = dict(
        repository="owner/repo",
        pr_number=9,
        title="Docs tweak",
        state="open",
        draft=False,
        mergeable=mergeable,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        changed_files=("docs/readme.md",),
    )
    fields.update(overrides)
    return PRSnapshot(**fields)


def _mapping(mergeable) -> dict:
    return {
        "repository": "owner/repo",
        "pr_number": 9,
        "state": "open",
        "is_draft": False,
        "mergeable": mergeable,
        "base_branch": "main",
        "base_sha": "main123",
        "head_branch": "feature",
        "head_sha": "head123",
        "current_main_sha": "main123",
        "changed_files": ["docs/readme.md"],
        "labels": [],
    }


def test_unknown_mergeable_is_not_review_ready_for_snapshot() -> None:
    result = classify_readiness(_snapshot(None))
    assert "MERGEABLE_UNKNOWN" in result.findings
    assert result.disposition == Disposition.NEEDS_ATTENTION
    assert result.is_review_ready is False
    assert result.evidence_completeness.value == "PARTIAL"
    assert "mergeable state unknown" in result.evidence_gaps


def test_unknown_mergeable_is_not_review_ready_for_mapping() -> None:
    result = classify_readiness(_mapping(None))
    assert result.disposition == Disposition.NEEDS_ATTENTION
    assert result.is_review_ready is False


def test_missing_mergeable_key_is_treated_as_unknown() -> None:
    data = _mapping(None)
    del data["mergeable"]
    result = classify_readiness(data)
    assert result.is_review_ready is False
    assert "MERGEABLE_UNKNOWN" in result.findings


def test_classifier_marks_unknown_mergeable_as_blocker() -> None:
    classification = classify(_snapshot(None))
    assert "MERGEABLE_UNKNOWN" in classification.findings
    assert classification.disposition == Disposition.NEEDS_ATTENTION


@pytest.mark.parametrize("mergeable", [True])
def test_known_mergeable_still_review_ready(mergeable) -> None:
    result = classify_readiness(_snapshot(mergeable))
    assert "MERGEABLE_UNKNOWN" not in result.findings
    assert result.disposition == Disposition.REVIEW_READY
    assert result.evidence_completeness.value == "COMPLETE"


def test_known_non_mergeable_still_excluded_not_needs_attention() -> None:
    result = classify_readiness(_snapshot(False))
    assert "NON_MERGEABLE" in result.findings
    assert "MERGEABLE_UNKNOWN" not in result.findings
    assert result.disposition == Disposition.EXCLUDED
