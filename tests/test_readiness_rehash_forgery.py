"""Issue #86 residuals: readiness cannot be forged by re-hashing.

The verifiers re-derive disposition, identity flags and completeness from the
payload itself (as cfi.py re-derives its status). Every genuine builder output
must still verify.
"""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import github_action as gha
from repository_intelligence import core as ri
from repository_intelligence.models import CheckObservation, PRSnapshot
from test_github_action import FakeGitHubAPI


class MergeBaseAPI(FakeGitHubAPI):
    """Stale base (main != base) with a selectable merge-base answer."""

    resolved = False

    def get_json(self, path, params=None):
        if path == "/repos/owner/repo/git/ref/heads/main":
            return {"object": {"sha": "c" * 40}}
        if path.startswith("/repos/owner/repo/compare/"):
            if self.resolved:
                return {"merge_base_commit": {"sha": "d" * 40}}
            raise RuntimeError("GitHub HTTP 404: No common ancestor between main and head")
        return super().get_json(path, params)


class ResolvedAPI(MergeBaseAPI):
    resolved = True


def _bundle(api_cls):
    return gha.run_cloud_bundle(gha.collect_pr_snapshot(api_cls(), "owner/repo", 7))


def _pr(n=1, **kw):
    base = dict(
        repository="owner/repo", pr_number=n, title="t", state="open", draft=False,
        mergeable=True, base_branch="main", base_sha="m" * 8, head_branch=f"f{n}",
        head_sha=f"h{n}", current_main_sha="m" * 8, changed_files=(f"a{n}.py",),
        checks=(CheckObservation(name="ci", status="success"),),
    )
    base.update(kw)
    return PRSnapshot(**base)


def _rehash_bundle(bundle):
    bundle["content_sha256"] = gha._hash_payload(bundle)
    return bundle


def _rehash_report(report):
    report["content_sha256"] = ri._content_hash(report)
    return report


def _force_ready(item):
    item.update(disposition="REVIEW_READY", is_review_ready=True)


# ---------------------------------------------------------------- genuine

GENUINE_SNAPSHOTS = {
    "clean": [_pr()],
    "stale_base_unknown_merge_base": [_pr(base_sha="b" * 8)],
    "stale_base_resolved_merge_base": [_pr(base_sha="b" * 8, merge_base_status="RESOLVED")],
    "no_merge_base": [_pr(base_sha="b" * 8, merge_base_status="NONE")],
    "draft": [_pr(draft=True)],
    "non_mergeable": [_pr(mergeable=False)],
    "mergeable_unknown": [_pr(mergeable=None)],
    "incomplete_collection": [_pr(collection_complete=False)],
    "collection_errors": [_pr(collection_errors=("boom",))],
    "declared_head_stale": [_pr(declared_head_sha="x" * 8)],
    "declared_base_stale": [_pr(declared_base_sha="x" * 8)],
    "declared_main_stale": [_pr(declared_main_sha="x" * 8)],
    "do_not_merge": [_pr(do_not_merge=True)],
    "stale_label": [_pr(labels=("long-lived",))],
    "invalid_identity": [_pr(head_sha="")],
    "invalid_repo": [_pr(repository="bad")],
    "multiple_independent": [_pr(1), _pr(2), _pr(3, draft=True)],
    "multiple_overlapping": [_pr(1, changed_files=("x.py",)), _pr(2, changed_files=("x.py",))],
    "mixed_main": [_pr(1), _pr(2, current_main_sha="z" * 8, base_sha="z" * 8)],
    "mixed_repository": [_pr(1), _pr(2, repository="owner/other")],
    "empty": [],
    "empty_base_sha": [_pr(base_sha="")],
    "empty_main_sha": [_pr(current_main_sha="")],
    "empty_head_sha_stale_base": [_pr(head_sha="", base_sha="b" * 8)],
    "empty_base_and_main": [_pr(base_sha="", current_main_sha="")],
    "empty_base_among_valid": [_pr(1), _pr(2, base_sha=""), _pr(3, current_main_sha="")],
    "empty_base_no_merge_base": [_pr(base_sha="", merge_base_status="NONE")],
    "empty_base_resolved": [_pr(base_sha="", merge_base_status="RESOLVED")],
    "overlap_with_pr_zero": [_pr(1, changed_files=("x.py",)), _pr(0, changed_files=("x.py",))],
    "overlap_with_negative_pr": [_pr(1, changed_files=("x.py",)), _pr(-3, changed_files=("x.py",))],
    "none_base_sha": [_pr(base_sha=None)],
    "none_main_sha": [_pr(current_main_sha=None)],
    "none_base_empty_main": [_pr(base_sha=None, current_main_sha="")],
    "mapping_empty_base": [dict(
        repository="owner/repo", pr_number=1, title="t", state="open", draft=False,
        mergeable=True, base_branch="main", base_sha="", head_branch="f", head_sha="h1",
        current_main_sha="m", changed_files=["a.py"], checks=[],
    )],
    "mapping_empty_main": [dict(
        repository="owner/repo", pr_number=1, title="t", state="open", draft=False,
        mergeable=True, base_branch="main", base_sha="b", head_branch="f", head_sha="h1",
        current_main_sha="", changed_files=["a.py"], checks=[],
    )],
}


