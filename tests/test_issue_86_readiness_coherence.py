"""Issue #86: re-hashed readiness forgery must be rejected by both verifiers."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import github_action as gha
from repository_intelligence import core as ri
from repository_intelligence.models import CheckObservation, PRSnapshot
from test_github_action import FakeGitHubAPI


class StaleBaseAPI(FakeGitHubAPI):
    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/git/ref/heads/main":
            return {"object": {"sha": "c" * 40}}
        return super().get_json(path, params)


def _stale_bundle():
    return gha.run_cloud_bundle(gha.collect_pr_snapshot(StaleBaseAPI(), "owner/repo", 7))


def _rehash_bundle(bundle):
    bundle["content_sha256"] = gha._hash_payload(bundle)
    return bundle


def test_genuine_stale_bundle_still_verifies_and_is_not_ready():
    bundle = _stale_bundle()
    result = bundle["reports"]["readiness"]["result"]
    assert result["disposition"] == "STALE" and result["is_review_ready"] is False
    assert gha.verify_cloud_bundle(bundle) is True


def test_cloud_bundle_rejects_rehashed_review_ready_on_stale_base():
    t = copy.deepcopy(_stale_bundle())
    t["reports"]["readiness"]["result"].update(
        disposition="REVIEW_READY", is_review_ready=True, findings=[], reasons=[], evidence_gaps=[], risk="LOW"
    )
    assert gha.verify_cloud_bundle(_rehash_bundle(t)) is False


def test_cloud_bundle_rejects_rehashed_is_review_ready_flag_alone():
    t = copy.deepcopy(_stale_bundle())
    t["reports"]["readiness"]["result"]["is_review_ready"] = True
    assert gha.verify_cloud_bundle(_rehash_bundle(t)) is False


def test_cloud_bundle_rejects_rehashed_review_ready_with_invalid_identity():
    bundle = gha.run_cloud_bundle(gha.collect_pr_snapshot(FakeGitHubAPI(), "owner/repo", 7))
    assert gha.verify_cloud_bundle(bundle) is True
    t = copy.deepcopy(bundle)
    t["reports"]["readiness"]["result"]["identity"]["is_valid"] = False
    assert gha.verify_cloud_bundle(_rehash_bundle(t)) is False


def _report_payload():
    pr = PRSnapshot(
        repository="owner/repo", pr_number=1, title="t", state="open", draft=True, mergeable=True,
        base_branch="main", base_sha="base1", head_branch="f", head_sha="head1",
        current_main_sha="main2", changed_files=("a.py",), checks=(CheckObservation(name="ci", status="success"),),
    )
    return ri.build_repository_intelligence_report([pr]).to_dict()


def test_report_verifier_accepts_genuine_report():
    assert ri.verify_repository_intelligence_report(_report_payload()) is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i: (i.update(disposition="REVIEW_READY", is_review_ready=True), i["identity"].update(is_valid=False)),
        lambda i: i.update(disposition="REVIEW_READY", is_review_ready=True),
        lambda i: i.update(is_review_ready=True),
    ],
)
def test_report_verifier_rejects_rehashed_incoherent_readiness(mutate):
    p = _report_payload()
    mutate(p["items"][0])
    p["content_sha256"] = ri._content_hash(p)
    assert ri.verify_repository_intelligence_report(p) is False
