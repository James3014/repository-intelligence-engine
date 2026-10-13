"""Cross-PR systemic CI failure signal (Issue #98).

A check that fails on many open pull requests at once is more likely a broken
shared dependency (workflow, runner, main-branch regression) than a defect in
any single PR. This module aggregates already-acquired per-PR check summaries
and reports such checks. It is deterministic, reads no network state, and makes
no root-cause, merge, or repair claim.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from ._hashing import content_hash as _content_hash
from .contracts import CI_EVIDENCE_CLAIM_CEILING, EvidenceCompleteness, is_terminal_failure_status

SYSTEMIC_SCHEMA = "reviewer.systemic_ci_failures.v1"
DEFAULT_MIN_PULL_REQUESTS = 3
DEFAULT_WINDOW_HOURS = 24
# Cancellation and pending approval are not evidence that the check is broken.
NON_SYSTEMIC_TERMINAL_STATUSES = frozenset({"cancelled", "action_required"})


@dataclass(frozen=True)
class SystemicFailure:
    check_name: str
    pr_numbers: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
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
    failing_checks_by_pr: dict[int, tuple[str, ...]]
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
                str(number): list(names) for number, names in sorted(self.failing_checks_by_pr.items())
            },
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


def _failing_names(
    checks: Any,
    *,
    window_start: datetime,
    window_end: datetime,
    label: str,
    gaps: list[str],
) -> tuple[str, ...]:
    """Names whose latest run on this PR is a systemic-eligible failure in window."""
    if not isinstance(checks, list):
        gaps.append(f"{label}: checks must be a list")
        return ()
    latest: dict[str, Mapping[str, Any]] = {}
    for check in checks:
        if not isinstance(check, Mapping):
            gaps.append(f"{label}: check entry must be a mapping")
            continue
        name = check.get("name")
        status = check.get("status")
        if not isinstance(name, str) or not name or not isinstance(status, str) or not status:
            gaps.append(f"{label}: check name/status missing")
            continue
        current = latest.get(name)
        if current is None or _run_order(check) > _run_order(current):
            latest[name] = check
    failing: list[str] = []
    for name, check in latest.items():
        status = str(check.get("status")).strip().lower()
        if not is_terminal_failure_status(status) or status in NON_SYSTEMIC_TERMINAL_STATUSES:
            continue
        completed = _parse_time(check.get("completed_at"))
        if completed is None or not (window_start <= completed <= window_end):
            continue
        failing.append(name)
    return tuple(sorted(failing))


def _systemic_from(
    failing_by_pr: Mapping[int, tuple[str, ...]], min_pull_requests: int
) -> tuple[SystemicFailure, ...]:
    by_name: dict[str, set[int]] = {}
    for number, names in failing_by_pr.items():
        for name in names:
            by_name.setdefault(name, set()).add(number)
    failures = [
        SystemicFailure(check_name=name, pr_numbers=tuple(sorted(numbers)))
        for name, numbers in by_name.items()
        if len(numbers) >= min_pull_requests
    ]
    failures.sort(key=lambda item: (-len(item.pr_numbers), item.check_name))
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

    failing_by_pr: dict[int, tuple[str, ...]] = {}
    valid_prs = 0
    for index, pr in enumerate(raw_prs):
        number = pr.get("pr_number") if isinstance(pr, Mapping) else None
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            gaps.append(f"pull_requests[{index}]: pr_number must be a positive integer")
            continue
        if number in failing_by_pr:
            gaps.append(f"pull_requests[{index}]: duplicate pr_number {number}")
            continue
        valid_prs += 1
        if observed is None:
            failing_by_pr[number] = ()
            continue
        failing_by_pr[number] = _failing_names(
            pr.get("checks"),
            window_start=observed - timedelta(hours=window_hours),
            window_end=observed + timedelta(minutes=5),
            label=f"pr:{number}",
            gaps=gaps,
        )

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
        failing_checks_by_pr={number: names for number, names in failing_by_pr.items() if names},
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
    failing: dict[int, tuple[str, ...]] = {}
    for key, names in raw.items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            return False
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            return False
        failing[number] = tuple(names)
    completeness = payload.get("evidence_completeness")
    expected = (
        []
        if completeness == EvidenceCompleteness.INCOMPLETE.value
        else [item.to_dict() for item in _systemic_from(failing, min_prs)]
    )
    return payload.get("systemic_failures") == expected
