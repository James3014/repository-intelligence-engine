"""Generic protected-path policy defaults empty (Issue #80)."""
from __future__ import annotations

from repository_intelligence.classifier import DEFAULT_AUTHORITY_PATTERNS, classify
from repository_intelligence.models import PRSnapshot

NEXUS_PATTERNS = ("AGENTS.md", "docs/agents/", "docs/governance/", "policy/")


def _snapshot(*changed_files: str) -> PRSnapshot:
    return PRSnapshot(
        repository="owner/repo",
        pr_number=80,
        title="Touch governed paths",
        state="open",
        draft=False,
        mergeable=True,
        base_branch="main",
        base_sha="main123",
        head_branch="feature",
        head_sha="head123",
        current_main_sha="main123",
        changed_files=tuple(changed_files),
    )


def test_default_authority_patterns_is_empty_but_importable() -> None:
    assert DEFAULT_AUTHORITY_PATTERNS == ()


def test_default_classify_does_not_flag_nexus_paths() -> None:
    result = classify(_snapshot("AGENTS.md", "policy/rules.md", "docs/governance/x.md", "docs/agents/y.md"))
    assert "AUTHORITY_OVERLAP" not in result.findings
    assert result.risk != "HIGH"


def test_explicit_patterns_still_flag_authority_overlap_high_risk() -> None:
    for path in ("AGENTS.md", "policy/rules.md", "docs/governance/x.md", "docs/agents/y.md"):
        result = classify(_snapshot(path), authority_patterns=NEXUS_PATTERNS)
        assert "AUTHORITY_OVERLAP" in result.findings
        assert result.risk == "HIGH"
