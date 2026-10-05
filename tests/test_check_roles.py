from __future__ import annotations

import copy

from repository_intelligence.check_roles import (
    ADVISORY_CHECK,
    REQUIRED_GATE,
    UNKNOWN_POLICY_ROLE,
    classify_check_roles,
    verify_check_role_report,
)


IDENTITY = {
    "repository": "owner/repo",
    "pr_number": 7,
    "head_sha": "head",
    "base_sha": "base",
    "current_main_sha": "main",
}


def test_required_failure_blocks_but_advisory_failure_only_degrades():
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[
            {"name": "tests", "conclusion": "failure", "head_sha": "head"},
            {"name": "observer", "conclusion": "failure", "head_sha": "head"},
        ],
        policy_roles={"tests": REQUIRED_GATE, "observer": ADVISORY_CHECK},
        previous_check_names=("tests", "observer"),
    )
    assert report["required_gate_state"] == "BLOCKED"
    assert report["required_blockers"] == ["tests"]
    assert report["advisory_degraded"] == ["observer"]
    assert report["observer_health"] == "DEGRADED"


def test_advisory_timeout_is_incomplete_not_product_failure():
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[{"name": "observer", "status": "timeout", "head_sha": "head"}],
        policy_roles={"observer": ADVISORY_CHECK},
        previous_check_names=("observer",),
    )
    assert report["required_gate_state"] == "CLEAR"
    assert report["checks"][0]["observer_state"] == "ADVISORY_INCOMPLETE"
    assert report["advisory_disposition"] == "ADVISORY_INCOMPLETE"


def test_missing_policy_role_is_explicit_unknown():
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[{"name": "mystery", "conclusion": "success", "head_sha": "head"}],
        policy_roles={},
    )
    assert report["checks"][0]["role"] == UNKNOWN_POLICY_ROLE
    assert report["unknown_policy_role"] == ["mystery"]


def test_duplicate_names_fail_closed_to_unknown_role():
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[
            {"name": "tests", "conclusion": "success", "head_sha": "head"},
            {"name": "tests", "conclusion": "failure", "head_sha": "head"},
        ],
        policy_roles={"tests": REQUIRED_GATE},
    )
    assert report["unknown_policy_role"] == ["tests"]
    assert {row["role"] for row in report["checks"]} == {UNKNOWN_POLICY_ROLE}


def test_check_set_change_is_explicitly_advisory_incomplete():
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[
            {"name": "tests", "conclusion": "success", "head_sha": "head"},
            {"name": "observer", "conclusion": "success", "head_sha": "head"},
        ],
        policy_roles={"tests": REQUIRED_GATE, "observer": ADVISORY_CHECK},
        previous_check_names=("tests",),
    )
    assert report["check_set_observation"]["stability"] == "CHANGED"
    assert report["advisory_disposition"] == "ADVISORY_INCOMPLETE"
    assert report["required_gate_state"] == "CLEAR"


def test_check_set_changes_change_content_hash_without_changing_identity():
    one = classify_check_roles(
        review_identity=IDENTITY,
        checks=[{"name": "tests", "conclusion": "success", "head_sha": "head"}],
        policy_roles={"tests": REQUIRED_GATE},
    )
    two = classify_check_roles(
        review_identity=IDENTITY,
        checks=[
            {"name": "tests", "conclusion": "success", "head_sha": "head"},
            {"name": "observer", "conclusion": "success", "head_sha": "head"},
        ],
        policy_roles={"tests": REQUIRED_GATE, "observer": ADVISORY_CHECK},
    )
    assert one["review_identity"] == two["review_identity"]
    assert one["content_sha256"] != two["content_sha256"]


def test_stale_or_missing_check_head_fails_closed():
    for check in (
        {"name": "tests", "conclusion": "success", "head_sha": "old-head"},
        {"name": "tests", "conclusion": "success"},
    ):
        report = classify_check_roles(
            review_identity=IDENTITY,
            checks=[check],
            policy_roles={"tests": REQUIRED_GATE},
            previous_check_names=("tests",),
        )
        assert report["required_gate_state"] == "BLOCKED"
        assert report["required_blockers"] == ["tests"]
        assert report["checks"][0]["identity_bound"] is False


def test_report_verifier_rejects_tamper():
    policy = {"tests": REQUIRED_GATE, "observer": ADVISORY_CHECK}
    report = classify_check_roles(
        review_identity=IDENTITY,
        checks=[
            {"name": "tests", "conclusion": "success", "head_sha": "head"},
            {"name": "observer", "status": "timeout", "head_sha": "head"},
        ],
        policy_roles=policy,
        previous_check_names=("tests", "observer"),
    )
    assert verify_check_role_report(report, policy_roles=policy) is True
    tampered = copy.deepcopy(report)
    tampered["required_gate_state"] = "BLOCKED"
    assert verify_check_role_report(tampered, policy_roles=policy) is False
