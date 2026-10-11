"""Regression tests: classify_readiness must apply PR body DO_NOT_MERGE rules (RIE-1).

Also pins the existing design that declared_*_sha values are never parsed out of
PR body prose on the mapping input path (see _coerce_snapshot).
"""
from __future__ import annotations

import pytest

from repository_intelligence.core import classify_readiness
from repository_intelligence.models import Disposition, PRSnapshot

HEX40 = "e" * 40


def _snapshot(**overrides) -> PRSnapshot:
    fields = dict(
        repository="owner/repo",
        pr_number=7,
        title="Docs tweak",
        state="open",
        draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        changed_files=("docs/readme.md",),
        body="",
    )
    fields.update(overrides)
    return PRSnapshot(**fields)


def _mapping(**overrides) -> dict:
    data = dict(
        repository="owner/repo",
        pr_number=7,
        title="Docs tweak",
        state="open",
        is_draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        changed_files=["docs/readme.md"],
        labels=[],
    )
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "body",
    [
        "DO NOT MERGE until the migration lands",
        "do not merge",
        "Status: Do Not Merge",
    ],
)
def test_do_not_merge_in_body_is_not_review_ready_for_snapshot(body: str) -> None:
    result = classify_readiness(_snapshot(body=body))
    assert "DO_NOT_MERGE" in result.findings
    assert result.disposition == Disposition.EVIDENCE_ONLY
    assert result.is_review_ready is False


def test_do_not_merge_in_body_is_not_review_ready_for_mapping() -> None:
    result = classify_readiness(_mapping(body="DO NOT MERGE"))
    assert "DO_NOT_MERGE" in result.findings
    assert result.is_review_ready is False


def test_clean_body_stays_review_ready() -> None:
    result = classify_readiness(_snapshot(body="Adds a paragraph to the readme."))
    assert "DO_NOT_MERGE" not in result.findings
    assert result.disposition == Disposition.REVIEW_READY


def test_mapping_body_does_not_parse_declared_sha_from_prose() -> None:
    # Declared identity must come from structured fields only. A body that merely
    # mentions a SHA must not create a declared head and trigger stale evidence.
    result = classify_readiness(_mapping(body=f"exact head: {HEX40}"))
    assert result.identity.declared_head_sha is None
    assert result.identity.stale_declared_head is False
    assert result.is_review_ready is True