@pytest.mark.parametrize("name", sorted(GENUINE_SNAPSHOTS))
def test_genuine_report_verifies(name):
    report = ri.build_repository_intelligence_report(GENUINE_SNAPSHOTS[name]).to_dict()
    assert ri.verify_repository_intelligence_report(report) is True


@pytest.mark.parametrize("name", sorted(n for n in GENUINE_SNAPSHOTS if GENUINE_SNAPSHOTS[n]))
def test_genuine_single_readiness_is_coherent(name):
    snap = GENUINE_SNAPSHOTS[name][0]
    assert ri.readiness_item_is_coherent(ri.classify_readiness(snap).to_dict()) is True


@pytest.mark.parametrize("api_cls", [FakeGitHubAPI, MergeBaseAPI, ResolvedAPI])
def test_genuine_bundle_verifies(api_cls):
    assert gha.verify_cloud_bundle(_bundle(api_cls)) is True


def test_resolved_merge_base_on_stale_base_is_legitimately_review_ready():
    bundle = _bundle(ResolvedAPI)
    readiness = bundle["reports"]["readiness"]["result"]
    assert readiness["disposition"] == "REVIEW_READY"
    assert readiness["identity"]["stale_base"] is True
    assert gha.verify_cloud_bundle(bundle) is True


# ----------------------------------------------------- forged: bundle level

def _clear(r):
    r.update(findings=[], reasons=[], evidence_gaps=[], risk="LOW")


def _f_blockers_kept_flag_flipped(r):
    _force_ready(r)
    r["identity"]["no_unique_merge_base"] = False


def _f_full_forge_flag_flipped(r):
    _force_ready(r)
    _clear(r)
    r["identity"]["no_unique_merge_base"] = False


def _f_nuMB_flag_true_without_finding(r):
    r["identity"]["no_unique_merge_base"] = False
    r["findings"] = [f for f in r["findings"] if f != "NO_UNIQUE_MERGE_BASE"]


def _f_ready_with_draft_finding(r):
    _force_ready(r)
    r["findings"] = ["DRAFT"]
    r["identity"]["no_unique_merge_base"] = False


def _f_disposition_not_function_of_findings(r):
    r["disposition"] = "EXCLUDED"  # findings say STALE / NO_UNIQUE_MERGE_BASE
    r["is_review_ready"] = False


def _f_stale_base_flag_cleared(r):
    _force_ready(r)
    _clear(r)
    r["identity"].update(stale_base=False, no_unique_merge_base=False)


def _f_declared_base_hidden(r):
    _force_ready(r)
    _clear(r)
    r["identity"].update(
        declared_base_sha="x" * 40, stale_declared_base=False, stale_evidence=False,
        no_unique_merge_base=False,
    )


def _f_valid_with_identity_gaps(r):
    _force_ready(r)
    _clear(r)
    r["identity"].update(no_unique_merge_base=False)
    r["identity"]["evidence_gaps"] = ["repository domain or format invalid"]


def _f_complete_with_gaps(r):
    r["evidence_completeness"] = "COMPLETE"
    r["is_review_ready"] = False
    r["evidence_gaps"] = ["merge-base with current main unknown"]


def _f_incomplete_collection_marked_complete(r):
    r["findings"] = list(r["findings"]) + ["COLLECTION_INCOMPLETE"]
    r["evidence_completeness"] = "COMPLETE"


