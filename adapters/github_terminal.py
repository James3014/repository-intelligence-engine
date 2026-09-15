"""Read-only terminal-observation adapter for Repository Intelligence.

This module does not infer a repository's required-check topology. It waits until
the exact external GitHub Check Run / Commit Status set visible through the
canonical Repository Intelligence acquisition adapter is complete, terminal,
and unchanged for a bounded quiescence window while the PR head remains exact.

The result stays advisory evidence. It does not approve, accept, merge, release,
deploy, or execute pull-request source.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from adapters.github_action import (
    CLOUD_CLAIM_CEILING,
    DEFAULT_API_URL,
    GitHubReadAPI,
    GitHubReadClient,
    _hash_payload,
    _resolve_pr_number,
    _utc_now,
    _validate_repo,
    collect_pr_snapshot,
    run_cloud_bundle,
    verify_cloud_bundle,
)
from repository_intelligence.contracts import SUPPORTED_TERMINAL_FAILURES

TERMINAL_SCHEMA = "reviewer.repository_intelligence_terminal_cloud.v1"
TERMINAL_OBSERVATION_SCHEMA = "reviewer.repository_intelligence_terminal_observation.v1"
TERMINAL_SNAPSHOT_SEMANTICS = "OBSERVED_CHECK_SET_TERMINAL_AFTER_QUIESCENCE"
TERMINAL_SUCCESS_STATES = frozenset({"success", "neutral", "skipped", "stale"})
TERMINAL_CHECK_STATES = SUPPORTED_TERMINAL_FAILURES | TERMINAL_SUCCESS_STATES | frozenset({"startup_failure"})
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_QUIESCENCE_SECONDS = 20.0
MAX_TIMEOUT_SECONDS = 3600.0
MAX_POLL_SECONDS = 60.0
MAX_QUIESCENCE_SECONDS = 300.0


def _validate_head(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 40 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("expected-head-sha must be a full 40-hex SHA")
    return normalized


def _validate_positive_int(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _validate_duration(value: float, *, name: str, minimum: float, maximum: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    numeric = float(value)
    if numeric < minimum or numeric > maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g} seconds")
    return numeric


def _is_terminal(check: Mapping[str, Any]) -> bool:
    status = check.get("status")
    return isinstance(status, str) and status.strip().casefold() in TERMINAL_CHECK_STATES


def _belongs_to_actions_run(check: Mapping[str, Any], run_id: int) -> bool:
    details_url = check.get("details_url")
    marker = f"/actions/runs/{run_id}/"
    return isinstance(details_url, str) and marker in details_url


def _canonical_checks(checks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    canonical: list[dict[str, Any]] = []
    for check in checks:
        item: dict[str, Any] = {
            "name": check.get("name"),
            "status": check.get("status"),
            "head_sha": check.get("head_sha"),
        }
        for key in ("check_run_id", "external_id", "details_url", "app_slug"):
            value = check.get(key)
            if value is not None:
                item[key] = value
        canonical.append(item)
    return sorted(canonical, key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))


def _checks_fingerprint(checks: Sequence[Mapping[str, Any]]) -> str:
    return _hash_payload({"observed_checks": _canonical_checks(checks)})


def _external_checks(
    snapshot: Mapping[str, Any], current_actions_run_id: int
) -> tuple[list[dict[str, Any]], int]:
    value = snapshot.get("checks")
    if not isinstance(value, list):
        return [], 0
    external: list[dict[str, Any]] = []
    excluded = 0
    for item in value:
        if not isinstance(item, Mapping):
            continue
        if _belongs_to_actions_run(item, current_actions_run_id):
            excluded += 1
            continue
        external.append(dict(item))
    return external, excluded


def wait_for_terminal_snapshot(
    api: GitHubReadAPI,
    repository: str,
    pr_number: int,
    *,
    expected_head_sha: str,
    current_actions_run_id: int,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    quiescence_seconds: float = DEFAULT_QUIESCENCE_SECONDS,
    monotonic_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one stable terminal observed-check snapshot and timing witness."""
    repository = _validate_repo(repository)
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("pr_number must be a positive integer")
    expected_head_sha = _validate_head(expected_head_sha)
    current_actions_run_id = _validate_positive_int(current_actions_run_id, "current-actions-run-id")
    timeout_seconds = _validate_duration(
        timeout_seconds, name="timeout", minimum=1.0, maximum=MAX_TIMEOUT_SECONDS
    )
    poll_seconds = _validate_duration(
        poll_seconds, name="poll", minimum=0.1, maximum=MAX_POLL_SECONDS
    )
    quiescence_seconds = _validate_duration(
        quiescence_seconds,
        name="quiescence",
        minimum=0.1,
        maximum=MAX_QUIESCENCE_SECONDS,
    )
    if quiescence_seconds >= timeout_seconds:
        raise ValueError("quiescence must be shorter than timeout")

    started_wall = _utc_now()
    started = float(monotonic_fn())
    stable_fingerprint: str | None = None
    stable_since: float | None = None
    stable_observations = 0

    while True:
        snapshot = collect_pr_snapshot(api, repository, pr_number)
        observed_head = snapshot.get("head_sha")
        if not isinstance(observed_head, str) or observed_head.lower() != expected_head_sha:
            raise RuntimeError("pull request head changed during terminal observation")

        external, excluded_count = _external_checks(snapshot, current_actions_run_id)
        complete = snapshot.get("collection_complete") is True
        all_terminal = bool(external) and all(_is_terminal(check) for check in external)
        now = float(monotonic_fn())

        if complete and all_terminal:
            fingerprint = _checks_fingerprint(external)
            if fingerprint != stable_fingerprint:
                stable_fingerprint = fingerprint
                stable_since = now
                stable_observations = 1
            else:
                stable_observations += 1

            if (
                stable_since is not None
                and stable_observations >= 2
                and now - stable_since >= quiescence_seconds
            ):
                observed_checks = _canonical_checks(external)
                witness = {
                    "schema": TERMINAL_OBSERVATION_SCHEMA,
                    "semantics": TERMINAL_SNAPSHOT_SEMANTICS,
                    "expected_head_sha": expected_head_sha,
                    "current_actions_run_id": current_actions_run_id,
                    "excluded_current_run_check_count": excluded_count,
                    "observed_external_check_count": len(observed_checks),
                    "observed_checks": observed_checks,
                    "observed_check_fingerprint": fingerprint,
                    "stable_observations": stable_observations,
                    "quiescence_seconds": quiescence_seconds,
                    "poll_seconds": poll_seconds,
                    "started_at": started_wall,
                    "completed_at": snapshot.get("observed_at"),
                }
                return snapshot, witness
        else:
            stable_fingerprint = None
            stable_since = None
            stable_observations = 0

        elapsed = now - started
        if elapsed >= timeout_seconds:
            raise RuntimeError(
                "terminal observation timed out before a complete, non-empty, stable terminal external check set was observed"
            )
        sleep_fn(min(poll_seconds, max(0.0, timeout_seconds - elapsed)))


