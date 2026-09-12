from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from adapters import github_action as gha


class FakeGitHubAPI:
    def __init__(self, *, check_runs=None, commit_statuses=None, check_error=None, status_error=None):
        self.calls: list[tuple[str, dict | None]] = []
        self.check_runs = check_runs if check_runs is not None else [
            {
                "id": 101,
                "name": "ci/test",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": "b" * 40,
                "details_url": "https://example.invalid/check/101",
                "check_suite": {"id": 201},
                "app": {"slug": "github-actions"},
                "output": {"annotations_count": 1},
                "started_at": "2026-08-30T01:00:00Z",
                "completed_at": "2026-08-30T01:01:00Z",
            }
        ]
        self.commit_statuses = commit_statuses if commit_statuses is not None else [
            {
                "id": 301,
                "context": "ci/test",
                "state": "success",
                "sha": "b" * 40,
                "target_url": "https://example.invalid/status/301",
            }
        ]
        self.check_error = check_error
        self.status_error = status_error

    def get_json(self, path: str, params=None):
        self.calls.append((path, dict(params) if params else None))
        if path == "/repos/owner/repo/pulls/7":
            return {
                "number": 7,
                "title": "fix: core",
                "state": "open",
                "draft": False,
                "mergeable": True,
                "head": {"sha": "b" * 40, "ref": "fix/core"},
                "base": {"sha": "a" * 40, "ref": "main"},
                "labels": [{"name": "bug"}],
                "created_at": "2026-08-30T00:00:00Z",
                "updated_at": "2026-08-30T01:00:00Z",
            }
        if path == "/repos/owner/repo":
            return {"default_branch": "main"}
        if path == "/repos/owner/repo/git/ref/heads/main":
            return {"object": {"sha": "a" * 40}}
        if path == "/repos/owner/repo/pulls/7/files":
            if params and params.get("page") == 1:
                return [{"filename": "src/core.ts"}, {"filename": "tests/core.test.ts"}]
            return []
        if path == "/repos/owner/repo/commits/" + "b" * 40 + "/check-runs":
            if self.check_error:
                raise self.check_error
            if params and params.get("page") == 1:
                return {"check_runs": self.check_runs}
            return {"check_runs": []}
        if path == "/repos/owner/repo/commits/" + "b" * 40 + "/statuses":
            if self.status_error:
                raise self.status_error
            if params and params.get("page") == 1:
                return self.commit_statuses
            return []
        raise AssertionError(f"unexpected API call: {path} {params}")


def test_cloud_acquisition_reads_metadata_files_and_checks_without_source_content():
    api = FakeGitHubAPI()
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)

    assert snapshot["head_sha"] == "b" * 40
    assert snapshot["base_sha"] == snapshot["current_main_sha"] == "a" * 40
    assert snapshot["changed_files"] == ["src/core.ts", "tests/core.test.ts"]
    assert snapshot["checks"][0]["check_run_id"] == 101
    assert snapshot["checks"][0]["head_sha"] == "b" * 40
    assert snapshot["checks"][1]["external_id"] == "github_commit_status:301"
    assert snapshot["collection_complete"] is True
    assert snapshot["source_identity"] == "github_action_rest_v1"

    paths = [path for path, _ in api.calls]
    assert not any("/contents/" in path for path in paths)
    assert not any("/git/blobs/" in path for path in paths)
    assert not any("/zipball" in path or "/tarball" in path for path in paths)


def test_cloud_bundle_is_exact_identity_bound_and_eia_ready():
    snapshot = gha.collect_pr_snapshot(FakeGitHubAPI(), "owner/repo", 7)
    bundle = gha.run_cloud_bundle(snapshot)

    assert bundle["schema"] == "reviewer.repository_intelligence_cloud.v1"
    assert bundle["claim_ceiling"] == "ADVISORY_EVIDENCE_ONLY"
    assert bundle["review_identity"] == ["owner/repo", 7, "b" * 40, "a" * 40, "a" * 40]
    assert bundle["reports"]["readiness"]["result"]["disposition"] == "REVIEW_READY"
    assert bundle["reports"]["cfi"]["result"]["status"] == "UNEXPECTED_FAILURE_OBSERVED"
    assert bundle["reports"]["eia"]["result"]["decision"] == "READY"
    assert gha.verify_cloud_bundle(bundle) is True


