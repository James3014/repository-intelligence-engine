"""Issue #98: signal-quality fixes and the cross-PR systemic failure signal."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import github_action as gha
from repository_intelligence import cli
from repository_intelligence import core as ri
from repository_intelligence.cfi import (
    analyze_ci_failure_intelligence,
    verify_ci_failure_intelligence_report,
)
from repository_intelligence.systemic import analyze_systemic_failures, verify_systemic_failure_report
from test_github_action import FakeGitHubAPI

HEAD = "b" * 40
BASE = "a" * 40
MAIN = "c" * 40


def _check(name, status, run_id, suite=900, started="2026-10-13T04:00:00Z", workflow_id=11):
    # Review follow-up: supersession needs the same app and workflow identity.
    return {
        "app_slug": "github-actions",
        "workflow_id": workflow_id,
        "name": name,
        "status": status,
        "head_sha": HEAD,
        "check_run_id": run_id,
        "check_suite_id": suite,
        "details_url": f"https://github.com/o/r/actions/runs/1/job/{run_id}",
        "started_at": started,
    }


def _snapshot(checks, **extra):
    data = {
        "repository": "owner/repo",
        "pr_number": 7,
        "head_sha": HEAD,
        "base_sha": BASE,
        "current_main_sha": BASE,
        "mergeable": True,
        "changed_files": ["src/a.py"],
        "checks": checks,
    }
    data.update(extra)
    return data


# --- CFI: superseded cancelled checks --------------------------------------


def test_cancelled_check_superseded_by_newer_same_name_run_is_not_a_failure():
    report = analyze_ci_failure_intelligence(_snapshot([
        _check("Nexus Core issue run", "cancelled", 100, suite=1),
        _check("Nexus Core issue run", "in_progress", 200, suite=2),
        _check("pytest", "success", 150, suite=3),
    ]))
    assert report.status.value == "NO_TERMINAL_FAILURE"
    assert report.failed_check_names == ()
    ignored = report.failure_evidence.ignored_checks
    assert [(c["name"], c["check_run_id"], c["reason"]) for c in ignored] == [
        ("Nexus Core issue run", 100, "SUPERSEDED_CANCELLED"),
    ]
    assert verify_ci_failure_intelligence_report(report.to_dict()) is True


def test_cancelled_check_without_newer_run_is_still_unexpected():
    report = analyze_ci_failure_intelligence(_snapshot([
        _check("pytest", "cancelled", 100),
        _check("lint", "success", 50),
    ]))
    assert report.status.value == "UNEXPECTED_FAILURE_OBSERVED"
    assert report.failed_check_names == ("pytest",)
    assert report.failure_evidence.ignored_checks == ()


def test_newest_cancelled_run_is_not_superseded_by_an_older_run():
    report = analyze_ci_failure_intelligence(_snapshot([
        _check("pytest", "success", 100),
        _check("pytest", "cancelled", 200),
    ]))
    assert report.failed_check_names == ("pytest",)


def test_superseded_failure_that_is_not_cancelled_still_counts():
    report = analyze_ci_failure_intelligence(_snapshot([
        _check("pytest", "failure", 100),
        _check("pytest", "success", 200),
    ]))
    assert report.failed_check_names == ("pytest",)


def test_rie_workflow_own_jobs_are_ignored_by_check_suite():
    report = analyze_ci_failure_intelligence(_snapshot(
        [
            _check("terminal", "failure", 100, suite=555),
            _check("guard-delta", "cancelled", 101, suite=555),
            _check("pytest", "success", 102, suite=777),
        ],
        self_check_suite_ids=[555],
    ))
    assert report.status.value == "NO_TERMINAL_FAILURE"
    reasons = {(c["name"], c["reason"]) for c in report.failure_evidence.ignored_checks}
    assert reasons == {("terminal", "SELF_WORKFLOW"), ("guard-delta", "SELF_WORKFLOW")}
    assert verify_ci_failure_intelligence_report(report.to_dict()) is True


def test_pr_1966_shape_reports_no_unexpected_failure():
    # Replay of Nexus-new PR #1966 artifact 11788789536: four cancelled checks,
    # each superseded by the newer run that was already queued on the same head.
    old_rie, new_rie, old_core, new_core = 103899580562, 103899580999, 103899578819, 103899578900
    checks = [
        _check("terminal", "cancelled", 115134540554, suite=old_rie),
        _check("Nexus Core issue run", "cancelled", 115134452915, suite=old_core),
        _check("guard-delta", "cancelled", 115134454748, suite=old_rie),
        _check("snapshot", "cancelled", 115134454846, suite=old_rie),
        _check("snapshot", "in_progress", 115134600000, suite=new_rie),
        _check("guard-delta", "queued", 115134600001, suite=new_rie),
        _check("terminal", "queued", 115134600002, suite=new_rie),
        _check("Nexus Core issue run", "in_progress", 115134600003, suite=new_core),
    ]
    report = analyze_ci_failure_intelligence(_snapshot(checks, self_check_suite_ids=[old_rie, new_rie]))
    assert report.status.value == "NO_TERMINAL_FAILURE"
    readiness = ri.classify_readiness(_snapshot(checks, self_check_suite_ids=[old_rie, new_rie]))
    assert "UNEXPECTED_FAILURE" not in readiness.findings


def test_tampered_ignored_checks_are_rejected_by_cfi_verifier():
    report = analyze_ci_failure_intelligence(_snapshot([
        _check("pytest", "cancelled", 100),
        _check("pytest", "queued", 200),
    ])).to_dict()
    forged = copy.deepcopy(report)
    forged["failure_evidence"]["ignored_checks"][0]["reason"] = "SELF_WORKFLOW"
    from repository_intelligence._hashing import content_hash

    forged["failure_evidence"]["content_sha256"] = content_hash(forged["failure_evidence"])
    forged["content_sha256"] = content_hash(forged)
    assert verify_ci_failure_intelligence_report(forged) is False


# --- STALE_BASE demotion -----------------------------------------------------


def test_base_behind_main_is_informational_and_review_ready():
    result = ri.classify_readiness(_snapshot([_check("pytest", "success", 1)], current_main_sha=MAIN))
    assert "STALE_BASE" in result.findings
    assert result.identity.stale_base is True
    assert result.identity.no_unique_merge_base is False
    assert result.disposition.value == "REVIEW_READY"


def test_no_unique_merge_base_keeps_readiness_stale():
    result = ri.classify_readiness(_snapshot(
        [_check("pytest", "success", 1)], current_main_sha=MAIN, merge_base_status="NONE",
    ))
    assert "NO_UNIQUE_MERGE_BASE" in result.findings
    assert result.identity.no_unique_merge_base is True
    assert result.disposition.value == "STALE"


def _report_item(**extra):
    report = ri.build_repository_intelligence_report([
        _snapshot([_check("pytest", "success", 1)], current_main_sha=MAIN, **extra)
    ]).to_dict()
    return report


def test_report_verifier_accepts_review_ready_with_base_behind_main():
    report = _report_item()
    assert report["items"][0]["disposition"] == "REVIEW_READY"
    assert ri.verify_repository_intelligence_report(report) is True


def test_report_verifier_rejects_rehashed_review_ready_without_unique_merge_base():
    from repository_intelligence._hashing import content_hash

    report = _report_item(merge_base_status="NONE")
    assert ri.verify_repository_intelligence_report(report) is True
    item = report["items"][0]
    item.update(disposition="REVIEW_READY", is_review_ready=True, findings=[], reasons=[])
    report["content_sha256"] = content_hash(report)
    assert ri.verify_repository_intelligence_report(report) is False


def test_legacy_item_without_merge_base_field_still_needs_fresh_base_for_review_ready():
    item = _report_item()["items"][0]
    del item["identity"]["no_unique_merge_base"]
    assert ri.readiness_item_is_coherent(item) is False
    item["identity"]["stale_base"] = False
    assert ri.readiness_item_is_coherent(item) is True


# --- Adapter acquisition -----------------------------------------------------


class _BehindMainAPI(FakeGitHubAPI):
    def __init__(self, *, compare_error=None, runs=None, runs_error=None, **kwargs):
        super().__init__(**kwargs)
        self.compare_error = compare_error
        self.runs = runs
        self.runs_error = runs_error

    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/git/ref/heads/main":
            self.calls.append((path, None))
            return {"object": {"sha": MAIN}}
        if path.startswith("/repos/owner/repo/compare/"):
            self.calls.append((path, None))
            if self.compare_error:
                raise self.compare_error
            return {"status": "diverged", "merge_base_commit": {"sha": BASE}}
        if path == "/repos/owner/repo/actions/runs":
            self.calls.append((path, dict(params or {})))
            if self.runs_error:
                raise self.runs_error
            return {"workflow_runs": self.runs or []}
        return super().get_json(path, params)


def test_adapter_resolves_merge_base_when_base_is_behind_main():
    snapshot = gha.collect_pr_snapshot(_BehindMainAPI(), "owner/repo", 7)
    assert snapshot["merge_base_status"] == "RESOLVED"
    assert snapshot["collection_complete"] is True


def test_adapter_marks_no_common_ancestor():
    api = _BehindMainAPI(compare_error=RuntimeError("GitHub HTTP 404: No common ancestor between c and b"))
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    assert snapshot["merge_base_status"] == "NONE"
    bundle = gha.run_cloud_bundle(snapshot)
    assert bundle["reports"]["readiness"]["result"]["disposition"] == "STALE"
    assert gha.verify_cloud_bundle(bundle) is True


def test_adapter_merge_base_lookup_failure_is_unknown_not_stale():
    api = _BehindMainAPI(compare_error=RuntimeError("GitHub HTTP 502: bad gateway"))
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    assert snapshot["merge_base_status"] == "UNKNOWN"
    assert snapshot["collection_complete"] is True


def test_adapter_skips_compare_when_base_is_main():
    api = FakeGitHubAPI()
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    assert snapshot["merge_base_status"] == "RESOLVED"
    assert not any("/compare/" in path for path, _ in api.calls)


def test_adapter_collects_own_workflow_check_suites_for_the_head():
    api = _BehindMainAPI(runs=[
        {"id": 42, "check_suite_id": 555, "workflow_id": 9, "head_sha": HEAD},
        {"id": 41, "check_suite_id": 554, "workflow_id": 9, "head_sha": HEAD},
        {"id": 39, "check_suite_id": 201, "workflow_id": 8, "head_sha": HEAD},
        {"id": 40, "check_suite_id": 553, "workflow_id": 9, "head_sha": "d" * 40},
    ])
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7, self_run_id=42)
    assert snapshot["self_check_suite_ids"] == [554, 555]
    assert [q["head_sha"] for p, q in api.calls if p.endswith("/actions/runs")] == [HEAD]


def test_adapter_workflow_run_lookup_failure_ignores_nothing():
    api = _BehindMainAPI(runs_error=RuntimeError("GitHub HTTP 403: Resource not accessible by integration"))
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7, self_run_id=42)
    assert snapshot["self_check_suite_ids"] == []
    assert "workflow_id" not in snapshot["checks"][0]
    assert snapshot["collection_complete"] is True


# --- Systemic failure signal -------------------------------------------------

NOW = "2026-10-13T06:00:00Z"


def _pr(number, checks):
    return {"pr_number": number, "checks": checks}


def _run(name, status, run_id, completed="2026-10-13T05:00:00Z"):
    return {"name": name, "status": status, "check_run_id": run_id, "completed_at": completed}


def _systemic_input(prs, **extra):
    data = {"repository": "owner/repo", "observed_at": NOW, "pull_requests": prs}
    data.update(extra)
    return data


def test_same_check_failing_on_three_open_prs_is_systemic():
    prs = [_pr(n, [_run("Trusted impact controller", "failure", n * 10), _run("pytest", "success", n * 10 + 1)])
           for n in (1952, 1960, 1966)]
    report = analyze_systemic_failures(_systemic_input(prs + [_pr(1970, [_run("pytest", "failure", 5)])]))
    assert [(s.check_name, s.pr_numbers) for s in report.systemic_failures] == [
        ("Trusted impact controller", (1952, 1960, 1966)),
    ]
    assert report.to_dict()["systemic_failures"][0]["failing_pr_count"] == 3


@pytest.mark.parametrize(
    "variant",
    ["two_prs", "cancelled", "old", "rerun_passed"],
)
def test_non_systemic_variants(variant):
    if variant == "two_prs":
        prs = [_pr(n, [_run("x", "failure", n)]) for n in (1, 2)]
    elif variant == "cancelled":
        prs = [_pr(n, [_run("x", "cancelled", n)]) for n in (1, 2, 3)]
    elif variant == "old":
        prs = [_pr(n, [_run("x", "failure", n, completed="2026-10-12T05:59:59Z")]) for n in (1, 2, 3)]
    else:
        prs = [_pr(n, [_run("x", "failure", n), _run("x", "success", n + 100)]) for n in (1, 2, 3)]
    assert analyze_systemic_failures(_systemic_input(prs)).systemic_failures == ()


def test_systemic_threshold_and_window_are_configurable_and_reported():
    prs = [_pr(n, [_run("x", "timed_out", n)]) for n in (1, 2)]
    report = analyze_systemic_failures(_systemic_input(prs, min_pull_requests=2, window_hours=1))
    assert [s.check_name for s in report.systemic_failures] == ["x"]
    payload = report.to_dict()
    assert payload["min_pull_requests"] == 2 and payload["window_hours"] == 1
    assert payload["claim_ceiling"] == "CI_EVIDENCE_ONLY"
    assert len(payload["content_sha256"]) == 64


def test_systemic_rejects_malformed_input_with_gaps():
    report = analyze_systemic_failures({"observed_at": "not-a-time", "pull_requests": [{"pr_number": "x"}]})
    assert report.systemic_failures == ()
    assert report.evidence_completeness.value == "INCOMPLETE"
    assert report.evidence_gaps


def test_systemic_is_a_cli_operation(tmp_path, capsys):
    prs = [_pr(n, [_run("x", "failure", n)]) for n in (1, 2, 3)]
    path = tmp_path / "in.json"
    path.write_text(json.dumps(_systemic_input(prs)), encoding="utf-8")
    assert cli.main(["--operation", "systemic", "--input", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["operation"] == "systemic"
    assert out["result"]["systemic_failures"][0]["pr_numbers"] == [1, 2, 3]


def test_systemic_verifier_accepts_genuine_and_rejects_rehashed_tamper():
    from repository_intelligence._hashing import content_hash

    prs = [_pr(n, [_run("x", "failure", n)]) for n in (1, 2, 3)]
    payload = analyze_systemic_failures(_systemic_input(prs)).to_dict()
    assert verify_systemic_failure_report(payload) is True
    forged = copy.deepcopy(payload)
    forged["systemic_failures"] = []
    forged["content_sha256"] = content_hash(forged)
    assert verify_systemic_failure_report(forged) is False
    forged = copy.deepcopy(payload)
    forged["failing_checks_by_pr"].pop("3")
    forged["content_sha256"] = content_hash(forged)
    assert verify_systemic_failure_report(forged) is False
