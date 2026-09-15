#!/usr/bin/env python3
"""Validate and inspect the bounded Repository Intelligence dogfooding corpus.

This module is intentionally stdlib-only.  It validates observational evidence
metadata; it does not acquire GitHub state, mutate the corpus, or make
acceptance/merge decisions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA = "repository_intelligence.dogfooding_corpus.v1"
CLAIM_CEILING = "OBSERVATIONAL_EVIDENCE_ONLY"
EVIDENCE_CLASSES = {
    "LIVE_FLEET_DOGFOOD",
    "CONTROLLED_REPRODUCTION",
    "SOURCE_FORENSICS",
}
CASE_KINDS = {"FAILURE_CASE", "OPERATING_WITNESS"}
CASE_STATUSES = {"OPEN", "FIXED", "OBSERVED", "POSITIVE"}
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
CASE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")
EXPECTED_FLEET = {
    "James3014/Nexus-new",
    "James3014/devspace",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine",
    "James3014/nexus-runtime",
    "James3014/nexus-opencli-reviewer",
}


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA40_RE.fullmatch(value))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_corpus(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["corpus must be a JSON object"]

    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    if data.get("claim_ceiling") != CLAIM_CEILING:
        errors.append(f"claim_ceiling must be {CLAIM_CEILING!r}")
    if set(data.get("evidence_classes", [])) != EVIDENCE_CLASSES:
        errors.append("evidence_classes must exactly match the admitted class set")

    families = data.get("failure_families")
    family_ids: set[str] = set()
    if not isinstance(families, list) or not families:
        errors.append("failure_families must be a non-empty list")
    else:
        for index, family in enumerate(families):
            prefix = f"failure_families[{index}]"
            if not isinstance(family, dict):
                errors.append(f"{prefix} must be an object")
                continue
            family_id = family.get("id")
            if not _is_nonempty_string(family_id):
                errors.append(f"{prefix}.id must be a non-empty string")
            elif family_id in family_ids:
                errors.append(f"duplicate failure family {family_id!r}")
            else:
                family_ids.add(family_id)
            if not _is_nonempty_string(family.get("description")):
                errors.append(f"{prefix}.description must be a non-empty string")

    cases = data.get("cases")
    case_ids: set[str] = set()
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty list")
    else:
        for index, case in enumerate(cases):
            prefix = f"cases[{index}]"
            if not isinstance(case, dict):
                errors.append(f"{prefix} must be an object")
                continue
            case_id = case.get("case_id")
            if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
                errors.append(f"{prefix}.case_id is invalid")
            elif case_id in case_ids:
                errors.append(f"duplicate case_id {case_id!r}")
            else:
                case_ids.add(case_id)

            kind = case.get("kind")
            if kind not in CASE_KINDS:
                errors.append(f"{prefix}.kind is invalid")
            evidence_class = case.get("evidence_class")
            if evidence_class not in EVIDENCE_CLASSES:
                errors.append(f"{prefix}.evidence_class is invalid")
            if case.get("status") not in CASE_STATUSES:
                errors.append(f"{prefix}.status is invalid")
            repository = case.get("repository")
            if not _is_nonempty_string(repository) or "/" not in repository:
                errors.append(f"{prefix}.repository must be owner/name")
            if not isinstance(case.get("pr_number"), int) or isinstance(case.get("pr_number"), bool) or case["pr_number"] <= 0:
                errors.append(f"{prefix}.pr_number must be a positive integer")
            for field in ("head_sha", "base_sha", "current_main_sha"):
                if field in case and case[field] is not None and not _is_sha(case[field]):
                    errors.append(f"{prefix}.{field} must be a 40-character lowercase SHA")
            if evidence_class == "LIVE_FLEET_DOGFOOD" and not _is_sha(case.get("head_sha")):
                errors.append(f"{prefix} live fleet evidence requires exact head_sha")
            if kind == "FAILURE_CASE":
                family = case.get("failure_family")
                if family not in family_ids:
                    errors.append(f"{prefix}.failure_family must reference a declared family")
            elif case.get("failure_family") is not None:
                errors.append(f"{prefix}.failure_family must be null for operating witnesses")
            refs = case.get("evidence_refs")
            if not isinstance(refs, list) or not refs or not all(_is_nonempty_string(ref) for ref in refs):
                errors.append(f"{prefix}.evidence_refs must be a non-empty string list")
            if not _is_nonempty_string(case.get("observed_at")):
                errors.append(f"{prefix}.observed_at must be a non-empty timestamp string")
            if not _is_nonempty_string(case.get("supported_claim")):
                errors.append(f"{prefix}.supported_claim must be non-empty")
            non_claims = case.get("non_claims")
            if not isinstance(non_claims, list) or not non_claims or not all(_is_nonempty_string(item) for item in non_claims):
                errors.append(f"{prefix}.non_claims must be a non-empty string list")

            report = case.get("report_observation")
            if report is not None:
                if not isinstance(report, dict):
                    errors.append(f"{prefix}.report_observation must be an object")
                else:
                    if report.get("claim_ceiling") != "ADVISORY_EVIDENCE_ONLY":
                        errors.append(f"{prefix}.report_observation.claim_ceiling must remain advisory")
                    if report.get("evidence_completeness") not in {"COMPLETE", "INCOMPLETE"}:
                        errors.append(f"{prefix}.report_observation.evidence_completeness is invalid")
                    digest = report.get("content_sha256")
                    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                        errors.append(f"{prefix}.report_observation.content_sha256 is invalid")

            if case.get("failure_family") == "STALE_BASE":
                base_sha = case.get("base_sha")
                current_main_sha = case.get("current_main_sha")
                if not (_is_sha(base_sha) and _is_sha(current_main_sha) and base_sha != current_main_sha):
                    errors.append(f"{prefix} STALE_BASE requires distinct exact base_sha/current_main_sha")

    fleet = data.get("fleet")
    seen_repos: set[str] = set()
    if not isinstance(fleet, list):
        errors.append("fleet must be a list")
    else:
        for index, row in enumerate(fleet):
            prefix = f"fleet[{index}]"
            if not isinstance(row, dict):
                errors.append(f"{prefix} must be an object")
                continue
            repository = row.get("repository")
            if repository in seen_repos:
                errors.append(f"duplicate fleet repository {repository!r}")
            if isinstance(repository, str):
                seen_repos.add(repository)
            if row.get("sidecar_integrated") is not True:
                errors.append(f"{prefix}.sidecar_integrated must be true for the completed fleet")
            if row.get("evidence_state") not in {"CANARY_ONLY", "POST_ROLLOUT_WITNESS", "FAILURE_WITNESS"}:
                errors.append(f"{prefix}.evidence_state is invalid")
            latest_case_id = row.get("latest_case_id")
            if latest_case_id is not None and latest_case_id not in case_ids:
                errors.append(f"{prefix}.latest_case_id must reference a declared case")
        if seen_repos != EXPECTED_FLEET:
            missing = sorted(EXPECTED_FLEET - seen_repos)
            extra = sorted(seen_repos - EXPECTED_FLEET)
            errors.append(f"fleet repository set mismatch; missing={missing}, extra={extra}")

    return errors


def extract_report_candidates(report: Any) -> list[dict[str, Any]]:
    """Return mutation-free candidate observations from one RIE cloud bundle."""
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    if report.get("claim_ceiling") != "ADVISORY_EVIDENCE_ONLY":
        raise ValueError("report claim ceiling is not ADVISORY_EVIDENCE_ONLY")
    identity = report.get("review_identity")
    if not isinstance(identity, list) or len(identity) != 5:
        raise ValueError("report review_identity must contain five fields")
    repository, pr_number, head_sha, base_sha, current_main_sha = identity
    if not _is_nonempty_string(repository) or not isinstance(pr_number, int) or isinstance(pr_number, bool):
        raise ValueError("report identity repository/pr_number is invalid")
    if not all(_is_sha(value) for value in (head_sha, base_sha, current_main_sha)):
        raise ValueError("report identity SHAs must be exact 40-character lowercase SHAs")

    reports = report.get("reports")
    if not isinstance(reports, dict):
        raise ValueError("report reports envelope is missing")
    readiness = reports.get("readiness", {}).get("result", {})
    cfi = reports.get("cfi", {}).get("result", {})
    candidates: list[dict[str, Any]] = []
    common = {
        "repository": repository,
        "pr_number": pr_number,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "current_main_sha": current_main_sha,
    }
    findings = readiness.get("findings", []) if isinstance(readiness, dict) else []
    if readiness.get("disposition") == "STALE" and "STALE_BASE" in findings:
        candidates.append({**common, "failure_family": "STALE_BASE", "evidence_class": "LIVE_FLEET_DOGFOOD"})
    readiness_complete = readiness.get("evidence_completeness") if isinstance(readiness, dict) else None
    cfi_complete = cfi.get("evidence_completeness") if isinstance(cfi, dict) else None
    if readiness_complete == "INCOMPLETE" or cfi_complete == "INCOMPLETE":
        candidates.append({**common, "failure_family": "EVIDENCE_INCOMPLETE", "evidence_class": "LIVE_FLEET_DOGFOOD"})
    if isinstance(cfi, dict) and cfi.get("status") == "UNEXPECTED_FAILURE_OBSERVED":
        candidates.append({**common, "failure_family": "UNEXPECTED_TERMINAL_CI_FAILURE", "evidence_class": "LIVE_FLEET_DOGFOOD"})
    return candidates


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus", type=Path, nargs="?", default=Path("docs/dogfooding/corpus.v1.json"))
    parser.add_argument("--extract-report", type=Path)
    args = parser.parse_args(argv)

    if args.extract_report is not None:
        try:
            candidates = extract_report_candidates(_load(args.extract_report))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"invalid report: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(candidates, indent=2, sort_keys=True))
        return 0

    try:
        data = _load(args.corpus)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"unable to load corpus: {exc}", file=sys.stderr)
        return 2
    errors = validate_corpus(data)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"OK: {args.corpus} ({len(data['cases'])} cases, {len(data['fleet'])} fleet repos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