@pytest.mark.parametrize(
    "mutate",
    [
        _f_blockers_kept_flag_flipped,
        _f_full_forge_flag_flipped,
        _f_nuMB_flag_true_without_finding,
        _f_ready_with_draft_finding,
        _f_disposition_not_function_of_findings,
        _f_stale_base_flag_cleared,
        _f_declared_base_hidden,
        _f_valid_with_identity_gaps,
        _f_complete_with_gaps,
        _f_incomplete_collection_marked_complete,
    ],
    ids=lambda f: f.__name__,
)
def test_rehashed_readiness_in_bundle_is_rejected(mutate):
    bundle = copy.deepcopy(_bundle(MergeBaseAPI))
    assert gha.verify_cloud_bundle(bundle) is True
    mutate(bundle["reports"]["readiness"]["result"])
    assert gha.verify_cloud_bundle(_rehash_bundle(bundle)) is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("is_valid", False),
        ("stale_base", False),
        ("stale_evidence", True),
        ("no_unique_merge_base", False),
        ("declared_head_sha", "x" * 40),
    ],
)
@pytest.mark.parametrize("target", ["readiness", "cfi", "eia"])
def test_bundle_identity_must_match_across_reports(target, key, value):
    if target == "eia" and key == "no_unique_merge_base":
        pytest.skip("EIA identity legitimately omits the merge-base probe result")
    bundle = copy.deepcopy(_bundle(MergeBaseAPI))
    bundle["reports"][target]["result"]["identity"][key] = value
    assert gha.verify_cloud_bundle(_rehash_bundle(bundle)) is False


# ---------------------------------------------------- forged: report level

def _item0(report):
    return report["items"][0]


def _r_ready_keeps_draft(report):
    _force_ready(_item0(report))


def _r_ready_stale_base_flag_cleared(report):
    it = _item0(report)
    _force_ready(it)
    it["identity"]["stale_base"] = False


def _r_empty_head_sha_valid(report):
    it = _item0(report)
    it["identity"]["head_sha"] = ""
    it["identity"]["review_identity"][2] = ""
    _force_ready(it)


def _r_is_valid_true_with_bad_repo(report):
    it = _item0(report)
    it["identity"]["repository"] = "bad"
    it["identity"]["review_identity"][0] = "bad"
    it["repository"] = "bad"


def _r_stale_declared_hidden(report):
    it = _item0(report)
    it["identity"]["declared_head_sha"] = "x" * 8
    it["identity"]["stale_declared_head"] = False


def _r_stale_evidence_not_or_of_declared(report):
    it = _item0(report)
    it["identity"]["declared_main_sha"] = "x" * 8
    it["identity"]["stale_declared_main"] = True
    it["identity"]["stale_evidence"] = False


def _r_findings_cleared_disposition_kept(report):
    _item0(report)["findings"] = []  # DRAFT disposition EXCLUDED no longer derivable


def _r_complete_with_gaps(report):
    it = _item0(report)
    it["evidence_completeness"] = "COMPLETE"
    it["evidence_gaps"] = ["x"]


def _r_top_complete_item_incomplete(report):
    _item0(report)["evidence_completeness"] = "INCOMPLETE"
    report["evidence_completeness"] = "COMPLETE"


def _r_top_gaps_stripped(report):
    report["evidence_gaps"] = []


def _r_top_gaps_injected(report):
    report["evidence_gaps"] = list(report["evidence_gaps"]) + ["pr:1:made up"]


def _r_top_partial_downgrade(report):
    _item0(report)["evidence_completeness"] = "INCOMPLETE"
    _item0(report)["evidence_gaps"] = ["x"]
    report["evidence_completeness"] = "PARTIAL"
    report["evidence_gaps"] = ["pr:1:x"]


def _r_empty_items_complete(report):
    report["items"] = []
    report["evidence_completeness"] = "COMPLETE"
    report["evidence_gaps"] = []


def _r_mixed_main_complete(report):
    other = copy.deepcopy(_item0(report))
    other["identity"]["current_main_sha"] = "zzz"
    other["identity"]["review_identity"][4] = "zzz"
    other["identity"]["pr_number"] = 2
    other["identity"]["review_identity"][1] = 2
    other["pr_number"] = 2
    report["items"].append(other)
    report["evidence_completeness"] = "COMPLETE"


def _r_wait_rebind_without_overlap(report):
    it = _item0(report)
    it["disposition"] = "WAIT_REBIND"
    it["findings"] = [f for f in it["findings"] if f not in ("DRAFT",)]
    it["is_review_ready"] = False


def _draft_report():
    return ri.build_repository_intelligence_report([_pr(draft=True, base_sha="b" * 8)]).to_dict()


@pytest.mark.parametrize(
    "mutate",
    [
        _r_ready_keeps_draft,
        _r_ready_stale_base_flag_cleared,
        _r_empty_head_sha_valid,
        _r_is_valid_true_with_bad_repo,
        _r_stale_declared_hidden,
        _r_stale_evidence_not_or_of_declared,
        _r_findings_cleared_disposition_kept,
        _r_complete_with_gaps,
        _r_top_complete_item_incomplete,
        _r_top_gaps_stripped,
        _r_top_gaps_injected,
        _r_top_partial_downgrade,
        _r_empty_items_complete,
        _r_mixed_main_complete,
        _r_wait_rebind_without_overlap,
    ],
    ids=lambda f: f.__name__,
)
def test_rehashed_report_is_rejected(mutate):
    report = copy.deepcopy(_draft_report())
    assert ri.verify_repository_intelligence_report(report) is True
    mutate(report)
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False


