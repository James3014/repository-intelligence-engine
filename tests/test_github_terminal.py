from __future__ import annotations

import copy
from pathlib import Path

import pytest

from adapters import github_action as gha
from adapters import github_terminal as terminal


HEAD = "b" * 40
BASE = "a" * 40


def _snapshot(*, checks, complete=True, head=HEAD, errors=None):
    return {
        "repository": "owner/repo",
        "pr_number": 7,
        "title": "fix: terminal observation",
        "state": "open",
        "draft": False,
        "mergeable": True,
        "base_branch": "main",
        "base_sha": BASE,
        "head_branch": "fix/terminal",
        "head_sha": head,
        "current_main_sha": BASE,
        "changed_files": ["src/core.py"],
        "issue_numbers": [],
        "labels": [],
        "checks": checks,
        "observed_at": "2026-09-16T00:00:00Z",
        "source_identity": "github_action_rest_v1",
        "collection_complete": complete,
        "collection_errors": list(errors or []),
        "created_at": "2026-09-15T00:00:00Z",
        "updated_at": "2026-09-16T00:00:00Z",
    }


def _check(
    name="ci/test",
    status="success",
    *,
    check_run_id=10,
    run_id=900,
    head=HEAD,
):
    return {
        "name": name,
        "status": status,
        "expected_failure": False,
        "head_sha": head,
        "check_run_id": check_run_id,
        "details_url": f"https://github.com/owner/repo/actions/runs/{run_id}/job/{check_run_id}",
        "app_slug": "github-actions",
    }


def _status(name="jenkins", state="success", *, status_id=30, head=HEAD):
    return {
        "name": name,
        "status": state,
        "expected_failure": False,
        "head_sha": head,
        "external_id": f"github_commit_status:{status_id}",
        "details_url": f"https://ci.example.invalid/status/{status_id}",
    }


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


def _patch_snapshots(monkeypatch, snapshots):
    values = iter(snapshots)
    last = snapshots[-1]

    def collect(_api, _repository, _pr_number):
        nonlocal values
        try:
            return copy.deepcopy(next(values))
        except StopIteration:
            return copy.deepcopy(last)

    monkeypatch.setattr(terminal, "collect_pr_snapshot", collect)


