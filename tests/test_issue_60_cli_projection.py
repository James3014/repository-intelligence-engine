"""Issue #60: canonical CLI projection for knowledge and guard delta."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from repository_intelligence.cli import OPERATIONS, execute_operation
from repository_intelligence.guard_delta import (
    GUARD_SEMANTIC_DELTA_CLAIM_CEILING,
    GUARD_SEMANTIC_DELTA_SCHEMA,
    analyze_guard_semantic_delta,
    verify_guard_semantic_delta_report,
)
from repository_intelligence.knowledge import (
    KNOWLEDGE_APPLICABILITY_CLAIM_CEILING,
    KNOWLEDGE_APPLICABILITY_SCHEMA,
    analyze_knowledge_applicability,
    verify_knowledge_applicability_report,
)


SHA_A = "a" * 64


def _knowledge_evidence() -> dict:
    return {
        "snapshot": {
            "repository": "owner/repo",
            "pr_number": 60,
            "head_sha": "head60",
            "base_sha": "main60",
            "current_main_sha": "main60",
        },
        "knowledge_artifacts": [
            {
                "artifact_id": "current",
                "path": "knowledge/current.md",
                "source_refs": [
                    {
                        "source_path": "src/current.py",
                        "expected_content_sha256": SHA_A,
                    }
                ],
                "covers": [],
            }
        ],
        "changes": [],
        "observed_source_sha256": {"src/current.py": SHA_A},
        "in_scope": ["src/**"],
        "collection_complete": True,
        "collection_errors": [],
    }


def _guard_evidence() -> dict:
    guard = {
        "rules": ["rule:baseline"],
        "enforcement_bindings": ["pre-commit:baseline"],
        "lifecycle_phases": ["pre-commit"],
        "trigger_patterns": ["src/protected/**"],
        "fail_fixtures": ["fixture:baseline"],
        "implementation_sha256": SHA_A,
        "self_test_sha256": SHA_A,
        "wording_sha256": SHA_A,
    }
    return {
        "old_snapshot": {
            "repository": "owner/repo",
            "pr_number": 60,
            "head_sha": "old-head",
            "base_sha": "old-main",
            "current_main_sha": "old-main",
        },
        "new_snapshot": {
            "repository": "owner/repo",
            "pr_number": 60,
            "head_sha": "new-head",
            "base_sha": "new-main",
            "current_main_sha": "new-main",
        },
        "old_guard": guard,
        "new_guard": guard,
        "known_files": ["src/protected/a.py"],
        "behavioral_witnesses": [],
        "collection_complete": True,
        "collection_errors": [],
    }


def test_issue_60_operations_are_registered() -> None:
    assert "knowledge" in OPERATIONS
    assert "guard-delta" in OPERATIONS


def test_execute_knowledge_delegates_to_canonical_analyzer() -> None:
    evidence = _knowledge_evidence()
    expected = analyze_knowledge_applicability(evidence).to_dict()

    payload = execute_operation("knowledge", evidence)

    assert payload["operation"] == "knowledge"
    assert payload["claim_ceiling"] == KNOWLEDGE_APPLICABILITY_CLAIM_CEILING
    assert payload["result"] == expected
    assert payload["result"]["schema"] == KNOWLEDGE_APPLICABILITY_SCHEMA
    assert verify_knowledge_applicability_report(payload["result"]) is True


def test_execute_guard_delta_delegates_to_canonical_analyzer() -> None:
    evidence = _guard_evidence()
    expected = analyze_guard_semantic_delta(evidence).to_dict()

    payload = execute_operation("guard-delta", evidence)

    assert payload["operation"] == "guard-delta"
    assert payload["claim_ceiling"] == GUARD_SEMANTIC_DELTA_CLAIM_CEILING
    assert payload["result"] == expected
    assert payload["result"]["schema"] == GUARD_SEMANTIC_DELTA_SCHEMA
    assert verify_guard_semantic_delta_report(payload["result"]) is True


@pytest.mark.parametrize("operation", ["knowledge", "guard-delta"])
def test_issue_60_operations_reject_non_object_input(operation: str) -> None:
    with pytest.raises(ValueError, match="must be a JSON object mapping"):
        execute_operation(operation, ["not", "an", "object"])


@pytest.mark.parametrize(
    ("operation", "evidence", "claim_ceiling", "schema"),
    [
        (
            "knowledge",
            _knowledge_evidence(),
            KNOWLEDGE_APPLICABILITY_CLAIM_CEILING,
            KNOWLEDGE_APPLICABILITY_SCHEMA,
        ),
        (
            "guard-delta",
            _guard_evidence(),
            GUARD_SEMANTIC_DELTA_CLAIM_CEILING,
            GUARD_SEMANTIC_DELTA_SCHEMA,
        ),
    ],
)
def test_cli_round_trip_preserves_hash_bound_report(
    tmp_path,
    operation: str,
    evidence: dict,
    claim_ceiling: str,
    schema: str,
) -> None:
    input_path = tmp_path / f"{operation}.json"
    input_path.write_text(json.dumps(evidence), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "repository_intelligence.cli",
            "--operation",
            operation,
            "--input",
            str(input_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["operation"] == operation
    assert payload["claim_ceiling"] == claim_ceiling
    assert payload["result"]["schema"] == schema
    assert len(payload["result"]["content_sha256"]) == 64

    expected = (
        analyze_knowledge_applicability(evidence).to_dict()
        if operation == "knowledge"
        else analyze_guard_semantic_delta(evidence).to_dict()
    )
    assert payload["result"]["content_sha256"] == expected["content_sha256"]