# ------------------------------------------------- cross-model review round 1

def _snapshot(api_cls=ResolvedAPI, **overrides):
    snap = dict(gha.collect_pr_snapshot(api_cls(), "owner/repo", 7))
    snap.update(overrides)
    return snap


GENUINE_BUNDLE_VARIANTS = {
    "declared_head_empty": dict(declared_head_sha=""),
    "declared_base_empty": dict(declared_base_sha=""),
    "declared_main_empty": dict(declared_main_sha=""),
    "declared_all_empty": dict(declared_head_sha="", declared_base_sha="", declared_main_sha=""),
    "declared_all_none": dict(declared_head_sha=None, declared_base_sha=None, declared_main_sha=None),
    "declared_head_stale": dict(declared_head_sha="x" * 40),
    "draft": dict(draft=True),
    "mergeable_unknown": dict(mergeable=None),
    "collection_incomplete": dict(collection_complete=False),
    "collection_errors": dict(collection_errors=["boom"]),
    "do_not_merge": dict(do_not_merge=True),
}


@pytest.mark.parametrize("name", sorted(GENUINE_BUNDLE_VARIANTS))
@pytest.mark.parametrize("api_cls", [MergeBaseAPI, ResolvedAPI])
def test_genuine_bundle_variants_verify(api_cls, name):
    bundle = gha.run_cloud_bundle(_snapshot(api_cls, **GENUINE_BUNDLE_VARIANTS[name]))
    assert gha.verify_cloud_bundle(bundle) is True


def _overlap_report():
    snaps = [_pr(1, changed_files=("x.py",)), _pr(2, changed_files=("x.py",))]
    return ri.build_repository_intelligence_report(snaps).to_dict()


def test_genuine_overlap_report_is_wait_rebind_and_verifies():
    report = _overlap_report()
    assert [i["disposition"] for i in report["items"]] == ["WAIT_REBIND", "WAIT_REBIND"]
    assert ri.verify_repository_intelligence_report(report) is True


def _o_both_ready(report):
    for it in report["items"]:
        _force_ready(it)


def _o_one_ready(report):
    _force_ready(report["items"][0])


def _o_overlaps_dropped_one_sided(report):
    _force_ready(report["items"][0])
    report["items"][0]["overlaps"] = {}
    report["items"][0]["findings"] = [f for f in report["items"][0]["findings"] if f != "PATH_OVERLAP"]


def _o_overlaps_asymmetric(report):
    report["items"][1]["overlaps"] = {}
    report["items"][1]["findings"] = [f for f in report["items"][1]["findings"] if f != "PATH_OVERLAP"]


def _o_path_overlap_finding_without_overlaps(report):
    report["items"][0]["overlaps"] = {}


@pytest.mark.parametrize(
    "mutate",
    [_o_both_ready, _o_one_ready, _o_overlaps_dropped_one_sided, _o_overlaps_asymmetric,
     _o_path_overlap_finding_without_overlaps],
    ids=lambda f: f.__name__,
)
def test_rehashed_overlap_forgery_is_rejected(mutate):
    report = copy.deepcopy(_overlap_report())
    mutate(report)
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False


def _clean_report():
    return ri.build_repository_intelligence_report([_pr()]).to_dict()


def _m_findings_dict_element(report):
    _item0(report)["findings"] = [{}]


def _m_findings_not_list(report):
    _item0(report)["findings"] = "DRAFT"


def _m_findings_unhashable_nested(report):
    _item0(report)["findings"] = [["x"]]


def _m_identity_not_dict(report):
    _item0(report)["identity"] = []


def _m_identity_key_missing(report):
    del _item0(report)["identity"]["is_valid"]


def _m_identity_gaps_non_str(report):
    _item0(report)["identity"]["evidence_gaps"] = [{}]


def _m_item_gaps_non_str(report):
    _item0(report)["evidence_gaps"] = [{}]


def _m_overlaps_bad(report):
    _item0(report)["overlaps"] = {"1": [{}]}


def _m_completeness_missing(report):
    del _item0(report)["evidence_completeness"]


def _m_repo_non_str(report):
    _item0(report)["identity"]["repository"] = {}


