"""Deterministic required-gate vs advisory-observer check classification."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

CHECK_ROLE_SCHEMA = "repository_intelligence.check_roles.v1"
CHECK_ROLE_CLAIM_CEILING = "CI_POLICY_ROLE_EVIDENCE_ONLY"
REQUIRED_GATE = "REQUIRED_GATE"
ADVISORY_CHECK = "ADVISORY_CHECK"
UNKNOWN_POLICY_ROLE = "UNKNOWN_POLICY_ROLE"
_ALLOWED_ROLES = {REQUIRED_GATE, ADVISORY_CHECK}
_SUCCESS = {"success", "successful", "passed", "pass", "neutral", "skipped"}
_INCOMPLETE = {"queued", "pending", "in_progress", "requested", "waiting", "timeout", "timed_out"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def classify_check_roles(
    *,
    review_identity: Mapping[str, Any],
    checks: Sequence[Mapping[str, Any]],
    policy_roles: Mapping[str, str],
    previous_check_names: Sequence[str] | None = None,
) -> dict[str, Any]:
    identity = {
        key: review_identity.get(key)
        for key in ("repository", "pr_number", "head_sha", "base_sha", "current_main_sha")
    }
    if (
        not identity["repository"]
        or not identity["head_sha"]
        or not identity["base_sha"]
        or not identity["current_main_sha"]
    ):
        raise ValueError("exact review identity is required")

    rows = [dict(row) for row in checks]
    names = [str(row.get("name") or "").strip() for row in rows]
    counts = Counter(names)
    classified: list[dict[str, Any]] = []
    required_blockers: list[str] = []
    advisory_degraded: list[str] = []
    unknown: list[str] = []

    for row, name in zip(rows, names):
        if not name:
            role, reason = UNKNOWN_POLICY_ROLE, "MISSING_CHECK_NAME"
        elif counts[name] > 1:
            role, reason = UNKNOWN_POLICY_ROLE, "DUPLICATE_CHECK_NAME"
        else:
            configured = policy_roles.get(name)
            if configured not in _ALLOWED_ROLES:
                role, reason = UNKNOWN_POLICY_ROLE, "POLICY_ROLE_MISSING"
            else:
                role, reason = configured, "POLICY_ROLE_BOUND"

        status = str(row.get("conclusion") or row.get("status") or "").strip().lower()
        incomplete = status in _INCOMPLETE or not status
        successful = status in _SUCCESS
        if role == REQUIRED_GATE and not successful:
            required_blockers.append(name or "<unnamed>")
        elif role == ADVISORY_CHECK and not successful:
            advisory_degraded.append(name)
        elif role == UNKNOWN_POLICY_ROLE:
            unknown.append(name or "<unnamed>")

        classified.append(
            {
                "name": name,
                "role": role,
                "status": status,
                "terminal": not incomplete,
                "successful": successful,
                "observer_state": (
                    "ADVISORY_INCOMPLETE"
                    if role == ADVISORY_CHECK and incomplete
                    else "ADVISORY_FAILED"
                    if role == ADVISORY_CHECK and not successful
                    else "OK"
                ),
                "reason": reason,
            }
        )

    current_check_names = sorted(name for name in names if name)
    if previous_check_names is None:
        previous_names: list[str] | None = None
        stability = "UNKNOWN"
    else:
        previous_names = sorted({str(name).strip() for name in previous_check_names if str(name).strip()})
        stability = "STABLE" if previous_names == sorted(set(current_check_names)) else "CHANGED"
    advisory_incomplete = any(
        row["role"] == ADVISORY_CHECK and not row["terminal"] for row in classified
    )
    if advisory_incomplete or stability != "STABLE":
        advisory_disposition = "ADVISORY_INCOMPLETE"
    elif advisory_degraded or unknown:
        advisory_disposition = "ADVISORY_DEGRADED"
    else:
        advisory_disposition = "ADVISORY_COMPLETE"

    body: dict[str, Any] = {
        "schema": CHECK_ROLE_SCHEMA,
        "review_identity": identity,
        "checks": sorted(classified, key=lambda row: (row["name"], row["role"], row["status"])),
        "required_blockers": sorted(set(required_blockers)),
        "advisory_degraded": sorted(set(advisory_degraded)),
        "unknown_policy_role": sorted(set(unknown)),
        "required_gate_state": "BLOCKED" if required_blockers else "CLEAR",
        "observer_health": "DEGRADED" if advisory_degraded or unknown or advisory_incomplete else "HEALTHY",
        "advisory_disposition": advisory_disposition,
        "check_set_observation": {
            "previous_names": previous_names,
            "current_names": sorted(set(current_check_names)),
            "stability": stability,
        },
        "claim_ceiling": CHECK_ROLE_CLAIM_CEILING,
    }
    body["content_sha256"] = _hash(body)
    return body


def verify_check_role_report(
    report: Mapping[str, Any], *, policy_roles: Mapping[str, str]
) -> bool:
    if (
        report.get("schema") != CHECK_ROLE_SCHEMA
        or report.get("claim_ceiling") != CHECK_ROLE_CLAIM_CEILING
    ):
        return False
    supplied = report.get("content_sha256")
    material = dict(report)
    material.pop("content_sha256", None)
    if _hash(material) != supplied:
        return False
    observation = report.get("check_set_observation") or {}
    previous_names = observation.get("previous_names")
    rebuilt = classify_check_roles(
        review_identity=report.get("review_identity") or {},
        checks=report.get("checks") or (),
        policy_roles=policy_roles,
        previous_check_names=previous_names,
    )
    return rebuilt == dict(report)


__all__ = [
    "CHECK_ROLE_SCHEMA",
    "CHECK_ROLE_CLAIM_CEILING",
    "REQUIRED_GATE",
    "ADVISORY_CHECK",
    "UNKNOWN_POLICY_ROLE",
    "classify_check_roles",
    "verify_check_role_report",
]
