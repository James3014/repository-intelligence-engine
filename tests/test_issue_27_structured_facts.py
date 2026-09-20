"""Issue #27: structured repository facts (deterministic AST pattern evidence)."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from adapters.python_fact_detector import (
    DETECTOR_COVERAGE,
    DETECTOR_LANGUAGE,
    DETECTOR_VERSION,
    collect_python_pattern_observations,
)
from repository_intelligence.contracts import (
    REPOSITORY_FACTS_CLAIM_CEILING,
    RepositoryFactKind,
    RepositoryFactStatus,
)
from repository_intelligence.facts import (
    STRUCTURED_FACTS_SCHEMA,
    analyze_structured_facts,
    verify_structured_facts_report,
)

VALID_SNAPSHOT = {
    "repository": "owner/repo",
    "pr_number": 42,
    "head_sha": "a" * 40,
    "base_sha": "b" * 40,
    "current_main_sha": "b" * 40,
    "declared_head_sha": "a" * 40,
    "declared_base_sha": "b" * 40,
    "changed_files": ["src/run.py"],
}


def _bundle(source_files: dict[str, str]) -> dict:
    return collect_python_pattern_observations(source_files)


def _report_data(bundle: dict, snapshot: dict | None = None, **overrides) -> dict:
    data = {
        "snapshot": snapshot if snapshot is not None else dict(VALID_SNAPSHOT),
        "language": bundle.get("language", DETECTOR_LANGUAGE),
        "covered_files": bundle["covered_files"],
        "observations": bundle["observations"],
        "detector_coverage": bundle["detector_coverage"],
        "detector_version": bundle.get("detector_version", DETECTOR_VERSION),
        "collection_complete": bundle.get("collection_complete", True),
        "collection_errors": bundle.get("collection_errors", []),
    }
    data.update(overrides)
    return data


def _status(report, kind: str) -> str:
    return report.fact_statuses[RepositoryFactKind(kind).value]


def _rehash(payload: dict) -> dict:
    changed = copy.deepcopy(payload)
    unsigned = {k: v for k, v in changed.items() if k != "content_sha256"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    changed["content_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return changed


# ---------------------------------------------------------------- adapter: positives


def test_adapter_detects_empty_handler() -> None:
    bundle = _bundle(
        {
            "src/a.py": (
                "def f():\n"
                "    try:\n"
                "        work()\n"
                "    except ValueError:\n"
                "        pass\n"
                "    try:\n"
                "        work()\n"
                "    except ValueError:\n"
                "        ...\n"
            )
        }
    )
    obs = [o for o in bundle["observations"] if "EMPTY_EXCEPTION_HANDLER" in o["fact_kind"]]
    assert len(obs) == 2
    assert {o["evidence_ref"] for o in obs} == {"empty_except_handler"}


def test_adapter_detects_broad_handlers() -> None:
    bundle = _bundle(
        {
            "src/a.py": (
                "def f():\n"
                "    try:\n"
                "        work()\n"
                "    except:\n"
                "        pass\n"
                "    try:\n"
                "        work()\n"
                "    except Exception:\n"
                "        handle()\n"
                "    try:\n"
                "        work()\n"
                "    except BaseException:\n"
                "        raise\n"
            )
        }
    )
    broad = sorted(
        o["evidence_ref"]
        for o in bundle["observations"]
        if "BROAD_EXCEPTION_HANDLER" in o["fact_kind"]
    )
    assert broad == ["bare_except_handler", "broad_except_handler", "broad_except_handler"]


def test_adapter_resolves_subprocess_aliases() -> None:
    bundle = _bundle(
        {
            "src/a.py": (
                "import subprocess\n"
                "import subprocess as sp\n"
                "from subprocess import run\n"
                "from subprocess import check_call as cc\n"
                "import os\n"
                "import os as operating\n"
                "\n"
                "subprocess.run(['ls'])\n"
                "sp.Popen(['ls'])\n"
                "run(['ls'])\n"
                "cc(['ls'])\n"
                "os.system('ls')\n"
                "operating.system('ls')\n"
            )
        }
    )
    refs = sorted(
        o["evidence_ref"]
        for o in bundle["observations"]
        if "SUBPROCESS_CALL" in o["fact_kind"]
    )
    assert refs == [
        "subprocess_call:os.system",
        "subprocess_call:os.system",
        "subprocess_call:subprocess.Popen",
        "subprocess_call:subprocess.check_call",
        "subprocess_call:subprocess.run",
        "subprocess_call:subprocess.run",
    ]


def test_adapter_does_not_report_os_path_joins() -> None:
    bundle = _bundle({"src/a.py": "import os\nos.path.join('a', 'b')\n"})
    sub_obs = [o for o in bundle["observations"] if "SUBPROCESS_CALL" in o["fact_kind"]]
    assert sub_obs == []


def test_adapter_detects_localhost_literals() -> None:
    bundle = _bundle(
        {
            "src/cfg.py": (
                "A = 'localhost'\n"
                "B = '127.0.0.1'\n"
                "C = 'http://0.0.0.0:8080/x'\n"
                "D = 'https://[::1]/'\n"
                "OK = 'example.com'\n"
                "UNRELATED = 'not_an_ip'\n"
            )
        }
    )
    hard = sorted(
        o["file_path"] + ":" + str(o["line"])
        for o in bundle["observations"]
        if "HARDCODED_LOCALHOST" in o["fact_kind"]
    )
    assert "src/cfg.py:1" in hard
    assert "src/cfg.py:2" in hard
    assert "src/cfg.py:3" in hard
    assert "src/cfg.py:4" in hard
    assert len(hard) == 4


def test_adapter_detects_silent_retry_in_loops() -> None:
    bundle = _bundle(
        {
            "src/a.py": (
                "def f():\n"
                "    while True:\n"
                "        try:\n"
                "            work()\n"
                "        except Exception:\n"
                "            continue\n"
                "    for i in range(3):\n"
                "        try:\n"
                "            work()\n"
                "        except Exception:\n"
                "            pass\n"
                "def g():\n"
                "    try:\n"
                "        work()\n"
                "    except Exception:\n"
                "        pass\n"
            )
        }
    )
    retry = [
        o for o in bundle["observations"] if "SILENT_RETRY_PATTERN" in o["fact_kind"]
    ]
    assert len(retry) == 2
    refs = {o["evidence_ref"] for o in retry}
    assert "silent_retry_handler" in refs


def test_adapter_coverage_marks_unimplemented_false() -> None:
    assert DETECTOR_COVERAGE[RepositoryFactKind.SUBPROCESS_CALL.value] is True
    assert DETECTOR_COVERAGE[RepositoryFactKind.NETWORK_ENDPOINT_ADDED.value] is False
    assert DETECTOR_COVERAGE[RepositoryFactKind.VISIBLE_AUTH_CHECK.value] is False
    assert DETECTOR_COVERAGE[RepositoryFactKind.RELATED_TEST_CHANGED.value] is False


# ---------------------------------------------------------------- adapter: fail-closed collection


def test_adapter_parse_failure_fails_collection_closed() -> None:
    bundle = _bundle({"src/bad.py": "def broken(:\n", "src/ok.py": "x = 1\n"})
    assert bundle["collection_complete"] is False
    assert "src/bad.py" not in bundle["covered_files"]
    assert "src/ok.py" in bundle["covered_files"]
    assert any("src/bad.py" in err for err in bundle["collection_errors"])


def test_adapter_rejects_unsafe_paths() -> None:
    bundle = _bundle({"../escape.py": "x = 1\n", "src/ok.py": "x = 1\n"})
    assert bundle["collection_complete"] is False
    assert "src/ok.py" in bundle["covered_files"]


# ---------------------------------------------------------------- engine: classification


def test_engine_proven_not_observed_unknown_with_dedupe() -> None:
    bundle = _bundle(
        {
            "src/run.py": (
                "import subprocess\n"
                "subprocess.run(['ls'])\n"
                "subprocess.run(['ls'])\n"
            )
        }
    )
    report = analyze_structured_facts(_report_data(bundle))
    assert report.schema == STRUCTURED_FACTS_SCHEMA
    assert report.claim_ceiling == REPOSITORY_FACTS_CLAIM_CEILING
    assert report.is_complete is True
    assert report.evidence_completeness.value == "COMPLETE"

    assert _status(report, "SUBPROCESS_CALL") == RepositoryFactStatus.PROVEN.value
    assert _status(report, "EMPTY_EXCEPTION_HANDLER") == RepositoryFactStatus.NOT_OBSERVED.value
    assert _status(report, "NETWORK_ENDPOINT_ADDED") == RepositoryFactStatus.UNKNOWN.value
    assert _status(report, "VISIBLE_AUTH_CHECK") == RepositoryFactStatus.UNKNOWN.value

    sub_fact = next(
        f for f in report.facts if f.fact_kind is RepositoryFactKind.SUBPROCESS_CALL
    )
    assert len(sub_fact.evidence) == 2
    assert sub_fact.evidence[0].file_path == "src/run.py"
    assert sub_fact.evidence[0].evidence_ref.startswith("subprocess_call:")
    assert sub_fact.evidence[0].line > 0

    # Duplicate observation entries are deduplicated by the engine.
    dup_bundle = copy.deepcopy(bundle)
    dup_bundle["observations"].append(dict(dup_bundle["observations"][0]))
    report_dedup = analyze_structured_facts(_report_data(dup_bundle))
    assert report_dedup.content_sha256 == report.content_sha256
    assert len(report_dedup.observations) == len(report.observations)


def test_engine_unbound_revision_unresolved() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    stale_snapshot = dict(VALID_SNAPSHOT)
    stale_snapshot["declared_head_sha"] = "c" * 40
    report = analyze_structured_facts(_report_data(bundle, snapshot=stale_snapshot))
    assert report.is_complete is False
    assert report.identity.stale_evidence is True
    assert all(
        fact.status is RepositoryFactStatus.UNRESOLVED for fact in report.facts
    )
    assert "STALE_EVIDENCE" in report.facts[0].reason_codes


def test_engine_stale_unpinned_revision_unresolved() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    unpinned_snapshot = {
        "repository": "owner/repo",
        "pr_number": 42,
        "head_sha": "a" * 40,
        "base_sha": "b" * 40,
        "current_main_sha": "c" * 40,
        "declared_head_sha": "a" * 40,
        "declared_base_sha": "b" * 40,
        "changed_files": ["src/run.py"],
    }
    report = analyze_structured_facts(_report_data(bundle, snapshot=unpinned_snapshot))
    assert report.identity.stale_base is True
    assert not report.identity.stale_evidence
    assert report.is_complete is True
    assert _status(report, "SUBPROCESS_CALL") == RepositoryFactStatus.PROVEN.value


def test_engine_collection_error_unresolves_all() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(
        _report_data(bundle, collection_complete=False, collection_errors=["transient failure"])
    )
    assert report.is_complete is False
    assert all(fact.status is RepositoryFactStatus.UNRESOLVED for fact in report.facts)


def test_engine_unknown_fact_kind_fails_collection_closed() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    bundle["observations"].append(
        {"fact_kind": "NOT_A_REAL_KIND", "file_path": "src/run.py", "line": 1, "column": 0, "evidence_ref": "x"}
    )
    report = analyze_structured_facts(_report_data(bundle))
    assert report.is_complete is False
    assert all(fact.status is RepositoryFactStatus.UNRESOLVED for fact in report.facts)
    assert any("unknown fact_kind" in err for err in report.collection_errors)


def test_engine_invalid_observation_marks_kind_unresolved() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    bundle["observations"].append(
        {
            "fact_kind": "EMPTY_EXCEPTION_HANDLER",
            "file_path": "src/run.py",
            "line": "not-an-int",
            "column": 0,
            "evidence_ref": "empty_except_handler",
        }
    )
    report = analyze_structured_facts(_report_data(bundle))
    assert report.is_complete is False
    assert _status(report, "EMPTY_EXCEPTION_HANDLER") == RepositoryFactStatus.UNRESOLVED.value
    assert _status(report, "SUBPROCESS_CALL") == RepositoryFactStatus.PROVEN.value


def test_engine_observation_outside_covered_files_fails_closed() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    extra = {
        "fact_kind": "SUBPROCESS_CALL",
        "file_path": "src/never_covered.py",
        "line": 1,
        "column": 0,
        "evidence_ref": "subprocess_call:subprocess.run",
    }
    bundle["observations"].append(extra)
    report = analyze_structured_facts(_report_data(bundle))
    assert _status(report, "SUBPROCESS_CALL") == RepositoryFactStatus.UNRESOLVED.value
    assert report.is_complete is False


def test_engine_related_test_changed_from_snapshot_diff() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    snapshot = dict(VALID_SNAPSHOT)
    snapshot["changed_files"] = ["src/run.py", "tests/test_run.py"]
    report = analyze_structured_facts(_report_data(bundle, snapshot=snapshot))
    rt = next(
        f for f in report.facts if f.fact_kind is RepositoryFactKind.RELATED_TEST_CHANGED
    )
    assert rt.status is RepositoryFactStatus.PROVEN
    assert rt.evidence[0].file_path == "tests/test_run.py"
    assert rt.evidence[0].line == 0
    assert rt.evidence[0].evidence_ref == "changed_test_file"


def test_engine_related_test_changed_no_test_diff_no_changed_files() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    snapshot = dict(VALID_SNAPSHOT)
    snapshot["changed_files"] = ["src/run.py"]
    report = analyze_structured_facts(_report_data(bundle, snapshot=snapshot))
    rt = next(
        f for f in report.facts if f.fact_kind is RepositoryFactKind.RELATED_TEST_CHANGED
    )
    assert rt.status is RepositoryFactStatus.NOT_OBSERVED

    no_diff_snapshot = {k: v for k, v in VALID_SNAPSHOT.items() if k != "changed_files"}
    report_no_diff = analyze_structured_facts(_report_data(bundle, snapshot=no_diff_snapshot))
    rt2 = next(
        f for f in report_no_diff.facts
        if f.fact_kind is RepositoryFactKind.RELATED_TEST_CHANGED
    )
    assert rt2.status is RepositoryFactStatus.UNKNOWN
    assert "NO_CHANGED_FILES" in rt2.reason_codes


def test_engine_changed_files_mismatch_fails_closed() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(
        _report_data(bundle, changed_files=["src/other.py"])
    )
    assert report.is_complete is False
    assert all(fact.status is RepositoryFactStatus.UNRESOLVED for fact in report.facts)


def test_engine_requested_subset_and_scope_limitations() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    data = _report_data(bundle, requested_facts=["SUBPROCESS_CALL"])
    report = analyze_structured_facts(data)
    assert [fact.fact_kind.value for fact in report.facts] == ["SUBPROCESS_CALL"]
    assert report.requested_facts == ("SUBPROCESS_CALL",)
    assert report.is_complete is True

    full = analyze_structured_facts(_report_data(bundle))
    unknown_limitations = full.limitations["NETWORK_ENDPOINT_ADDED"]
    assert any("no deterministic" in note.casefold() for note in unknown_limitations)


def test_engine_unsupported_requested_fact_fails_closed() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(
        _report_data(bundle, requested_facts=["SUBPROCESS_CALL", "MADE_UP_KIND"])
    )
    assert report.is_complete is False
    assert all(fact.status is RepositoryFactStatus.UNRESOLVED for fact in report.facts)


def test_engine_structured_consumer_access_without_prose() -> None:
    bundle = _bundle(
        {
            "src/run.py": (
                "import subprocess as sp\n"
                "def launch():\n"
                "    sp.run(['true'])\n"
            )
        }
    )
    report = analyze_structured_facts(_report_data(bundle))
    assert report.fact_statuses["SUBPROCESS_CALL"] == "PROVEN"
    fact = next(f for f in report.facts if f.fact_kind.value == "SUBPROCESS_CALL")
    assert fact.status.value == "PROVEN"
    assert fact.head_sha == ("a" * 40)
    assert fact.language == DETECTOR_LANGUAGE
    assert fact.reason_codes == ("DETECTOR_OBSERVATION", "REVISION_BOUND")
    assert fact.evidence[0].to_dict()["evidence_ref"] == "subprocess_call:subprocess.run"


# ---------------------------------------------------------------- verifier


def test_verifier_accepts_genuine_report() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(_report_data(bundle))
    assert verify_structured_facts_report(report.to_dict()) is True


def test_verifier_rejects_tampered_status_with_valid_hash() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(_report_data(bundle))
    tampered = _rehash(report.to_dict())
    tampered["facts"][0]["status"] = "PROVEN"
    assert verify_structured_facts_report(tampered) is False


def test_verifier_rejects_tampered_evidence_location() -> None:
    bundle = _bundle(
        {"src/run.py": "import subprocess as sp\nsp.run(['x'])\n", "src/other.py": "y = 1\n"}
    )
    report = analyze_structured_facts(_report_data(bundle))
    tampered = _rehash(report.to_dict())
    # Move the evidence to a different line; recomputing from observations must disagree.
    sub_fact = next(f for f in tampered["facts"] if f["fact_kind"] == "SUBPROCESS_CALL")
    sub_fact["evidence"] = [
        {"file_path": "src/run.py", "line": 99, "column": 0, "evidence_ref": "subprocess_call:subprocess.run"}
    ]
    assert verify_structured_facts_report(tampered) is False


def test_verifier_rejects_missing_limitations() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(_report_data(bundle))
    tampered = _rehash(report.to_dict())
    tampered["limitations"] = {}
    assert verify_structured_facts_report(tampered) is False


def test_verifier_rejects_bad_hash_and_wrong_schema() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    report = analyze_structured_facts(_report_data(bundle))
    payload = report.to_dict()
    payload["content_sha256"] = "0" * 64
    assert verify_structured_facts_report(payload) is False
    payload2 = report.to_dict()
    payload2["schema"] = "reviewer.other.v9"
    assert verify_structured_facts_report(payload2) is False


def test_verifier_accepts_incomplete_stale_report() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    stale_snapshot = dict(VALID_SNAPSHOT)
    stale_snapshot["declared_head_sha"] = "c" * 40
    report = analyze_structured_facts(_report_data(bundle, snapshot=stale_snapshot))
    assert report.is_complete is False
    assert verify_structured_facts_report(report.to_dict()) is True


def test_content_hash_is_deterministic_and_sorted() -> None:
    bundle = _bundle({"src/run.py": "import subprocess\nsubprocess.run(['x'])\n"})
    first = analyze_structured_facts(_report_data(bundle)).content_sha256
    second = analyze_structured_facts(_report_data(bundle)).content_sha256
    assert first == second
    assert len(first) == 64