"""Cross-PR systemic CI failure signal (Issue #98).

A check that fails on many open pull requests at once is more likely a broken
shared dependency (workflow, runner, main-branch regression) than a defect in
any single PR. This module aggregates already-acquired per-PR check summaries
and reports such checks. It is deterministic, reads no network state, and makes
no root-cause, merge, or repair claim.

A check is identified by ``(workflow_path, name)`` so equally named jobs in
different workflows are never merged. A failure only counts when it completed
after the check's cutoff: the newest success of the same check on any open PR
or on main, or the newest main change to the workflow file, whichever is later.
That keeps an already-fixed failure (e.g. fixed by a workflow change on main
that the failing PRs have not re-run against) from being reported.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ._hashing import content_hash as _content_hash
from .contracts import CI_EVIDENCE_CLAIM_CEILING, EvidenceCompleteness, is_terminal_failure_status

SYSTEMIC_SCHEMA = "reviewer.systemic_ci_failures.v1"
DEFAULT_MIN_PULL_REQUESTS = 3
DEFAULT_WINDOW_HOURS = 24
# Cancellation and pending approval are not evidence that the check is broken.
NON_SYSTEMIC_TERMINAL_STATUSES = frozenset({"cancelled", "action_required"})


CheckKey = tuple[str, str]  # (workflow_path or "", check name)


@dataclass(frozen=True)
class SystemicFailure:
    check_name: str
    pr_numbers: tuple[int, ...]
    workflow_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "workflow_path": self.workflow_path,
            "pr_numbers": list(self.pr_numbers),
            "failing_pr_count": len(self.pr_numbers),
        }


@dataclass(frozen=True)
class SystemicFailureReportV1:
    repository: str
    observed_at: str
    window_hours: int
    min_pull_requests: int
    pull_request_count: int
    failing_checks_by_pr: dict[int, tuple[CheckKey, ...]]
    cutoffs: dict[CheckKey, str]
    systemic_failures: tuple[SystemicFailure, ...]
    evidence_gaps: tuple[str, ...]
    evidence_completeness: EvidenceCompleteness
    content_sha256: str
    schema: str = SYSTEMIC_SCHEMA
    claim_ceiling: str = CI_EVIDENCE_CLAIM_CEILING

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "repository": self.repository,
            "observed_at": self.observed_at,
            "window_hours": self.window_hours,
            "min_pull_requests": self.min_pull_requests,
            "pull_request_count": self.pull_request_count,
            "failing_checks_by_pr": {
                str(number): [list(key) for key in keys]
                for number, keys in sorted(self.failing_checks_by_pr.items())
            },
            "cutoffs": [
                {"workflow_path": key[0], "check_name": key[1], "cutoff": value}
                for key, value in sorted(self.cutoffs.items())
            ],
            "systemic_failures": [item.to_dict() for item in self.systemic_failures],
            "evidence_gaps": list(self.evidence_gaps),
            "evidence_completeness": self.evidence_completeness.value,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
        }


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _positive_int(value: Any, default: int, label: str, gaps: list[str]) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        gaps.append(f"{label} must be a positive integer")
        return default
    return value


def _run_order(check: Mapping[str, Any]) -> tuple[int, str, str]:
    run_id = check.get("check_run_id")
    return (
        run_id if isinstance(run_id, int) and not isinstance(run_id, bool) else -1,
        str(check.get("completed_at") or ""),
        str(check.get("started_at") or ""),
    )


def _key(check: Mapping[str, Any]) -> CheckKey:
    path = check.get("workflow_path")
    return (path if isinstance(path, str) else "", str(check.get("name")))


def _valid_checks(checks: Any, *, label: str, gaps: list[str]) -> list[Mapping[str, Any]]:
    if not isinstance(checks, list):
        gaps.append(f"{label}: checks must be a list")
        return []
    valid: list[Mapping[str, Any]] = []
    for check in checks:
        if not isinstance(check, Mapping):
            gaps.append(f"{label}: check entry must be a mapping")
            continue
        name, status = check.get("name"), check.get("status")
        if not isinstance(name, str) or not name or not isinstance(status, str) or not status:
            gaps.append(f"{label}: check name/status missing")
            continue
        valid.append(check)
    return valid


def _latest_by_key(checks: list[Mapping[str, Any]]) -> dict[CheckKey, Mapping[str, Any]]:
    latest: dict[CheckKey, Mapping[str, Any]] = {}
    for check in checks:
        key = _key(check)
        current = latest.get(key)
        if current is None or _run_order(check) > _run_order(current):
            latest[key] = check
    return latest


def _is_success(check: Mapping[str, Any]) -> bool:
    return str(check.get("status")).strip().lower() == "success"


def _is_systemic_failure(check: Mapping[str, Any]) -> bool:
    status = str(check.get("status")).strip().lower()
    return is_terminal_failure_status(status) and status not in NON_SYSTEMIC_TERMINAL_STATUSES


def _systemic_from(
    failing_by_pr: Mapping[int, Sequence[CheckKey]], min_pull_requests: int
) -> tuple[SystemicFailure, ...]:
    by_key: dict[CheckKey, set[int]] = {}
    for number, keys in failing_by_pr.items():
        for key in keys:
            by_key.setdefault(tuple(key), set()).add(number)  # type: ignore[arg-type]
    failures = [
        SystemicFailure(check_name=key[1], workflow_path=key[0], pr_numbers=tuple(sorted(numbers)))
        for key, numbers in by_key.items()
        if len(numbers) >= min_pull_requests
    ]
    failures.sort(key=lambda item: (-len(item.pr_numbers), item.workflow_path, item.check_name))
    return tuple(failures)


def analyze_systemic_failures(data: Mapping[str, Any]) -> SystemicFailureReportV1:
    """Report check names failing on at least ``min_pull_requests`` open PRs.

    Input shape::

        {
          "repository": "owner/name",
          "observed_at": "2026-10-13T06:00:00Z",
          "window_hours": 24,            # optional
          "min_pull_requests": 3,        # optional
          "pull_requests": [
            {"pr_number": 1, "checks": [
              {"name": "pytest", "status": "failure", "check_run_id": 10,
               "completed_at": "2026-10-13T05:00:00Z"}]}
          ]
        }

    Per PR only the latest run of each check name counts (a passing re-run
    clears an older failure). ``cancelled`` and ``action_required`` never count.
    """
    if not isinstance(data, Mapping):
        raise TypeError("systemic input must be a mapping")
    gaps: list[str] = []
    repository = data.get("repository") if isinstance(data.get("repository"), str) else ""
    observed_raw = data.get("observed_at")
    observed = _parse_time(observed_raw)
    if observed is None:
        gaps.append("observed_at must be an ISO-8601 timestamp with timezone")
    window_hours = _positive_int(data.get("window_hours"), DEFAULT_WINDOW_HOURS, "window_hours", gaps)
    min_prs = _positive_int(
        data.get("min_pull_requests"), DEFAULT_MIN_PULL_REQUESTS, "min_pull_requests", gaps
    )
    raw_prs = data.get("pull_requests")
    if not isinstance(raw_prs, list):
        gaps.append("pull_requests must be a list")
        raw_prs = []

    per_pr: dict[int, dict[CheckKey, Mapping[str, Any]]] = {}
    for index, pr in enumerate(raw_prs):
        number = pr.get("pr_number") if isinstance(pr, Mapping) else None
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            gaps.append(f"pull_requests[{index}]: pr_number must be a positive integer")
            continue
        if number in per_pr:
            gaps.append(f"pull_requests[{index}]: duplicate pr_number {number}")
            continue
        per_pr[number] = _latest_by_key(_valid_checks(pr.get("checks"), label=f"pr:{number}", gaps=gaps))
    valid_prs = len(per_pr)
    main_checks = _valid_checks(data.get("main_checks", []), label="main_checks", gaps=gaps)

    raw_changed = data.get("workflow_changed_at", {})
    if not isinstance(raw_changed, Mapping):
        gaps.append("workflow_changed_at must be a mapping of workflow path to timestamp")
        raw_changed = {}
    workflow_changed: dict[str, datetime] = {}
    for path, value in raw_changed.items():
        parsed = _parse_time(value)
        if not isinstance(path, str) or parsed is None:
            gaps.append("workflow_changed_at entries must map a path to an ISO-8601 timestamp")
            continue
        workflow_changed[path] = parsed

    # Cutoff per check: newest success anywhere (open PRs or main) or newest
    # main change to the workflow file, whichever is later.
    cutoff_times: dict[CheckKey, datetime] = {}

    def _raise_cutoff(key: CheckKey, when: datetime | None) -> None:
        if when is not None and (key not in cutoff_times or when > cutoff_times[key]):
            cutoff_times[key] = when

    for latest in per_pr.values():
        for key, check in latest.items():
            if _is_success(check):
                _raise_cutoff(key, _parse_time(check.get("completed_at")))
    for check in main_checks:
        if _is_success(check):
            _raise_cutoff(_key(check), _parse_time(check.get("completed_at")))

    failing_by_pr: dict[int, tuple[CheckKey, ...]] = {}
    if observed is not None:
        window_start = observed - timedelta(hours=window_hours)
        window_end = observed + timedelta(minutes=5)
        for latest in per_pr.values():
            for key in latest:
                if key[0] in workflow_changed:
                    _raise_cutoff(key, workflow_changed[key[0]])
        for number, latest in per_pr.items():
            keys: list[CheckKey] = []
            for key, check in latest.items():
                completed = _parse_time(check.get("completed_at"))
                if not _is_systemic_failure(check) or completed is None:
                    continue
                if not (window_start <= completed <= window_end):
                    continue
                cutoff = cutoff_times.get(key)
                if cutoff is not None and completed <= cutoff:
                    continue
                keys.append(key)
            if keys:
                failing_by_pr[number] = tuple(sorted(keys))

    deduped_gaps = tuple(dict.fromkeys(gaps))
    if observed is None or valid_prs == 0:
        completeness = EvidenceCompleteness.INCOMPLETE
        systemic: tuple[SystemicFailure, ...] = ()
    else:
        completeness = EvidenceCompleteness.PARTIAL if deduped_gaps else EvidenceCompleteness.COMPLETE
        systemic = _systemic_from(failing_by_pr, min_prs)

    report = SystemicFailureReportV1(
        repository=repository,
        observed_at=observed_raw if isinstance(observed_raw, str) else "",
        window_hours=window_hours,
        min_pull_requests=min_prs,
        pull_request_count=valid_prs,
        failing_checks_by_pr=failing_by_pr,
        cutoffs={
            key: value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            for key, value in cutoff_times.items()
        },
        systemic_failures=systemic,
        evidence_gaps=deduped_gaps,
        evidence_completeness=completeness,
        content_sha256="",
    )
    return replace(report, content_sha256=_content_hash(report.to_dict()))


def verify_systemic_failure_report(payload: Mapping[str, Any]) -> bool:
    """Verify hash binding and re-derive systemic failures from embedded evidence."""
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != SYSTEMIC_SCHEMA or payload.get("claim_ceiling") != CI_EVIDENCE_CLAIM_CEILING:
        return False
    supplied = payload.get("content_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64 or supplied != _content_hash(payload):
        return False
    min_prs = payload.get("min_pull_requests")
    if isinstance(min_prs, bool) or not isinstance(min_prs, int) or min_prs <= 0:
        return False
    raw = payload.get("failing_checks_by_pr")
    if not isinstance(raw, Mapping):
        return False
    failing: dict[int, tuple[CheckKey, ...]] = {}
    for raw_number, keys in raw.items():
        try:
            number = int(raw_number)
        except (TypeError, ValueError):
            return False
        if not isinstance(keys, list):
            return False
        parsed: list[CheckKey] = []
        for key in keys:
            if not isinstance(key, list) or len(key) != 2 or not all(isinstance(part, str) for part in key):
                return False
            parsed.append((key[0], key[1]))
        failing[number] = tuple(parsed)
    completeness = payload.get("evidence_completeness")
    expected = (
        []
        if completeness == EvidenceCompleteness.INCOMPLETE.value
        else [item.to_dict() for item in _systemic_from(failing, min_prs)]
    )
    return payload.get("systemic_failures") == expected
