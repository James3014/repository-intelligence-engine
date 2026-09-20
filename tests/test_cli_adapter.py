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
    REPOSITORY_FACTS_CLAIM_CEILING,
    REPOSITORY_QUERY_CLAIM_CEILING,
)
from repository_intelligence.eia import AUTOMATION_CLAIM_CEILING


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


@pytest.fixture
def sample_impact_data() -> dict:
    return {
        "snapshot": {
            "repository": "owner/repo",
            "pr_number": 50,
            "head_sha": "h50",
            "base_sha": "m50",
            "current_main_sha": "m50",
            "changed_files": ["pkg/leaf.py"],
        },
        "covered_files": ["pkg/leaf.py", "pkg/mid.py", "pkg/root.py"],
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


@pytest.fixture
def sample_cfi_snapshot() -> dict:
    return {
        "repository": "owner/repo",
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


@pytest.fixture
def sample_eia_data(sample_cfi_snapshot: dict) -> dict:
    return {
        "snapshot": sample_cfi_snapshot,
    }


@pytest.fixture
def sample_facts_data() -> dict:
    return {
        "snapshot": {
            "repository": "owner/repo",
            "pr_number": 42,
            "head_sha": "aaaa1111",
            "base_sha": "bbbb2222",
            "current_main_sha": "bbbb2222",
            "declared_base_sha": "bbbb2222",
            "declared_head_sha": "aaaa1111",
            "changed_files": ["pkg/util.py", "tests/test_util.py"],
        },
        "language": "python",
        "covered_files": ["pkg/util.py"],
        "detector_version": "python-ast-v1",
        "detector_coverage": {
            "EMPTY_EXCEPTION_HANDLER": True,
            "BROAD_EXCEPTION_HANDLER": True,
            "SUBPROCESS_CALL": True,
            "SILENT_RETRY_PATTERN": True,
            "HARDCODED_LOCALHOST": True,
        },
        "observations": [
            {
                "fact_kind": "EMPTY_EXCEPTION_HANDLER",
                "file_path": "pkg/util.py",
                "line": 3,
                "column": 0,
                "evidence_ref": "empty_except_handler",
            }
        ],
        "collection_complete": True,
        "collection_errors": [],
    }


@pytest.fixture
def sample_query_data() -> dict:
    return {
        "snapshot": {
            "repository": "owner/repo",
            "pr_number": 42,
            "head_sha": "aaaa1111",
            "base_sha": "bbbb2222",
            "current_main_sha": "bbbb2222",
            "declared_base_sha": "bbbb2222",
            "declared_head_sha": "aaaa1111",
        },
        "query_id": "symbols:revision_identity",
        "query_digest": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
        "index_identity": {
            "index_id": "python-ast-symbols-v1",
            "index_revision": "idx-42",
            "backend_id": "stdlib-pointer",
        },
        "retrievers": [
            {
                "identity": {
                    "retriever_id": "exact_symbol",
                    "index_id": "python-ast-symbols-v1",
                    "index_revision": "idx-42",
                    "retriever_version": "v1",
                },
                "ranked_candidates": [
                    {
                        "candidate_ref": "pkg/core.py::revision_identity",
                        "source_rank": 1,
                        "source_score": 1.0,
                        "evidence_ref": "symbol-index:pkg/core.py:revision_identity",
                        "match_class": "EXACT",
                    }
                ],
                "complete": True,
                "source_hits": 1,
                "errors": [],
            }
        ],
        "required_candidates": 5,
        "collection_complete": True,
        "collection_errors": [],
    }


def test_supported_operations_set() -> None:
    assert OPERATIONS == frozenset({"revision", "readiness", "overlap", "ci", "impact", "cfi", "eia", "facts", "query"})


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


def test_execute_operation_impact(sample_impact_data: dict) -> None:
    payload = execute_operation("impact", sample_impact_data)
    assert payload["operation"] == "impact"
    assert payload["claim_ceiling"] == CLAIM_CEILING
    result = payload["result"]
    assert result["direct_impacted_files"] == ["pkg/mid.py"]
    assert result["transitive_impacted_files"] == ["pkg/root.py"]
    assert result["all_impacted_files"] == ["pkg/leaf.py", "pkg/mid.py", "pkg/root.py"]
    assert result["direct_impacted_count"] == 1
    assert result["is_complete"] is True


def test_execute_operation_cfi(sample_cfi_snapshot: dict) -> None:
    payload = execute_operation("cfi", sample_cfi_snapshot)
    assert payload["operation"] == "cfi"
    assert payload["claim_ceiling"] == CI_EVIDENCE_CLAIM_CEILING
    result = payload["result"]
    assert result["status"] == "UNEXPECTED_FAILURE_OBSERVED"
    assert result["diagnosis_eligible"] is True
    assert result["failed_check_names"] == ["unit-tests"]


def test_execute_operation_eia(sample_eia_data: dict) -> None:
    payload = execute_operation("eia", sample_eia_data)
    assert payload["operation"] == "eia"
    assert payload["claim_ceiling"] == AUTOMATION_CLAIM_CEILING
    result = payload["result"]
    assert result["decision"] == "READY"
    assert result["action_kind"] == "CI_FAILURE_DIAGNOSIS"


def test_execute_operation_facts(sample_facts_data: dict) -> None:
    payload = execute_operation("facts", sample_facts_data)
    assert payload["operation"] == "facts"
    assert payload["claim_ceiling"] == REPOSITORY_FACTS_CLAIM_CEILING
    result = payload["result"]
    assert result["schema"] == "reviewer.structured_facts.v1"
    assert result["is_complete"] is True
    statuses = {fact["fact_kind"]: fact["status"] for fact in result["facts"]}
    assert statuses["EMPTY_EXCEPTION_HANDLER"] == "PROVEN"
    assert statuses["NETWORK_ENDPOINT_ADDED"] == "UNKNOWN"
    assert statuses["RELATED_TEST_CHANGED"] == "PROVEN"

    with pytest.raises(ValueError, match="Input for 'facts' must be a JSON object mapping"):
        execute_operation("facts", ["not", "a", "dict"])


def test_execute_operation_query(sample_query_data: dict) -> None:
    payload = execute_operation("query", sample_query_data)
    assert payload["operation"] == "query"
    assert payload["claim_ceiling"] == REPOSITORY_QUERY_CLAIM_CEILING
    result = payload["result"]
    assert result["schema"] == "reviewer.repository_query_evidence.v1"
    assert result["resolution"] == "EXACT_RESOLUTION"
    assert result["is_complete"] is True
    assert result["semantic_review_needed"] is False
    assert result["exact_match_count"] == 1
    assert result["distinct_candidate_count"] == 1

    with pytest.raises(ValueError, match="Input for 'query' must be a JSON object mapping"):
        execute_operation("query", "not a dict")


def test_execute_operation_unsupported_or_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown operation: 'unknown_op'"):
        execute_operation("unknown_op", {})

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

    with pytest.raises(ValueError, match="Input for 'impact' must be a JSON object mapping"):
        execute_operation("impact", ["not", "a", "dict"])

    with pytest.raises(ValueError, match="Input for 'cfi' must be a JSON object snapshot mapping"):
        execute_operation("cfi", "not a dict")

    with pytest.raises(ValueError, match="Input for 'eia' must be a JSON object mapping"):
        execute_operation("eia", 9999)


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


def test_subprocess_invocation(
    tmp_path: Path,
    sample_ci_snapshot: dict,
    sample_impact_data: dict,
    sample_cfi_snapshot: dict,
    sample_eia_data: dict,
    sample_facts_data: dict,
    sample_query_data: dict,
) -> None:
    ci_file = tmp_path / "ci_input.json"
    ci_file.write_text(json.dumps(sample_ci_snapshot), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "ci", "--input", str(ci_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["operation"] == "ci"
    assert payload["claim_ceiling"] == CI_EVIDENCE_CLAIM_CEILING
    assert payload["result"]["unexpected_count"] == 1

    impact_file = tmp_path / "impact_input.json"
    impact_file.write_text(json.dumps(sample_impact_data), encoding="utf-8")
    proc_impact = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "impact", "--input", str(impact_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_impact.returncode == 0
    payload_impact = json.loads(proc_impact.stdout)
    assert payload_impact["operation"] == "impact"
    assert payload_impact["claim_ceiling"] == CLAIM_CEILING
    assert payload_impact["result"]["direct_impacted_count"] == 1

    cfi_file = tmp_path / "cfi_input.json"
    cfi_file.write_text(json.dumps(sample_cfi_snapshot), encoding="utf-8")
    proc_cfi = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "cfi", "--input", str(cfi_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_cfi.returncode == 0
    payload_cfi = json.loads(proc_cfi.stdout)
    assert payload_cfi["operation"] == "cfi"
    assert payload_cfi["claim_ceiling"] == CI_EVIDENCE_CLAIM_CEILING
    assert payload_cfi["result"]["status"] == "UNEXPECTED_FAILURE_OBSERVED"

    eia_file = tmp_path / "eia_input.json"
    eia_file.write_text(json.dumps(sample_eia_data), encoding="utf-8")
    proc_eia = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "eia", "--input", str(eia_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_eia.returncode == 0
    payload_eia = json.loads(proc_eia.stdout)
    assert payload_eia["operation"] == "eia"
    assert payload_eia["claim_ceiling"] == AUTOMATION_CLAIM_CEILING
    assert payload_eia["result"]["decision"] == "READY"

    facts_file = tmp_path / "facts_input.json"
    facts_file.write_text(json.dumps(sample_facts_data), encoding="utf-8")
    proc_facts = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "facts", "--input", str(facts_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_facts.returncode == 0, proc_facts.stderr
    payload_facts = json.loads(proc_facts.stdout)
    assert payload_facts["operation"] == "facts"
    assert payload_facts["claim_ceiling"] == REPOSITORY_FACTS_CLAIM_CEILING
    assert payload_facts["result"]["is_complete"] is True

    query_file = tmp_path / "query_input.json"
    query_file.write_text(json.dumps(sample_query_data), encoding="utf-8")
    proc_query = subprocess.run(
        [sys.executable, "-m", "repository_intelligence.cli", "--operation", "query", "--input", str(query_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_query.returncode == 0, proc_query.stderr
    payload_query = json.loads(proc_query.stdout)
    assert payload_query["operation"] == "query"
    assert payload_query["claim_ceiling"] == REPOSITORY_QUERY_CLAIM_CEILING
    assert payload_query["result"]["resolution"] == "EXACT_RESOLUTION"
    assert payload_query["result"]["is_complete"] is True

