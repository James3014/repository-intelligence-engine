"""Issue #57: deterministic guard semantic delta advisory evidence."""
from __future__ import annotations

import copy
import hashlib
import json

import repository_intelligence as ri


A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64


def _rehash(payload):
    unsigned = copy.deepcopy(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    return payload


def _snapshots():
    return {
        "old_snapshot": {
            "repository": "owner/repo",
            "pr_number": 57,
            "head_sha": "old-head",
            "base_sha": "old-main",
            "current_main_sha": "old-main",
        },
        "new_snapshot": {
            "repository": "owner/repo",
            "pr_number": 57,
            "head_sha": "new-head",
            "base_sha": "new-main",
            "current_main_sha": "new-main",
        },
    }


def _guard(**updates):
    guard = {
        "rules": ["rule:baseline"],
        "enforcement_bindings": ["pre-commit:baseline"],
        "lifecycle_phases": ["pre-commit"],
        "trigger_patterns": ["src/protected/**"],
        "fail_fixtures": ["fixture:baseline"],
        "implementation_sha256": A,
        "self_test_sha256": B,
        "wording_sha256": C,
    }
    guard.update(updates)
    return guard


def _evidence(old_guard=None, new_guard=None, **updates):
    evidence = {
        **_snapshots(),
        "old_guard": old_guard or _guard(),
        "new_guard": new_guard or _guard(),
        "known_files": [
            "src/protected/a.py",
            "src/other.py",
        ],
        "behavioral_witnesses": [],
        "collection_complete": True,
        "collection_errors": [],
    }
    evidence.update(updates)
    return evidence


def test_rule_add_and_remove_classify_directionally():
    tightened = ri.analyze_guard_semantic_delta(
        _evidence(new_guard=_guard(rules=["rule:baseline", "rule:new"]))
    ).to_dict()
    loosened = ri.analyze_guard_semantic_delta(
        _evidence(old_guard=_guard(rules=["rule:baseline", "rule:old"]),
                  new_guard=_guard())
    ).to_dict()

    assert tightened["classification"] == "TIGHTENS"
    assert "RULE_ADDED:rule:new" in tightened["reason_codes"]
    assert loosened["classification"] == "LOOSENS"
    assert "RULE_REMOVED:rule:old" in loosened["reason_codes"]


def test_enforcement_and_lifecycle_changes_classify_directionally():
    tightened = ri.analyze_guard_semantic_delta(
        _evidence(
            new_guard=_guard(
                enforcement_bindings=["pre-commit:baseline", "pre-tool:policy"],
                lifecycle_phases=["pre-tool", "pre-commit"],
            )
        )
    ).to_dict()
    loosened = ri.analyze_guard_semantic_delta(
        _evidence(
            old_guard=_guard(
                enforcement_bindings=["pre-commit:baseline", "pre-tool:policy"],
                lifecycle_phases=["pre-tool", "pre-commit"],
            ),
            new_guard=_guard(),
        )
    ).to_dict()

    assert tightened["classification"] == "TIGHTENS"
    assert "ENFORCEMENT_ADDED:pre-tool:policy" in tightened["reason_codes"]
    assert "LIFECYCLE_PHASE_ADDED:pre-tool" in tightened["reason_codes"]
    assert loosened["classification"] == "LOOSENS"
    assert "ENFORCEMENT_REMOVED:pre-tool:policy" in loosened["reason_codes"]
    assert "LIFECYCLE_PHASE_REMOVED:pre-tool" in loosened["reason_codes"]


def test_trigger_scope_widen_and_narrow_use_known_file_witnesses():
    widened = ri.analyze_guard_semantic_delta(
        _evidence(new_guard=_guard(trigger_patterns=["src/**"]))
    ).to_dict()
    narrowed = ri.analyze_guard_semantic_delta(
        _evidence(
            old_guard=_guard(trigger_patterns=["src/**"]),
            new_guard=_guard(trigger_patterns=["src/protected/**"]),
        )
    ).to_dict()

    assert widened["classification"] == "TIGHTENS"
    assert "TRIGGER_SCOPE_EXPANDED:src/other.py" in widened["reason_codes"]
    assert narrowed["classification"] == "LOOSENS"
    assert "TRIGGER_SCOPE_REDUCED:src/other.py" in narrowed["reason_codes"]


def test_fail_fixture_add_remove_classifies_directionally():
    added = ri.analyze_guard_semantic_delta(
        _evidence(
            new_guard=_guard(
                fail_fixtures=["fixture:baseline", "fixture:new-negative"]
            )
        )
    ).to_dict()
    removed = ri.analyze_guard_semantic_delta(
        _evidence(
            old_guard=_guard(
                fail_fixtures=["fixture:baseline", "fixture:old-negative"]
            ),
            new_guard=_guard(),
        )
    ).to_dict()

    assert added["classification"] == "TIGHTENS"
    assert "FAIL_FIXTURE_ADDED:fixture:new-negative" in added["reason_codes"]
    assert removed["classification"] == "LOOSENS"
    assert "FAIL_FIXTURE_REMOVED:fixture:old-negative" in removed["reason_codes"]


def test_implementation_only_is_unknown_without_independent_witness():
    report = ri.analyze_guard_semantic_delta(
        _evidence(new_guard=_guard(implementation_sha256=D))
    ).to_dict()

    assert report["classification"] == "UNKNOWN"
    assert "IMPLEMENTATION_CHANGED_BEHAVIOR_UNPROVEN" in report["reason_codes"]


def test_implementation_and_self_test_cochange_is_explicit_unknown():
    report = ri.analyze_guard_semantic_delta(
        _evidence(
            new_guard=_guard(
                implementation_sha256=D,
                self_test_sha256=D,
            )
        )
    ).to_dict()

    assert report["classification"] == "UNKNOWN"
    assert "IMPLEMENTATION_AND_SELF_TEST_CHANGED_TOGETHER" in report["reason_codes"]


def test_independent_behavioral_witness_can_prove_implementation_direction():
    report = ri.analyze_guard_semantic_delta(
        _evidence(
            new_guard=_guard(implementation_sha256=D),
            behavioral_witnesses=[
                {
                    "witness_id": "deny-new-write",
                    "old_decision": "ALLOW",
                    "new_decision": "DENY",
                }
            ],
        )
    ).to_dict()

    assert report["classification"] == "TIGHTENS"
    assert "BEHAVIOR_WITNESS_TIGHTENS:deny-new-write" in report["reason_codes"]
    assert "IMPLEMENTATION_CHANGED_BEHAVIOR_UNPROVEN" not in report["reason_codes"]


def test_simultaneous_tightening_and_loosening_is_mixed():
    report = ri.analyze_guard_semantic_delta(
        _evidence(
            old_guard=_guard(rules=["rule:baseline", "rule:removed"]),
            new_guard=_guard(rules=["rule:baseline", "rule:added"]),
        )
    ).to_dict()

    assert report["classification"] == "MIXED"
    assert "RULE_ADDED:rule:added" in report["tightening_witnesses"]
    assert "RULE_REMOVED:rule:removed" in report["loosening_witnesses"]


def test_wording_only_change_remains_unknown():
    report = ri.analyze_guard_semantic_delta(
        _evidence(new_guard=_guard(wording_sha256=D))
    ).to_dict()

    assert report["classification"] == "UNKNOWN"
    assert "WORDING_CHANGED_BEHAVIOR_UNPROVEN" in report["reason_codes"]


def test_unchanged_is_unchanged():
    report = ri.analyze_guard_semantic_delta(_evidence()).to_dict()
    assert report["classification"] == "UNCHANGED"
    assert report["reason_codes"] == []
    assert report["is_complete"] is True


def test_stale_revision_identity_fails_closed():
    evidence = _evidence()
    evidence["new_snapshot"]["declared_head_sha"] = "different"
    report = ri.analyze_guard_semantic_delta(evidence).to_dict()

    assert report["classification"] == "UNKNOWN"
    assert report["is_complete"] is False
    assert "NEW_REVISION_IDENTITY_INVALID_OR_STALE" in report["evidence_gaps"]


def test_replay_is_deterministic_and_hash_stable():
    first = ri.analyze_guard_semantic_delta(_evidence()).to_dict()
    second = ri.analyze_guard_semantic_delta(_evidence()).to_dict()
    assert first == second
    assert first["content_sha256"] == second["content_sha256"]
    assert ri.verify_guard_semantic_delta_report(first) is True


def test_tampered_classification_rejected_even_with_recomputed_hash():
    payload = ri.analyze_guard_semantic_delta(_evidence()).to_dict()
    forged = copy.deepcopy(payload)
    forged["classification"] = "TIGHTENS"
    _rehash(forged)
    assert ri.verify_guard_semantic_delta_report(forged) is False


def test_tampered_reason_rejected_even_with_recomputed_hash():
    payload = ri.analyze_guard_semantic_delta(
        _evidence(new_guard=_guard(rules=["rule:baseline", "rule:new"]))
    ).to_dict()
    forged = copy.deepcopy(payload)
    forged["reason_codes"] = ["RULE_ADDED:forged"]
    _rehash(forged)
    assert ri.verify_guard_semantic_delta_report(forged) is False


def test_substituted_old_identity_rejected_even_with_recomputed_hash():
    payload = ri.analyze_guard_semantic_delta(_evidence()).to_dict()
    forged = copy.deepcopy(payload)
    forged["old_identity"]["head_sha"] = "substituted"
    _rehash(forged)
    assert ri.verify_guard_semantic_delta_report(forged) is False