def test_cloud_bundle_rejects_rehashed_cross_report_identity_substitution():
    snapshot = gha.collect_pr_snapshot(FakeGitHubAPI(), "owner/repo", 7)
    bundle = gha.run_cloud_bundle(snapshot)
    tampered = copy.deepcopy(bundle)
    tampered["reports"]["cfi"]["result"]["identity"]["head_sha"] = "f" * 40
    tampered["content_sha256"] = gha._hash_payload(tampered)
    assert gha.verify_cloud_bundle(tampered) is False


def test_action_metadata_never_checks_out_or_executes_pull_request_code():
    text = (Path(__file__).resolve().parent.parent / "action.yml").read_text(encoding="utf-8")
    assert "actions/checkout" not in text
    assert "pull_request_target" not in text
    assert '"$GITHUB_ACTION_PATH/adapters/github_action.py"' in text
    assert 'PYTHONPATH="$GITHUB_ACTION_PATH' in text


def test_main_writes_report_summary_and_outputs_without_github_mutation(tmp_path, monkeypatch):
    class FakeClientFactory:
        def __init__(self, *args, **kwargs):
            self.api = FakeGitHubAPI()

        def get_json(self, path, params=None):
            return self.api.get_json(path, params)

    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7}}), encoding="utf-8")
    summary = tmp_path / "summary.md"
    outputs = tmp_path / "outputs.txt"
    report = tmp_path / "ri.json"

    monkeypatch.setattr(gha, "GitHubReadClient", FakeClientFactory)
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))

    code = gha.main(["--output", str(report)])
    assert code == 0
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert gha.verify_cloud_bundle(payload) is True
    assert "Repository Intelligence" in summary.read_text(encoding="utf-8")
    output_text = outputs.read_text(encoding="utf-8")
    assert "eia-decision=READY" in output_text
    assert "claim-ceiling=ADVISORY_EVIDENCE_ONLY" in output_text


def _check_run(status: str = "success") -> dict:
    return {
        "id": 401,
        "name": "ci/test",
        "status": "completed",
        "conclusion": status,
        "head_sha": "b" * 40,
    }


def _commit_status(context: str, state: str, *, status_id: int, sha: str = "b" * 40) -> dict:
    return {
        "id": status_id,
        "context": context,
        "state": state,
        "sha": sha,
        "target_url": f"https://example.invalid/status/{status_id}",
    }


def test_commit_status_failure_is_terminal_and_ready_for_advisory_diagnosis():
    api = FakeGitHubAPI(
        check_runs=[_check_run("success")],
        commit_statuses=[_commit_status("ci/test", "failure", status_id=402)],
    )
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()
    eia = gha.plan_external_intelligence_automation({"cfi_report": cfi}).to_dict()

    assert snapshot["collection_complete"] is True
    assert snapshot["checks"][1]["external_id"] == "github_commit_status:402"
    assert cfi["status"] == "UNEXPECTED_FAILURE_OBSERVED"
    assert cfi["failure_evidence"]["unexpected_failures"][0]["external_id"] == "github_commit_status:402"
    assert eia["decision"] == "READY"


def test_commit_status_error_is_terminal_failure():
    api = FakeGitHubAPI(
        check_runs=[_check_run("success")],
        commit_statuses=[_commit_status("external", "error", status_id=403)],
    )
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert cfi["status"] == "UNEXPECTED_FAILURE_OBSERVED"
    assert cfi["failure_evidence"]["unexpected_count"] == 1