def run_terminal_cloud_bundle(
    snapshot: Mapping[str, Any], terminal_observation: Mapping[str, Any]
) -> dict[str, Any]:
    cloud_bundle = run_cloud_bundle(snapshot)
    if not verify_cloud_bundle(cloud_bundle):
        raise RuntimeError("inner cloud bundle failed canonical verification")
    bundle: dict[str, Any] = {
        "schema": TERMINAL_SCHEMA,
        "claim_ceiling": CLOUD_CLAIM_CEILING,
        "snapshot_semantics": TERMINAL_SNAPSHOT_SEMANTICS,
        "review_identity": cloud_bundle["review_identity"],
        "terminal_observation": dict(terminal_observation),
        "cloud_bundle": cloud_bundle,
        "content_sha256": "",
    }
    bundle["content_sha256"] = _hash_payload(bundle)
    return bundle


def verify_terminal_cloud_bundle(payload: Mapping[str, Any]) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != TERMINAL_SCHEMA:
        return False
    if payload.get("claim_ceiling") != CLOUD_CLAIM_CEILING:
        return False
    if payload.get("snapshot_semantics") != TERMINAL_SNAPSHOT_SEMANTICS:
        return False
    supplied_hash = payload.get("content_sha256")
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        return False
    if supplied_hash != _hash_payload(payload):
        return False

    cloud_bundle = payload.get("cloud_bundle")
    if not isinstance(cloud_bundle, Mapping) or not verify_cloud_bundle(cloud_bundle):
        return False
    identity = payload.get("review_identity")
    if identity != cloud_bundle.get("review_identity"):
        return False
    if not isinstance(identity, list) or len(identity) != 5:
        return False

    witness = payload.get("terminal_observation")
    if not isinstance(witness, Mapping):
        return False
    if witness.get("schema") != TERMINAL_OBSERVATION_SCHEMA:
        return False
    if witness.get("semantics") != TERMINAL_SNAPSHOT_SEMANTICS:
        return False
    if witness.get("expected_head_sha") != identity[2]:
        return False
    run_id = witness.get("current_actions_run_id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        return False
    excluded_count = witness.get("excluded_current_run_check_count")
    if not isinstance(excluded_count, int) or isinstance(excluded_count, bool) or excluded_count < 0:
        return False
    checks = witness.get("observed_checks")
    count = witness.get("observed_external_check_count")
    if not isinstance(checks, list) or not checks:
        return False
    if not isinstance(count, int) or isinstance(count, bool) or count != len(checks):
        return False
    normalized_checks: list[Mapping[str, Any]] = []
    for check in checks:
        if not isinstance(check, Mapping):
            return False
        if check.get("head_sha") != identity[2] or not _is_terminal(check):
            return False
        if _belongs_to_actions_run(check, run_id):
            return False
        normalized_checks.append(check)
    fingerprint = witness.get("observed_check_fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        return False
    if fingerprint != _checks_fingerprint(normalized_checks):
        return False
    stable = witness.get("stable_observations")
    if not isinstance(stable, int) or isinstance(stable, bool) or stable < 2:
        return False
    for field in ("quiescence_seconds", "poll_seconds"):
        value = witness.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            return False
    if not isinstance(witness.get("started_at"), str) or not isinstance(witness.get("completed_at"), str):
        return False
    return True


def _write_step_summary(bundle: Mapping[str, Any], path: str | None) -> None:
    if not path:
        return
    cloud = bundle["cloud_bundle"]
    reports = cloud["reports"]
    readiness = reports["readiness"]["result"]
    cfi = reports["cfi"]["result"]
    eia = reports["eia"]["result"]
    witness = bundle["terminal_observation"]
    text = (
        "## Repository Intelligence terminal observation\n\n"
        f"- Review identity: `{json.dumps(bundle['review_identity'], separators=(',', ':'))}`\n"
        f"- Snapshot semantics: `{TERMINAL_SNAPSHOT_SEMANTICS}`\n"
        f"- Observed external checks: `{witness.get('observed_external_check_count')}`\n"
        f"- Readiness: `{readiness.get('disposition')}`\n"
        f"- CI failure intelligence: `{cfi.get('status')}`\n"
        f"- External automation advisory: `{eia.get('decision')}`\n"
        f"- Claim ceiling: `{bundle['claim_ceiling']}`\n"
        f"- Terminal bundle SHA-256: `{bundle['content_sha256']}`\n\n"
        "This proves only that the observed external check/status set was complete, terminal, and stable for the bounded quiescence window. It does not prove required-check completeness, all-green CI, Candidate acceptance, or merge readiness.\n"
    )
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def _write_github_outputs(bundle: Mapping[str, Any], path: str | None, report_path: str) -> None:
    if not path:
        return
    cloud = bundle["cloud_bundle"]
    reports = cloud["reports"]
    values = {
        "report-path": report_path,
        "content-sha256": bundle["content_sha256"],
        "readiness": reports["readiness"]["result"].get("disposition", ""),
        "cfi-status": reports["cfi"]["result"].get("status", ""),
        "eia-decision": reports["eia"]["result"].get("decision", ""),
        "claim-ceiling": bundle["claim_ceiling"],
        "snapshot-semantics": TERMINAL_SNAPSHOT_SEMANTICS,
        "observed-external-check-count": bundle["terminal_observation"].get("observed_external_check_count", ""),
    }
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repository-intelligence-terminal-action")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--current-actions-run-id", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--quiescence-seconds", type=float, default=DEFAULT_QUIESCENCE_SECONDS)
    parser.add_argument("--output", default=os.environ.get("RI_OUTPUT_FILE", "repository-intelligence-terminal.json"))
    args = parser.parse_args(argv)
    try:
        repository = _validate_repo(args.repository)
        pr_number = _resolve_pr_number(args.pr_number, os.environ.get("GITHUB_EVENT_PATH"))
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        api = GitHubReadClient(token, api_url=os.environ.get("GITHUB_API_URL", DEFAULT_API_URL))
        snapshot, witness = wait_for_terminal_snapshot(
            api,
            repository,
            pr_number,
            expected_head_sha=args.expected_head_sha,
            current_actions_run_id=args.current_actions_run_id,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
            quiescence_seconds=args.quiescence_seconds,
        )
        bundle = run_terminal_cloud_bundle(snapshot, witness)
        if not verify_terminal_cloud_bundle(bundle):
            raise RuntimeError("terminal cloud bundle failed self-verification")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_step_summary(bundle, os.environ.get("GITHUB_STEP_SUMMARY"))
        _write_github_outputs(bundle, os.environ.get("GITHUB_OUTPUT"), str(output))
        print(json.dumps(bundle, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": str(exc),
                    "claim_ceiling": CLOUD_CLAIM_CEILING,
                    "snapshot_semantics": TERMINAL_SNAPSHOT_SEMANTICS,
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
