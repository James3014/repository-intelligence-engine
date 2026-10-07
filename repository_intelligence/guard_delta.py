"""Deterministic guard semantic delta advisory evidence.

Issue #57: classify mechanically observable changes in normalized policy/gate
structure without becoming a policy authority or semantic reviewer.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .core import revision_identity


GUARD_SEMANTIC_DELTA_SCHEMA = "reviewer.guard_semantic_delta.v1"
GUARD_SEMANTIC_DELTA_CLAIM_CEILING = (
    "GUARD_SEMANTIC_DELTA_ADVISORY_EVIDENCE_ONLY"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GuardSemanticDeltaClassification(str, Enum):
    TIGHTENS = "TIGHTENS"
    LOOSENS = "LOOSENS"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"
    UNCHANGED = "UNCHANGED"


@dataclass(frozen=True)
class GuardSemanticDeltaReportV1:
    old_identity: Mapping[str, Any]
    new_identity: Mapping[str, Any]
    old_guard: Mapping[str, Any]
    new_guard: Mapping[str, Any]
    known_files: tuple[str, ...]
    behavioral_witnesses: tuple[Mapping[str, str], ...]
    collection_complete: bool
    collection_errors: tuple[str, ...]
    classification: GuardSemanticDeltaClassification
    reason_codes: tuple[str, ...]
    tightening_witnesses: tuple[str, ...]
    loosening_witnesses: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    is_complete: bool
    content_sha256: str = ""
    schema: str = GUARD_SEMANTIC_DELTA_SCHEMA
    claim_ceiling: str = GUARD_SEMANTIC_DELTA_CLAIM_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(self, "old_identity", MappingProxyType(dict(self.old_identity)))
        object.__setattr__(self, "new_identity", MappingProxyType(dict(self.new_identity)))
        object.__setattr__(self, "old_guard", MappingProxyType(dict(self.old_guard)))
        object.__setattr__(self, "new_guard", MappingProxyType(dict(self.new_guard)))
        object.__setattr__(self, "known_files", tuple(self.known_files))
        object.__setattr__(
            self,
            "behavioral_witnesses",
            tuple(MappingProxyType(dict(item)) for item in self.behavioral_witnesses),
        )
        object.__setattr__(self, "collection_errors", tuple(self.collection_errors))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "tightening_witnesses", tuple(self.tightening_witnesses))
        object.__setattr__(self, "loosening_witnesses", tuple(self.loosening_witnesses))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "old_identity": dict(self.old_identity),
            "new_identity": dict(self.new_identity),
            "old_guard": _plain_guard(self.old_guard),
            "new_guard": _plain_guard(self.new_guard),
            "known_files": list(self.known_files),
            "behavioral_witnesses": [dict(item) for item in self.behavioral_witnesses],
            "collection_complete": self.collection_complete,
            "collection_errors": list(self.collection_errors),
            "classification": self.classification.value,
            "reason_codes": list(self.reason_codes),
            "tightening_witnesses": list(self.tightening_witnesses),
            "loosening_witnesses": list(self.loosening_witnesses),
            "evidence_gaps": list(self.evidence_gaps),
            "is_complete": self.is_complete,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


def _plain_guard(guard: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rules": list(guard.get("rules", ())),
        "enforcement_bindings": list(guard.get("enforcement_bindings", ())),
        "lifecycle_phases": list(guard.get("lifecycle_phases", ())),
        "trigger_patterns": list(guard.get("trigger_patterns", ())),
        "fail_fixtures": list(guard.get("fail_fixtures", ())),
        "implementation_sha256": guard.get("implementation_sha256"),
        "self_test_sha256": guard.get("self_test_sha256"),
        "wording_sha256": guard.get("wording_sha256"),
    }


def _hash_payload(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    encoded = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_string_list(
    value: Any,
    field: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return (), (f"{field.upper()}_INVALID",)
    problems: list[str] = []
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            problems.append(f"{field.upper()}_ITEM_INVALID:{index}")
            continue
        normalized.append(item)
    return tuple(sorted(set(normalized))), tuple(sorted(set(problems)))


def _normalize_optional_sha(
    value: Any,
    field: str,
) -> tuple[str | None, tuple[str, ...]]:
    if value is None:
        return None, ()
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value.lower()):
        return None, (f"{field.upper()}_INVALID",)
    return value.lower(), ()


def _normalize_guard(
    value: Any,
    prefix: str,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    if not isinstance(value, Mapping):
        return {
            "rules": (),
            "enforcement_bindings": (),
            "lifecycle_phases": (),
            "trigger_patterns": (),
            "fail_fixtures": (),
            "implementation_sha256": None,
            "self_test_sha256": None,
            "wording_sha256": None,
        }, (f"{prefix}_GUARD_INVALID",)

    problems: list[str] = []
    normalized: dict[str, Any] = {}
    for field in (
        "rules",
        "enforcement_bindings",
        "lifecycle_phases",
        "trigger_patterns",
        "fail_fixtures",
    ):
        items, field_problems = _normalize_string_list(value.get(field, []), field)
        normalized[field] = items
        problems.extend(f"{prefix}_{problem}" for problem in field_problems)

    for field in (
        "implementation_sha256",
        "self_test_sha256",
        "wording_sha256",
    ):
        digest, field_problems = _normalize_optional_sha(value.get(field), field)
        normalized[field] = digest
        problems.extend(f"{prefix}_{problem}" for problem in field_problems)

    return normalized, tuple(sorted(set(problems)))


def _normalize_known_files(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return _normalize_string_list(value, "known_files")


def _normalize_behavioral_witnesses(
    value: Any,
) -> tuple[tuple[dict[str, str], ...], tuple[str, ...]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return (), ("BEHAVIORAL_WITNESSES_INVALID",)
    witnesses: list[dict[str, str]] = []
    problems: list[str] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            problems.append(f"BEHAVIORAL_WITNESS_INVALID:{index}")
            continue
        witness_id = raw.get("witness_id")
        old_decision = raw.get("old_decision")
        new_decision = raw.get("new_decision")
        if not isinstance(witness_id, str) or not witness_id:
            problems.append(f"BEHAVIORAL_WITNESS_ID_INVALID:{index}")
            continue
        if old_decision not in {"ALLOW", "DENY"}:
            problems.append(f"BEHAVIORAL_OLD_DECISION_INVALID:{index}")
            continue
        if new_decision not in {"ALLOW", "DENY"}:
            problems.append(f"BEHAVIORAL_NEW_DECISION_INVALID:{index}")
            continue
        witnesses.append(
            {
                "witness_id": witness_id,
                "old_decision": old_decision,
                "new_decision": new_decision,
            }
        )
    witnesses.sort(
        key=lambda item: (
            item["witness_id"],
            item["old_decision"],
            item["new_decision"],
        )
    )
    return tuple(witnesses), tuple(sorted(set(problems)))


def _identity(snapshot: Any) -> tuple[dict[str, Any], bool]:
    result = revision_identity(snapshot)
    return result.to_dict(), bool(result.is_valid and not result.stale_evidence)


def _set_delta(
    old_values: Sequence[str],
    new_values: Sequence[str],
    *,
    added_prefix: str,
    removed_prefix: str,
) -> tuple[list[str], list[str]]:
    old_set = set(old_values)
    new_set = set(new_values)
    tightening = [f"{added_prefix}:{item}" for item in sorted(new_set - old_set)]
    loosening = [f"{removed_prefix}:{item}" for item in sorted(old_set - new_set)]
    return tightening, loosening


def _matches(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def analyze_guard_semantic_delta(
    evidence: Mapping[str, Any],
) -> GuardSemanticDeltaReportV1:
    """Classify deterministic guard direction from normalized neutral evidence."""
    if not isinstance(evidence, Mapping):
        evidence = {}

    old_identity, old_identity_ok = _identity(evidence.get("old_snapshot", {}))
    new_identity, new_identity_ok = _identity(evidence.get("new_snapshot", {}))
    old_guard, old_problems = _normalize_guard(evidence.get("old_guard", {}), "OLD")
    new_guard, new_problems = _normalize_guard(evidence.get("new_guard", {}), "NEW")
    known_files, known_file_problems = _normalize_known_files(
        evidence.get("known_files", [])
    )
    witnesses, witness_problems = _normalize_behavioral_witnesses(
        evidence.get("behavioral_witnesses", [])
    )

    normalisation_problems = [
        *old_problems,
        *new_problems,
        *known_file_problems,
        *witness_problems,
    ]

    collection_complete = evidence.get("collection_complete") is True
    caller_errors: list[str] = []
    errors_raw = evidence.get("collection_errors", [])
    if not isinstance(errors_raw, Sequence) or isinstance(
        errors_raw, (str, bytes, bytearray)
    ):
        normalisation_problems.append("COLLECTION_ERRORS_INVALID")
    else:
        for index, item in enumerate(errors_raw):
            if not isinstance(item, str) or not item:
                normalisation_problems.append(f"COLLECTION_ERROR_INVALID:{index}")
            else:
                caller_errors.append(item)
    collection_errors = tuple(sorted(set(caller_errors + normalisation_problems)))

    evidence_gaps: list[str] = []
    if not old_identity_ok:
        evidence_gaps.append("OLD_REVISION_IDENTITY_INVALID_OR_STALE")
    if not new_identity_ok:
        evidence_gaps.append("NEW_REVISION_IDENTITY_INVALID_OR_STALE")
    if not collection_complete:
        evidence_gaps.append("COLLECTION_INCOMPLETE")
    evidence_gaps.extend(f"COLLECTION_ERROR:{item}" for item in collection_errors)

    tightening: list[str] = []
    loosening: list[str] = []
    unknown: list[str] = []

    for field, added, removed in (
        ("rules", "RULE_ADDED", "RULE_REMOVED"),
        ("enforcement_bindings", "ENFORCEMENT_ADDED", "ENFORCEMENT_REMOVED"),
        ("lifecycle_phases", "LIFECYCLE_PHASE_ADDED", "LIFECYCLE_PHASE_REMOVED"),
        ("fail_fixtures", "FAIL_FIXTURE_ADDED", "FAIL_FIXTURE_REMOVED"),
    ):
        t, l = _set_delta(
            old_guard[field],
            new_guard[field],
            added_prefix=added,
            removed_prefix=removed,
        )
        tightening.extend(t)
        loosening.extend(l)

    old_triggered = {path for path in known_files if _matches(path, old_guard["trigger_patterns"])}
    new_triggered = {path for path in known_files if _matches(path, new_guard["trigger_patterns"])}
    tightening.extend(
        f"TRIGGER_SCOPE_EXPANDED:{path}" for path in sorted(new_triggered - old_triggered)
    )
    loosening.extend(
        f"TRIGGER_SCOPE_REDUCED:{path}" for path in sorted(old_triggered - new_triggered)
    )

    for witness in witnesses:
        witness_id = witness["witness_id"]
        old_decision = witness["old_decision"]
        new_decision = witness["new_decision"]
        if old_decision == "ALLOW" and new_decision == "DENY":
            tightening.append(f"BEHAVIOR_WITNESS_TIGHTENS:{witness_id}")
        elif old_decision == "DENY" and new_decision == "ALLOW":
            loosening.append(f"BEHAVIOR_WITNESS_LOOSENS:{witness_id}")

    directional_behavior_witness = any(
        item.startswith("BEHAVIOR_WITNESS_")
        for item in (*tightening, *loosening)
    )

    implementation_changed = (
        old_guard["implementation_sha256"] != new_guard["implementation_sha256"]
    )
    self_test_changed = old_guard["self_test_sha256"] != new_guard["self_test_sha256"]
    wording_changed = old_guard["wording_sha256"] != new_guard["wording_sha256"]

    if implementation_changed and self_test_changed:
        if not directional_behavior_witness:
            unknown.append("IMPLEMENTATION_AND_SELF_TEST_CHANGED_TOGETHER")
    elif implementation_changed and not directional_behavior_witness:
        unknown.append("IMPLEMENTATION_CHANGED_BEHAVIOR_UNPROVEN")

    if self_test_changed and not implementation_changed and not directional_behavior_witness:
        unknown.append("SELF_TEST_CHANGED_BEHAVIOR_UNPROVEN")

    if wording_changed and not directional_behavior_witness:
        unknown.append("WORDING_CHANGED_BEHAVIOR_UNPROVEN")

    tightening = sorted(set(tightening))
    loosening = sorted(set(loosening))
    unknown = sorted(set(unknown))
    global_unknown = bool(evidence_gaps)

    if global_unknown or unknown:
        classification = GuardSemanticDeltaClassification.UNKNOWN
    elif tightening and loosening:
        classification = GuardSemanticDeltaClassification.MIXED
    elif tightening:
        classification = GuardSemanticDeltaClassification.TIGHTENS
    elif loosening:
        classification = GuardSemanticDeltaClassification.LOOSENS
    else:
        classification = GuardSemanticDeltaClassification.UNCHANGED

    reason_codes = tuple(sorted(set([*tightening, *loosening, *unknown])))
    is_complete = not global_unknown and not unknown

    report = GuardSemanticDeltaReportV1(
        old_identity=old_identity,
        new_identity=new_identity,
        old_guard=old_guard,
        new_guard=new_guard,
        known_files=known_files,
        behavioral_witnesses=witnesses,
        collection_complete=collection_complete,
        collection_errors=collection_errors,
        classification=classification,
        reason_codes=reason_codes,
        tightening_witnesses=tuple(tightening),
        loosening_witnesses=tuple(loosening),
        evidence_gaps=tuple(sorted(set(evidence_gaps))),
        is_complete=is_complete,
        content_sha256="",
    )
    return replace(report, content_sha256=_hash_payload(report.to_dict()))


def verify_guard_semantic_delta_report(payload: Mapping[str, Any]) -> bool:
    """Recompute semantic output from embedded neutral inputs and reject tampering."""
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != GUARD_SEMANTIC_DELTA_SCHEMA:
        return False
    if payload.get("claim_ceiling") != GUARD_SEMANTIC_DELTA_CLAIM_CEILING:
        return False
    supplied_hash = payload.get("content_sha256")
    if not isinstance(supplied_hash, str) or not _SHA256_RE.fullmatch(supplied_hash):
        return False
    if _hash_payload(payload) != supplied_hash:
        return False

    old_identity = payload.get("old_identity")
    new_identity = payload.get("new_identity")
    if not isinstance(old_identity, Mapping) or not isinstance(new_identity, Mapping):
        return False

    neutral = {
        "old_snapshot": {
            "repository": old_identity.get("repository", ""),
            "pr_number": old_identity.get("pr_number", 0),
            "head_sha": old_identity.get("head_sha", ""),
            "base_sha": old_identity.get("base_sha", ""),
            "current_main_sha": old_identity.get("current_main_sha", ""),
            "declared_base_sha": old_identity.get("declared_base_sha"),
            "declared_head_sha": old_identity.get("declared_head_sha"),
            "declared_main_sha": old_identity.get("declared_main_sha"),
        },
        "new_snapshot": {
            "repository": new_identity.get("repository", ""),
            "pr_number": new_identity.get("pr_number", 0),
            "head_sha": new_identity.get("head_sha", ""),
            "base_sha": new_identity.get("base_sha", ""),
            "current_main_sha": new_identity.get("current_main_sha", ""),
            "declared_base_sha": new_identity.get("declared_base_sha"),
            "declared_head_sha": new_identity.get("declared_head_sha"),
            "declared_main_sha": new_identity.get("declared_main_sha"),
        },
        "old_guard": payload.get("old_guard", {}),
        "new_guard": payload.get("new_guard", {}),
        "known_files": payload.get("known_files", []),
        "behavioral_witnesses": payload.get("behavioral_witnesses", []),
        "collection_complete": payload.get("collection_complete") is True,
        "collection_errors": payload.get("collection_errors", []),
    }
    try:
        expected = analyze_guard_semantic_delta(neutral).to_dict()
    except (TypeError, ValueError):
        return False
    return dict(payload) == expected