def test_all_latest_commit_status_contexts_success_is_complete_without_failure():
    api = FakeGitHubAPI(
        check_runs=[_check_run("success")],
        commit_statuses=[
            _commit_status("lint", "success", status_id=404),
            _commit_status("unit", "success", status_id=405),
        ],
    )
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert snapshot["collection_complete"] is True
    assert cfi["evidence_completeness"] == "COMPLETE"
    assert cfi["status"] == "NO_TERMINAL_FAILURE"


def test_only_latest_commit_status_for_context_contributes():
    api = FakeGitHubAPI(
        check_runs=[_check_run("success")],
        # GitHub returns newest first, and status contexts are case-insensitive:
        # the success supersedes the historical failure despite casing drift.
        commit_statuses=[
            _commit_status("CI/Test", "success", status_id=406),
            _commit_status("ci/test", "failure", status_id=407),
        ],
    )
    snapshot = gha.collect_pr_snapshot(api, "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    current_statuses = [
        check
        for check in snapshot["checks"]
        if str(check.get("external_id", "")).startswith("github_commit_status:")
    ]
    assert len(current_statuses) == 1
    assert current_statuses[0]["external_id"] == "github_commit_status:406"
    assert cfi["status"] == "NO_TERMINAL_FAILURE"


@pytest.mark.parametrize(
    ("channel", "expected_error"),
    (("statuses", "commit_statuses acquisition failed"), ("check_runs", "check_runs acquisition failed")),
)
def test_required_channel_acquisition_failure_is_incomplete(channel, expected_error):
    kwargs = {"status_error": RuntimeError("status unavailable")} if channel == "statuses" else {"check_error": RuntimeError("checks unavailable")}
    snapshot = gha.collect_pr_snapshot(FakeGitHubAPI(**kwargs), "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert snapshot["collection_complete"] is False
    assert any(expected_error in error for error in snapshot["collection_errors"])
    assert cfi["status"] == "INSUFFICIENT_EVIDENCE"
    assert cfi["evidence_completeness"] == "INCOMPLETE"


def test_malformed_status_response_is_incomplete():
    class MalformedStatuses(FakeGitHubAPI):
        def get_json(self, path, params=None):
            if path.endswith("/statuses") and params and params.get("page") == 1:
                self.calls.append((path, dict(params)))
                return {"statuses": "not-a-list"}
            return super().get_json(path, params)

    snapshot = gha.collect_pr_snapshot(MalformedStatuses(), "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert snapshot["collection_complete"] is False
    assert any("commit_statuses acquisition failed" in error for error in snapshot["collection_errors"])
    assert cfi["status"] == "INSUFFICIENT_EVIDENCE"


def test_malformed_check_run_response_is_incomplete():
    class MalformedCheckRuns(FakeGitHubAPI):
        def get_json(self, path, params=None):
            if path.endswith("/check-runs") and params and params.get("page") == 1:
                self.calls.append((path, dict(params)))
                return {"check_runs": "not-a-list"}
            return super().get_json(path, params)

    snapshot = gha.collect_pr_snapshot(MalformedCheckRuns(), "owner/repo", 7)
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert snapshot["collection_complete"] is False
    assert any("check_runs acquisition failed" in error for error in snapshot["collection_errors"])
    assert cfi["status"] == "INSUFFICIENT_EVIDENCE"


def test_foreign_head_commit_status_is_not_accepted_as_current_evidence():
    snapshot = gha.collect_pr_snapshot(
        FakeGitHubAPI(
            check_runs=[_check_run("success")],
            commit_statuses=[_commit_status("ci/test", "failure", status_id=408, sha="f" * 40)],
        ),
        "owner/repo",
        7,
    )
    cfi = gha.analyze_ci_failure_intelligence(snapshot).to_dict()

    assert snapshot["collection_complete"] is False
    assert not any(
        str(check.get("external_id", "")).startswith("github_commit_status:")
        for check in snapshot["checks"]
    )
    assert cfi["status"] == "INSUFFICIENT_EVIDENCE"
