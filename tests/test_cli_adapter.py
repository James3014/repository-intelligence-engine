"""Tests for the canonical repository_intelligence CLI adapter."""
from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from repository_intelligence.cli import (
    OPERATIONS,
    execute_operation,
    load_input_data,
    main,
)
from repository_intelligence.contracts import (
    CI_EVIDENCE_CLAIM_CEILING,
    CLAIM_CEILING,
)


@pytest.fixture
def sample_revision_snapshot() -> dict:
    return {
        "repository": "owner/repo",
        "pr_number": 42,
        "head_sha": "aaaa1111",
        "base_sha": "bbbb2222",
        "current_main_sha": "bbbb2222",
        "declared_base_sha": "bbbb2222",
        "declared_head_sha": "aaaa1111",
        "declared_main_sha": "bbbb2222",
    }


@pytest.fixture
def sample_readiness_snapshot() -> dict:
    return {
        "repository": "owner/repo",
        "pr_number": 10,
        "head_sha": "h10",
        "base_sha": "b10",
        "current_main_sha": "b10",
        "changed_files": ["docs/readme.md"],
        "labels": [],
        "is_draft": False,
        "mergeable": True,
    }


@pytest.fixture
def sample_overlap_data() -> dict:
    return {
        "snapshots": [
            {
                "repository": "owner/repo",
                "pr_number": 1,
                "head_sha": "h1",
                "base_sha": "m1",
                "current_main_sha": "m1",
                "changed_files": ["pkg/common.py", "pkg/a.py"],
            },
            {
                "repository": "owner/repo",
                "pr_number": 2,
                "head_sha": "h2",
                "base_sha": "m1",
                "current_main_sha": "m1",
                "changed_files": ["pkg/common.py", "pkg/b.py"],
            },
        ]
    }


@pytest.fixture
def sample_ci_snapshot() -> dict:
    return {
        "repository": "owner/repo",
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
        ],
        "collection_complete": True,
        "collection_errors": [],
    }


def test_supported_operations_set() -> None:
    assert OPERATIONS == frozenset({"revision", "readiness", "overlap", "ci"})


def test_execute_operation_revision(sample_revision_snapshot: dict) -> None:
    payload = execute_operation("revision", sample_revision_snapshot)
    assert payload["operation"] == "revision"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    result = payload["result"]
    assert result["repository"] == "owner/repo"
    assert result["pr_number"] == 42
    assert result["is_valid"] is True


def test_execute_operation_readiness(sample_readiness_snapshot: dict) -> None:
    payload = execute_operation("readiness", sample_readiness_snapshot)
    assert payload["operation"] == "readiness"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    result = payload["result"]
    assert result["is_review_ready"] is True
    assert result["disposition"] == "REVIEW_READY"


def test_execute_operation_overlap(sample_overlap_data: dict) -> None:
    # Dict with snapshots key
    payload = execute_operation("overlap", sample_overlap_data)
    assert payload["operation"] == "overlap"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    result = payload["result"]
    assert len(result["overlap_pairs"]) == 1
    assert result["overlap_pairs"][0]["shared_paths"] == ["pkg/common.py"]

    # Direct list
    payload_list = execute_operation("overlap", sample_overlap_data["snapshots"])
    assert payload_list["operation"] == "overlap"
    assert payload_list["claim_ceiling"] == CLAIM_CEILING
    assert len(payload_list["result"]["overlap_pairs"]) == 1


def test_execute_operation_ci(sample_ci_snapshot: dict) -> None:
    payload = execute_operation("ci", sample_ci_snapshot)
    assert payload["operation"] == "ci"
    assert payload["claim_ceiling"] == CI_EVIDENCE_CLAIM_CEILING
    result = payload["result"]
    assert result["unexpected_count"] == 1
    assert result["has_unexpected_failures"] is True


def test_execute_operation_unsupported_or_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown operation: 'impact'"):
        execute_operation("impact", {})

    with pytest.raises(ValueError, match="Unknown operation: 'cfi'"):
        execute_operation("cfi", {})

    with pytest.raises(ValueError, match="Unknown operation: 'eia'"):
        execute_operation("eia", {})

    with pytest.raises(ValueError, match="Input for 'revision' must be a JSON object snapshot mapping"):
        execute_operation("revision", ["not", "a", "dict"])

    with pytest.raises(ValueError, match="Input for 'readiness' must be a JSON object snapshot mapping"):
        execute_operation("readiness", "not a dict")

    with pytest.raises(ValueError, match="Input for 'overlap' must be an object with 'snapshots' list"):
        execute_operation("overlap", "invalid")

    with pytest.raises(ValueError, match="'snapshots' must be a list of PR snapshot mappings"):
        execute_operation("overlap", {"snapshots": "not-a-list"})

    with pytest.raises(ValueError, match="Input for 'ci' must be a JSON object snapshot mapping"):
        execute_operation("ci", 12345)


def test_load_input_data_file(tmp_path: Path) -> None:
    test_file = tmp_path / "input.json"
    test_file.write_text('{"key": "value"}', encoding="utf-8")
    data = load_input_data(str(test_file))
    assert data == {"key": "value"}


def test_load_input_data_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"stdin_key": 999}'))
    data = load_input_data("-")
    assert data == {"stdin_key": 999}


def test_load_input_data_missing_file() -> None:
    with pytest.raises(FileNotFoundError, match="Input file does not exist"):
        load_input_data("/path/to/definitely/nonexistent/file.json")


def test_load_input_data_malformed_json(tmp_path: Path) -> None:
    test_file = tmp_path / "bad.json"
    test_file.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed JSON input"):
        load_input_data(str(test_file))


def test_main_success_file(tmp_path: Path, capsys: pytest.CaptureFixture[str], sample_revision_snapshot: dict) -> None:
    input_file = tmp_path / "revision.json"
    input_file.write_text(json.dumps(sample_revision_snapshot), encoding="utf-8")

    exit_code = main(["--operation", "revision", "--input", str(input_file)])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "revision"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    assert payload["result"]["pr_number"] == 42


def test_main_success_stdin(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], sample_readiness_snapshot: dict) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(sample_readiness_snapshot)))

    exit_code = main(["--operation", "readiness", "--input", "-"])
    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["operation"] == "readiness"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    assert payload["result"]["is_review_ready"] is True


def test_main_error_handling(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["--operation", "invalid_op", "--input", "-"])
    assert exit_code == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "ERROR"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    assert "Argument error" in payload["error"]


def test_subprocess_invocation(tmp_path: Path, sample_ci_snapshot: dict) -> None:
    input_file = tmp_path / "ci_input.json"
    input_file.write_text(json.dumps(sample_ci_snapshot), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "ci", "--input", str(input_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["operation"] == "ci"
    assert payload["claim_ceiling"] == CI_EVIDENCE_CLAIM_CEILING
    assert payload["result"]["unexpected_count"] == 1