@pytest.mark.parametrize(
    "mutate",
    [_m_findings_dict_element, _m_findings_not_list, _m_findings_unhashable_nested,
     _m_identity_not_dict, _m_identity_key_missing, _m_identity_gaps_non_str,
     _m_item_gaps_non_str, _m_overlaps_bad, _m_completeness_missing, _m_repo_non_str],
    ids=lambda f: f.__name__,
)
def test_malformed_input_returns_false_not_raises(mutate):
    report = copy.deepcopy(_clean_report())
    mutate(report)
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False
    bundle = copy.deepcopy(_bundle(ResolvedAPI))
    # Same mutation shape applied to the bundle's readiness result.
    wrapper = {"items": [bundle["reports"]["readiness"]["result"]]}
    mutate(wrapper)
    assert gha.verify_cloud_bundle(_rehash_bundle(bundle)) is False


def _b_merge_base_unknown_on_fresh_base(report):
    it = _item0(report)
    it["findings"] = list(it["findings"]) + ["MERGE_BASE_UNKNOWN"]
    it["evidence_gaps"] = ["merge-base with current main unknown"]
    _force_ready(it)


def _b_merge_base_gap_without_finding(report):
    _item0(report)["evidence_gaps"] = ["merge-base with current main unknown"]


def _b_unknown_and_none_together(report):
    it = _item0(report)
    it["identity"]["base_sha"] = "b" * 8
    it["identity"]["review_identity"][3] = "b" * 8
    it["identity"]["stale_base"] = True
    it["findings"] = ["STALE_BASE", "MERGE_BASE_UNKNOWN", "NO_UNIQUE_MERGE_BASE"]
    it["identity"]["no_unique_merge_base"] = True
    it["disposition"] = "STALE"
    it["is_review_ready"] = False
    it["evidence_gaps"] = ["merge-base with current main unknown"]


def _b_mergeable_gap_without_finding(report):
    it = _item0(report)
    it["evidence_gaps"] = ["mergeable state unknown"]
    it["evidence_completeness"] = "PARTIAL"
    report["evidence_completeness"] = "PARTIAL"
    report["evidence_gaps"] = ["pr:1:mergeable state unknown"]


@pytest.mark.parametrize(
    "mutate",
    [_b_merge_base_unknown_on_fresh_base, _b_merge_base_gap_without_finding,
     _b_unknown_and_none_together, _b_mergeable_gap_without_finding],
    ids=lambda f: f.__name__,
)
def test_finding_preconditions_are_checked(mutate):
    report = copy.deepcopy(_clean_report())
    mutate(report)
    report["evidence_gaps"] = [f"pr:1:{g}" for g in _item0(report)["evidence_gaps"]]
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False


def _p_partial_no_gaps(report):
    _item0(report)["evidence_completeness"] = "PARTIAL"
    report["evidence_completeness"] = "PARTIAL"


def _p_complete_but_collection_errors(report):
    # genuine item is PARTIAL because of a collection error; claim COMPLETE
    it = _item0(report)
    it["evidence_completeness"] = "COMPLETE"
    report["evidence_completeness"] = "COMPLETE"


def _p_mergeable_unknown_marked_complete(report):
    it = _item0(report)
    it["evidence_completeness"] = "COMPLETE"
    report["evidence_completeness"] = "COMPLETE"


@pytest.mark.parametrize("mutate", [_p_partial_no_gaps], ids=lambda f: f.__name__)
def test_partial_completeness_must_be_derivable(mutate):
    report = copy.deepcopy(_clean_report())
    mutate(report)
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False


@pytest.mark.parametrize("mutate", [_p_complete_but_collection_errors, _p_mergeable_unknown_marked_complete],
                         ids=lambda f: f.__name__)
@pytest.mark.parametrize("snap", [_pr(collection_errors=("boom",)), _pr(mergeable=None)], ids=["errors", "unknown"])
def test_downgraded_partial_is_rejected(mutate, snap):
    report = ri.build_repository_intelligence_report([snap]).to_dict()
    assert _item0(report)["evidence_completeness"] == "PARTIAL"
    mutate(report)
    assert ri.verify_repository_intelligence_report(_rehash_report(report)) is False


def test_duplicate_pr_numbers_fail_closed_by_design():
    # Real open-PR lists never repeat a number, and a duplicate would let a forger
    # dodge the overlap-graph check, so such reports intentionally do not verify.
    for snaps in (
        [_pr(1, head_sha="h-a"), _pr(1, head_sha="h-b")],
        [_pr(0, changed_files=("x.py",)), _pr(0, changed_files=("x.py",))],
    ):
        report = ri.build_repository_intelligence_report(snaps).to_dict()
        assert ri.verify_repository_intelligence_report(report) is False
