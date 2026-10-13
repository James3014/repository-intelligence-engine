"""Issue #98 independent-review follow-ups (RED first).

1. Supersession requires the same check name, app, and workflow identity, and a
   check-run id on both sides; no started_at fallback across check kinds.
2. Systemic failures are keyed by (workflow path, job name) and only count
   failures completed after the newest success of that check (on any open PR
   or main) and after the newest main change to the workflow file.
3. Merge-base lookups that fail are recorded as MERGE_BASE_UNKNOWN, and a
   SUPERSEDED ignored entry without a check-run id fails verification.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import github_action as gha
from repository_intelligence import core as ri
from repository_intelligence._hashing import content_hash
from repository_intelligence.cfi import (
    analyze_ci_failure_intelligence,
    verify_ci_failure_intelligence_report,
)
from repository_intelligence.systemic import (
    analyze_systemic_failures,
    verify_systemic_failure_report,
)
from test_github_action import FakeGitHubAPI

HEAD = "b" * 40
BASE = "a" * 40
MAIN = "c" * 40


def _check(name, status, run_id, *, workflow_id=11, app="github-actions", suite=900, started="2026-10-13T04:00:00Z"):
    check = {
        "name": name,
        "status": status,
        "head_sha": HEAD,
        "check_suite_id": suite,
        "details_url": f"https://github.com/o/r/actions/runs/1/job/{run_id}",
        "started_at": started,
        "app_slug": app,
        "workflow_id": workflow_id,
    }
    if run_id is not None:
        check["check_run_id"] = run_id
    return check


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


def _failed(checks):
    return analyze_ci_failure_intelligence(_snapshot(checks)).failed_check_names


# --- 1. strict supersession --------------------------------------------------


def test_same_workflow_and_app_newer_run_supersedes():
    assert _failed([_check("pytest", "cancelled", 100), _check("pytest", "success", 200)]) == ()


def test_newer_same_name_run_from_another_workflow_does_not_supersede():
    assert _failed([
        _check("pytest", "cancelled", 100, workflow_id=11),
        _check("pytest", "success", 200, workflow_id=22),
    ]) == ("pytest",)


def test_newer_same_name_run_from_another_app_does_not_supersede():
    assert _failed([
        _check("pytest", "cancelled", 100, app="github-actions"),
        _check("pytest", "success", 200, app="other-ci"),
    ]) == ("pytest",)


def test_missing_workflow_identity_does_not_supersede():
    assert _failed([
        _check("pytest", "cancelled", 100, workflow_id=None),
        _check("pytest", "success", 200, workflow_id=None),
    ]) == ("pytest",)


def test_commit_status_without_run_id_never_supersedes_via_started_at():
    status_like = {
        "name": "pytest",
        "status": "success",
        "head_sha": HEAD,
        "external_id": "github_commit_status:1",
        "started_at": "2026-10-13T09:00:00Z",
    }
    assert _failed([_check("pytest", "cancelled", 100), status_like]) == ("pytest",)


def test_missing_run_id_on_cancelled_check_does_not_supersede():
    assert _failed([
        _check("pytest", "cancelled", None, started="2026-10-13T01:00:00Z"),
        _check("pytest", "success", 200, started="2026-10-13T02:00:00Z"),
    ]) == ("pytest",)


def _rehash(report):
    report["failure_evidence"]["content_sha256"] = content_hash(report["failure_evidence"])
    report["content_sha256"] = content_hash(report)
    return report


def test_superseded_entry_records_workflow_identity_and_verifies():
    report = analyze_ci_failure_intelligence(
        _snapshot([_check("pytest", "cancelled", 100), _check("pytest", "queued", 200)])
    ).to_dict()
    (entry,) = report["failure_evidence"]["ignored_checks"]
    assert entry["app_slug"] == "github-actions" and entry["workflow_id"] == 11
    assert entry["superseded_by_check_run_id"] == 200
    assert verify_ci_failure_intelligence_report(report) is True


def test_superseded_entry_with_null_run_id_fails_verification():
    report = analyze_ci_failure_intelligence(
        _snapshot([_check("pytest", "cancelled", 100), _check("pytest", "queued", 200)])
    ).to_dict()
    forged = copy.deepcopy(report)
    forged["failure_evidence"]["ignored_checks"][0]["check_run_id"] = None
    assert verify_ci_failure_intelligence_report(_rehash(forged)) is False


def test_superseded_entry_without_workflow_identity_fails_verification():
    report = analyze_ci_failure_intelligence(
        _snapshot([_check("pytest", "cancelled", 100), _check("pytest", "queued", 200)])
    ).to_dict()
    forged = copy.deepcopy(report)
    forged["failure_evidence"]["ignored_checks"][0]["workflow_id"] = None
    assert verify_ci_failure_intelligence_report(_rehash(forged)) is False


# --- 3. merge-base status ----------------------------------------------------


def test_unknown_merge_base_is_recorded_not_claimed():
    result = ri.classify_readiness(_snapshot([_check("pytest", "success", 1)], current_main_sha=MAIN))
    assert "MERGE_BASE_UNKNOWN" in result.findings
    assert "merge-base with current main unknown" in result.evidence_gaps
    assert result.disposition.value == "REVIEW_READY"
    assert result.identity.no_unique_merge_base is False


def test_resolved_merge_base_has_no_unknown_marker():
    result = ri.classify_readiness(
        _snapshot([_check("pytest", "success", 1)], current_main_sha=MAIN, merge_base_status="RESOLVED")
    )
    assert "MERGE_BASE_UNKNOWN" not in result.findings
    assert "STALE_BASE" in result.findings


def test_no_merge_base_status_is_stale():
    result = ri.classify_readiness(
        _snapshot([_check("pytest", "success", 1)], current_main_sha=MAIN, merge_base_status="NONE")
    )
    assert "NO_UNIQUE_MERGE_BASE" in result.findings
    assert result.disposition.value == "STALE"
    assert result.identity.no_unique_merge_base is True


class _CompareAPI(FakeGitHubAPI):
    def __init__(self, compare_error=None, **kwargs):
        super().__init__(**kwargs)
        self.compare_error = compare_error

    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/git/ref/heads/main":
            return {"object": {"sha": MAIN}}
        if path.startswith("/repos/owner/repo/compare/"):
            if self.compare_error:
                raise self.compare_error
            return {"merge_base_commit": {"sha": BASE}}
        return super().get_json(path, params)


def test_adapter_reports_merge_base_status_values():
    assert gha.collect_pr_snapshot(_CompareAPI(), "owner/repo", 7)["merge_base_status"] == "RESOLVED"
    none = _CompareAPI(RuntimeError("GitHub HTTP 404: No common ancestor between c and b"))
    assert gha.collect_pr_snapshot(none, "owner/repo", 7)["merge_base_status"] == "NONE"
    unknown = _CompareAPI(RuntimeError("GitHub HTTP 502: bad gateway"))
    snapshot = gha.collect_pr_snapshot(unknown, "owner/repo", 7)
    assert snapshot["merge_base_status"] == "UNKNOWN"
    assert "merge_base_unique" not in snapshot


class _RunsAPI(FakeGitHubAPI):
    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/actions/runs":
            assert params and params.get("head_sha") == HEAD
            return {"workflow_runs": [
                {"id": 1, "check_suite_id": 201, "workflow_id": 77, "path": ".github/workflows/ci.yml", "head_sha": HEAD},
            ]}
        return super().get_json(path, params)


def test_adapter_attaches_workflow_identity_to_check_runs():
    snapshot = gha.collect_pr_snapshot(_RunsAPI(), "owner/repo", 7)
    check = snapshot["checks"][0]
    assert check["check_suite_id"] == 201
    assert check["workflow_id"] == 77
    assert check["workflow_path"] == ".github/workflows/ci.yml"
    assert check["app_slug"] == "github-actions"


# --- 2. systemic keyed by workflow and bounded by cutoffs ---------------------

NOW = "2026-10-13T06:00:00Z"
WF = ".github/workflows/trusted-impact-gate.yml"


def _run(name, status, run_id, completed, workflow_path=WF):
    return {"name": name, "status": status, "check_run_id": run_id, "completed_at": completed, "workflow_path": workflow_path}


def _prs(*rows):
    return [{"pr_number": n, "checks": checks} for n, checks in rows]


def _report(prs, **extra):
    data = {"repository": "o/r", "observed_at": NOW, "pull_requests": prs}
    data.update(extra)
    return analyze_systemic_failures(data)


FAILS = [(n, [_run("controller", "failure", n, "2026-10-13T03:00:00Z")]) for n in (1, 2, 3)]


def test_systemic_reports_workflow_path():
    (item,) = _report(_prs(*FAILS)).to_dict()["systemic_failures"]
    assert item == {"check_name": "controller", "workflow_path": WF, "pr_numbers": [1, 2, 3], "failing_pr_count": 3}


def test_same_job_name_in_different_workflows_is_not_merged():
    rows = [
        (1, [_run("build", "failure", 1, "2026-10-13T03:00:00Z", ".github/workflows/a.yml")]),
        (2, [_run("build", "failure", 2, "2026-10-13T03:00:00Z", ".github/workflows/b.yml")]),
        (3, [_run("build", "failure", 3, "2026-10-13T03:00:00Z", ".github/workflows/c.yml")]),
    ]
    assert _report(_prs(*rows)).systemic_failures == ()


def test_newer_success_on_another_open_pr_sets_the_cutoff():
    rows = [*FAILS, (4, [_run("controller", "success", 40, "2026-10-13T04:00:00Z")])]
    assert _report(_prs(*rows)).systemic_failures == ()


def test_failures_after_the_newest_success_still_count():
    rows = [
        (4, [_run("controller", "success", 40, "2026-10-13T02:00:00Z")]),
        *FAILS,
    ]
    assert [s.check_name for s in _report(_prs(*rows)).systemic_failures] == ["controller"]


def test_success_on_main_sets_the_cutoff():
    main = [_run("controller", "success", 99, "2026-10-13T04:00:00Z")]
    assert _report(_prs(*FAILS), main_checks=main).systemic_failures == ()


def test_workflow_file_change_on_main_sets_the_cutoff():
    report = _report(_prs(*FAILS), workflow_changed_at={WF: "2026-10-13T04:30:00Z"})
    assert report.systemic_failures == ()
    report = _report(_prs(*FAILS), workflow_changed_at={WF: "2026-10-13T01:00:00Z"})
    assert [s.check_name for s in report.systemic_failures] == ["controller"]


def test_cutoffs_are_embedded_and_verified():
    payload = _report(_prs(*FAILS), workflow_changed_at={WF: "2026-10-13T01:00:00Z"}).to_dict()
    assert verify_systemic_failure_report(payload) is True
    forged = copy.deepcopy(payload)
    forged["systemic_failures"][0]["workflow_path"] = ".github/workflows/other.yml"
    forged["content_sha256"] = content_hash(forged)
    assert verify_systemic_failure_report(forged) is False