def test_terminal_observation_excludes_only_exact_current_actions_run(monkeypatch):
    self_check = _check("Repository Intelligence terminal", "in_progress", check_run_id=11, run_id=1234)
    external = _check("CI", "success", check_run_id=12, run_id=8888)
    snapshots = [_snapshot(checks=[self_check, external]), _snapshot(checks=[self_check, external])]
    _patch_snapshots(monkeypatch, snapshots)
    clock = FakeClock()

    snapshot, witness = terminal.wait_for_terminal_snapshot(
        object(),
        "owner/repo",
        7,
        expected_head_sha=HEAD,
        current_actions_run_id=1234,
        timeout_seconds=5,
        poll_seconds=1,
        quiescence_seconds=1,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    assert snapshot["head_sha"] == HEAD
    assert witness["semantics"] == terminal.TERMINAL_SNAPSHOT_SEMANTICS
    assert witness["excluded_current_run_check_count"] == 1
    assert witness["observed_external_check_count"] == 1
    assert witness["observed_checks"][0]["name"] == "CI"


def test_same_name_check_from_different_run_is_not_excluded(monkeypatch):
    external_same_name = _check(
        "Repository Intelligence terminal", "in_progress", check_run_id=12, run_id=9999
    )
    _patch_snapshots(monkeypatch, [_snapshot(checks=[external_same_name])])
    clock = FakeClock()

    with pytest.raises(RuntimeError, match="timed out"):
        terminal.wait_for_terminal_snapshot(
            object(),
            "owner/repo",
            7,
            expected_head_sha=HEAD,
            current_actions_run_id=1234,
            timeout_seconds=1,
            poll_seconds=0.5,
            quiescence_seconds=0.5,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )


def test_pending_commit_status_prevents_terminal_proof(monkeypatch):
    _patch_snapshots(monkeypatch, [_snapshot(checks=[_status(state="pending")])])
    clock = FakeClock()

    with pytest.raises(RuntimeError, match="timed out"):
        terminal.wait_for_terminal_snapshot(
            object(),
            "owner/repo",
            7,
            expected_head_sha=HEAD,
            current_actions_run_id=1234,
            timeout_seconds=1,
            poll_seconds=0.5,
            quiescence_seconds=0.5,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )


def test_incomplete_acquisition_prevents_terminal_proof(monkeypatch):
    _patch_snapshots(
        monkeypatch,
        [_snapshot(checks=[_check()], complete=False, errors=["check_runs acquisition failed"])],
    )
    clock = FakeClock()

    with pytest.raises(RuntimeError, match="timed out"):
        terminal.wait_for_terminal_snapshot(
            object(),
            "owner/repo",
            7,
            expected_head_sha=HEAD,
            current_actions_run_id=1234,
            timeout_seconds=1,
            poll_seconds=0.5,
            quiescence_seconds=0.5,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )


def test_only_current_run_does_not_count_as_external_evidence(monkeypatch):
    self_check = _check("terminal", "in_progress", check_run_id=11, run_id=1234)
    _patch_snapshots(monkeypatch, [_snapshot(checks=[self_check])])
    clock = FakeClock()

    with pytest.raises(RuntimeError, match="timed out"):
        terminal.wait_for_terminal_snapshot(
            object(),
            "owner/repo",
            7,
            expected_head_sha=HEAD,
            current_actions_run_id=1234,
            timeout_seconds=1,
            poll_seconds=0.5,
            quiescence_seconds=0.5,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )


def test_head_drift_fails_closed_immediately(monkeypatch):
    _patch_snapshots(monkeypatch, [_snapshot(checks=[_check()], head="f" * 40)])
    clock = FakeClock()

    with pytest.raises(RuntimeError, match="head changed"):
        terminal.wait_for_terminal_snapshot(
            object(),
            "owner/repo",
            7,
            expected_head_sha=HEAD,
            current_actions_run_id=1234,
            timeout_seconds=5,
            poll_seconds=1,
            quiescence_seconds=1,
            monotonic_fn=clock.monotonic,
            sleep_fn=clock.sleep,
        )


def test_changed_terminal_set_resets_quiescence(monkeypatch):
    first = _snapshot(checks=[_check("unit", check_run_id=1)])
    changed = _snapshot(checks=[_check("unit", check_run_id=1), _check("lint", check_run_id=2)])
    stable = _snapshot(checks=[_check("unit", check_run_id=1), _check("lint", check_run_id=2)])
    _patch_snapshots(monkeypatch, [first, changed, stable])
    clock = FakeClock()

    _, witness = terminal.wait_for_terminal_snapshot(
        object(),
        "owner/repo",
        7,
        expected_head_sha=HEAD,
        current_actions_run_id=1234,
        timeout_seconds=5,
        poll_seconds=1,
        quiescence_seconds=1,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    assert witness["observed_external_check_count"] == 2
    assert witness["stable_observations"] == 2
    assert clock.value == 2


def test_terminal_bundle_wraps_and_reverifies_canonical_cloud_bundle(monkeypatch):
    snapshot = _snapshot(checks=[_check("unit", check_run_id=1), _status()])
    _patch_snapshots(monkeypatch, [snapshot, snapshot])
    clock = FakeClock()
    final_snapshot, witness = terminal.wait_for_terminal_snapshot(
        object(),
        "owner/repo",
        7,
        expected_head_sha=HEAD,
        current_actions_run_id=1234,
        timeout_seconds=5,
        poll_seconds=1,
        quiescence_seconds=1,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    bundle = terminal.run_terminal_cloud_bundle(final_snapshot, witness)
    assert bundle["claim_ceiling"] == "ADVISORY_EVIDENCE_ONLY"
    assert bundle["snapshot_semantics"] == terminal.TERMINAL_SNAPSHOT_SEMANTICS
    assert gha.verify_cloud_bundle(bundle["cloud_bundle"]) is True
    assert terminal.verify_terminal_cloud_bundle(bundle) is True


def test_terminal_bundle_rejects_semantic_tamper_even_when_rehashed(monkeypatch):
    snapshot = _snapshot(checks=[_check()])
    _patch_snapshots(monkeypatch, [snapshot, snapshot])
    clock = FakeClock()
    final_snapshot, witness = terminal.wait_for_terminal_snapshot(
        object(),
        "owner/repo",
        7,
        expected_head_sha=HEAD,
        current_actions_run_id=1234,
        timeout_seconds=5,
        poll_seconds=1,
        quiescence_seconds=1,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )
    bundle = terminal.run_terminal_cloud_bundle(final_snapshot, witness)

    tampered = copy.deepcopy(bundle)
    tampered["terminal_observation"]["observed_checks"][0]["status"] = "in_progress"
    tampered["terminal_observation"]["observed_check_fingerprint"] = terminal._checks_fingerprint(
        tampered["terminal_observation"]["observed_checks"]
    )
    tampered["content_sha256"] = gha._hash_payload(tampered)
    assert terminal.verify_terminal_cloud_bundle(tampered) is False


def test_legacy_event_bundle_remains_canonically_verifiable():
    legacy = gha.run_cloud_bundle(_snapshot(checks=[_check()]))
    assert "snapshot_semantics" not in legacy
    assert gha.verify_cloud_bundle(legacy) is True
    assert terminal.verify_terminal_cloud_bundle(legacy) is False


def test_terminal_action_never_checks_out_or_executes_pull_request_code():
    text = (
        Path(__file__).resolve().parent.parent / "terminal" / "action.yml"
    ).read_text(encoding="utf-8")
    assert "actions/checkout" not in text
    assert "pull_request_target" not in text
    assert "github_terminal.py" in text
    assert 'GITHUB_RUN_ID' in text
    assert 'RI_EXPECTED_HEAD_SHA' in text
