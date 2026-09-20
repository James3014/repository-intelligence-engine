"""Repository Intelligence V1.1 Structured Repository Facts.

Deterministic, revision-bound, transport-neutral repository facts for recurring
code-risk/review patterns so consumers can reason over structured evidence
instead of re-inferring the same pattern from raw source.

This module does not parse source code and does not own a language-specific
detector index. It consumes normalized pattern observations (typically produced
by an adapter-owned source parser/detector such as ``adapters.python_fact_detector``)
and emits hash-bound advisory facts.

Facts are advisory repository evidence. A ``PROVEN`` fact never grants review
approval, merge, release, dispatch, or Candidate-acceptance authority.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .contracts import (
    REPOSITORY_FACTS_CLAIM_CEILING,
    EvidenceCompleteness,
    RepositoryFactEvidenceV1,
    RepositoryFactKind,
    RepositoryFactStatus,
    RepositoryFactV1,
    RevisionIdentity,
    StructuredFactsReportV1,
)
from .core import revision_identity

STRUCTURED_FACTS_SCHEMA = "reviewer.structured_facts.v1"

KNOWN_FACT_LIMITATIONS: dict[str, str] = {
    RepositoryFactKind.EMPTY_EXCEPTION_HANDLER.value: (
        "AST-based; only detected when a try/except handler body holds exactly "
        "one statement of pass or literal ellipsis."
    ),
    RepositoryFactKind.BROAD_EXCEPTION_HANDLER.value: (
        "AST-based; detects bare except, except Exception, and except "
        "BaseException; aliased or dynamically-resolved exception types are not modeled."
    ),
    RepositoryFactKind.SUBPROCESS_CALL.value: (
        "AST call-site with module-level import/alias resolution for subprocess.* "
        "and os.* spawn call chains; indirect/dynamic dispatch is not followed."
    ),
    RepositoryFactKind.NETWORK_ENDPOINT_ADDED.value: (
        "No deterministic AST detector; deciding 'added' requires diff and "
        "ownership analysis that is not implemented here."
    ),
    RepositoryFactKind.VISIBLE_AUTH_CHECK.value: (
        "No deterministic AST detector; deciding visibility/reachability of an "
        "auth check requires semantic or control-flow analysis that is not implemented here."
    ),
    RepositoryFactKind.RELATED_TEST_CHANGED.value: (
        "Diff-path heuristic over changed_files; test files are matched by "
        "naming convention (test/ directory, test_* / *_test / *.test.* / *.spec.*)."
    ),
    RepositoryFactKind.SILENT_RETRY_PATTERN.value: (
        "AST-based; detects a try/except whose handler body only passes or "
        "returns (pass/break/continue/Ellipsis) nested inside a for/while loop."
    ),
    RepositoryFactKind.HARDCODED_LOCALHOST.value: (
        "Literal scanner; only flat string constants equal to a localhost hostname/"
        "IP or URL literals with a localhost hostname are detected."
    ),
}


def _content_hash(payload: Mapping[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_path(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, "path must be a non-empty string"
    if "\x00" in value:
        return None, "path contains NUL"
    if "\\" in value:
        return None, f"path must use POSIX separators: {value!r}"
    if value.startswith("/"):
        return None, f"absolute path rejected: {value!r}"
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, f"path is not normalized or contains traversal: {value!r}"
    return value, None


def _normalize_path_sequence(
    raw: Any,
    *,
    label: str,
    problems: Sequence[str] | None = None,
    collection_problems: list[str] | None = None,
) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        if collection_problems is not None:
            collection_problems.append(f"{label} must be a list")
        return ()
    values: set[str] = set()
    for item in raw:
        path, error = _normalize_path(item)
        if error:
            if collection_problems is not None:
                collection_problems.append(f"{label}: {error}")
            elif problems is not None:
                problems.append(f"{label}: {error}")
            continue
        values.add(path)
    return tuple(sorted(values))


def _normalize_errors(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple)):
        return ()
    normalized: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item.strip() not in normalized:
            normalized.append(item.strip())
    return tuple(normalized)


def _obs_key(raw: Mapping[str, Any]) -> str:
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), default=repr)


def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    for component in parts:
        if component.lower() in {"test", "tests", "__tests__"}:
            return True
    filename = parts[-1]
    lower = filename.lower()
    stem = lower.rsplit(".", 1)[0] if "." in lower else lower
    if lower.startswith("test_") or lower.endswith("_test"):
        return True
    if stem.startswith("test") and stem.endswith("test"):
        return True
    if ".test." in lower or ".spec." in lower:
        return True
    return False


def _validate_observation(
    raw: Mapping[str, Any],
    *,
    covered_set: set[str],
    problems: list[str],
) -> tuple[RepositoryFactEvidenceV1 | None, RepositoryFactKind | None, bool]:
    """Validate one normalized observation.

    Returns ``(evidence, kind, invalid)`` with ``invalid=True`` for failing
    evidence. ``kind`` is ``None`` when the fault is not attributable to a
    specific fact kind; those faults fail the whole collection closed.
    """
    raw_kind = raw.get("fact_kind")
    if not isinstance(raw_kind, str):
        problems.append("observation missing a string fact_kind")
        return None, None, True
    try:
        kind = RepositoryFactKind(raw_kind)
    except (TypeError, ValueError):
        problems.append(f"observation has unknown fact_kind: {raw_kind!r}")
        return None, None, True

    path, path_error = _normalize_path(raw.get("file_path"))
    if path_error:
        problems.append(f"observation[{kind.value}]: {path_error}")
        return None, kind, True
    if path not in covered_set:
        problems.append(f"observation[{kind.value}] path not in covered_files: {path}")
        return None, kind, True

    line = raw.get("line")
    column = raw.get("column")
    evidence_ref = raw.get("evidence_ref")
    if isinstance(line, bool) or not isinstance(line, int) or line <= 0:
        problems.append(f"observation[{kind.value}] line must be a position int > 0")
        return None, kind, True
    if isinstance(column, bool) or not isinstance(column, int) or column < 0:
        problems.append(f"observation[{kind.value}] column must be a position int >= 0")
        return None, kind, True
    if not isinstance(evidence_ref, str) or not evidence_ref.strip():
        problems.append(f"observation[{kind.value}] evidence_ref must be a non-empty string")
        return None, kind, True

    return (
        RepositoryFactEvidenceV1(
            file_path=path,
            line=line,
            column=column,
            evidence_ref=evidence_ref.strip(),
        ),
        kind,
        False,
    )


def _derive_limitations(kind: RepositoryFactKind, *, language: str, coverage_true: bool) -> tuple[str, ...]:
    notes: list[str] = [KNOWN_FACT_LIMITATIONS[kind.value]]
    if kind is RepositoryFactKind.RELATED_TEST_CHANGED and not coverage_true:
        notes.append("No changed_files evidence was provided; test-change coverage is unassessed.")
    elif not coverage_true:
        notes.append(
            f"No deterministic {language!r} detector is implemented for fact kind {kind.value}; "
            "the fact stays UNKNOWN (scope limitation)."
        )
    return tuple(notes)


def _classify_facts(
    *,
    identity: RevisionIdentity,
    language: str,
    covered_files: tuple[str, ...],
    changed_files: tuple[str, ...],
    requested_kinds: tuple[RepositoryFactKind, ...],
    coverage: Mapping[str, bool],
    observations_raw: Sequence[Mapping[str, Any]],
    collection_complete: bool,
) -> tuple[list[RepositoryFactV1], dict[str, tuple[str, ...]], set[RepositoryFactKind], list[str]]:
    """Deterministic fact classification shared by analyze and verification."""
    covered_set = set(covered_files)
    kind_evidence: dict[RepositoryFactKind, list[RepositoryFactEvidenceV1]] = {}
    invalid_kinds: set[RepositoryFactKind] = set()
    problems: list[str] = []

    for raw in observations_raw:
        evidence, kind, invalid = _validate_observation(
            raw, covered_set=covered_set, problems=problems
        )
        if invalid:
            if kind is not None:
                invalid_kinds.add(kind)
            continue
        if kind is not None and evidence is not None:
            kind_evidence.setdefault(kind, []).append(evidence)

    for observations in kind_evidence.values():
        observations.sort(
            key=lambda item: (item.file_path, item.line, item.column, item.evidence_ref)
        )

    if not identity.is_valid:
        unresolved_reasons = ("INVALID_REVISION_IDENTITY",)
    elif identity.stale_evidence:
        unresolved_reasons = ("STALE_EVIDENCE",)
    elif not collection_complete:
        unresolved_reasons = ("EVIDENCE_INCOMPLETE",)
    elif not language:
        unresolved_reasons = ("LANGUAGE_UNSPECIFIED",)
    else:
        unresolved_reasons = None

    facts: list[RepositoryFactV1] = []
    limitations: dict[str, tuple[str, ...]] = {}

    for kind in requested_kinds:
        if kind is RepositoryFactKind.RELATED_TEST_CHANGED:
            coverage_true = bool(changed_files)
        else:
            coverage_true = coverage.get(kind.value) is True
        limitations[kind.value] = _derive_limitations(
            kind, language=language, coverage_true=coverage_true
        )

        if unresolved_reasons is not None:
            facts.append(
                RepositoryFactV1(
                    fact_kind=kind,
                    status=RepositoryFactStatus.UNRESOLVED,
                    head_sha=identity.head_sha,
                    language=language,
                    evidence=(),
                    reason_codes=unresolved_reasons,
                    limitations=limitations[kind.value],
                )
            )
            continue
        if kind in invalid_kinds:
            facts.append(
                RepositoryFactV1(
                    fact_kind=kind,
                    status=RepositoryFactStatus.UNRESOLVED,
                    head_sha=identity.head_sha,
                    language=language,
                    evidence=(),
                    reason_codes=("INVALID_OBSERVATION",),
                    limitations=limitations[kind.value],
                )
            )
            continue
        if kind is RepositoryFactKind.RELATED_TEST_CHANGED:
            if not changed_files:
                facts.append(
                    RepositoryFactV1(
                        fact_kind=kind,
                        status=RepositoryFactStatus.UNKNOWN,
                        head_sha=identity.head_sha,
                        language=language,
                        evidence=(),
                        reason_codes=("NO_CHANGED_FILES",),
                        limitations=limitations[kind.value],
                    )
                )
                continue
            test_paths = tuple(path for path in changed_files if _is_test_path(path))
            if test_paths:
                facts.append(
                    RepositoryFactV1(
                        fact_kind=kind,
                        status=RepositoryFactStatus.PROVEN,
                        head_sha=identity.head_sha,
                        language=language,
                        evidence=tuple(
                            RepositoryFactEvidenceV1(
                                file_path=path,
                                line=0,
                                column=0,
                                evidence_ref="changed_test_file",
                            )
                            for path in test_paths
                        ),
                        reason_codes=("TEST_CHANGE_DETECTED", "REVISION_BOUND"),
                        limitations=limitations[kind.value],
                    )
                )
            else:
                facts.append(
                    RepositoryFactV1(
                        fact_kind=kind,
                        status=RepositoryFactStatus.NOT_OBSERVED,
                        head_sha=identity.head_sha,
                        language=language,
                        evidence=(),
                        reason_codes=("NO_OBSERVATIONS", "COVERAGE_COMPLETE"),
                        limitations=limitations[kind.value],
                    )
                )
            continue

        if not coverage_true:
            facts.append(
                RepositoryFactV1(
                    fact_kind=kind,
                    status=RepositoryFactStatus.UNKNOWN,
                    head_sha=identity.head_sha,
                    language=language,
                    evidence=(),
                    reason_codes=("DETECTOR_NOT_IMPLEMENTED",),
                    limitations=limitations[kind.value],
                )
            )
            continue
        observations = kind_evidence.get(kind, ())
        if observations:
            facts.append(
                RepositoryFactV1(
                    fact_kind=kind,
                    status=RepositoryFactStatus.PROVEN,
                    head_sha=identity.head_sha,
                    language=language,
                    evidence=tuple(observations),
                    reason_codes=("DETECTOR_OBSERVATION", "REVISION_BOUND"),
                    limitations=limitations[kind.value],
                )
            )
        else:
            facts.append(
                RepositoryFactV1(
                    fact_kind=kind,
                    status=RepositoryFactStatus.NOT_OBSERVED,
                    head_sha=identity.head_sha,
                    language=language,
                    evidence=(),
                    reason_codes=("NO_OBSERVATIONS", "COVERAGE_COMPLETE"),
                    limitations=limitations[kind.value],
                )
            )

    return facts, limitations, invalid_kinds, problems


def _derive_completeness(
    *,
    identity: RevisionIdentity,
    language: str,
    covered_files: tuple[str, ...],
    coverage: Mapping[str, bool],
    collection_complete: bool,
    collection_errors: tuple[str, ...],
    invalid_kinds: set[RepositoryFactKind],
    requested_kinds: tuple[RepositoryFactKind, ...],
    facts: Sequence[RepositoryFactV1],
) -> tuple[EvidenceCompleteness, bool]:
    incomplete = (
        not identity.is_valid
        or identity.stale_evidence
        or not language
        or not covered_files
        or not coverage
        or not collection_complete
        or bool(collection_errors)
        or bool(invalid_kinds)
        or not requested_kinds
        or any(fact.status is RepositoryFactStatus.UNRESOLVED for fact in facts)
    )
    if incomplete:
        return EvidenceCompleteness.INCOMPLETE, False
    return EvidenceCompleteness.COMPLETE, True


def analyze_structured_facts(data: Mapping[str, Any]) -> StructuredFactsReportV1:
    """Emit hash-bound, revision-bound structured repository facts.

    Required input shape::

        {
          "snapshot": {repository/pr_number/base_sha/head_sha/current_main_sha,
                       changed_files, declared_*_sha...},
          "language": "python",
          "requested_facts": ["EMPTY_EXCEPTION_HANDLER", ...],  # optional
          "covered_files": ["src/a.py", ...],
          "observations": [
            {"fact_kind": "EMPTY_EXCEPTION_HANDLER", "file_path": "src/a.py",
             "line": 4, "column": 8, "evidence_ref": "empty_except_handler"}
          ],
          "detector_coverage": {"EMPTY_EXCEPTION_HANDLER": true, ...},
          "detector_version": "python-ast-v1",
          "collection_complete": true,
          "collection_errors": []
        }

    ``changed_files`` are authoritative inside ``snapshot.changed_files``; an
    optional top-level ``changed_files`` copy must match exactly. Observations
    are normalized adapter evidence; the engine classifies facts and never
    parses source itself. Caller-input validation failures fail the collection
    closed (``EVIDENCE_INCOMPLETE``).
    """
    if not isinstance(data, Mapping):
        raise TypeError("structured facts input must be a mapping")
    snapshot_missing = not isinstance(data.get("snapshot"), Mapping)

    collection_problems: list[str] = []
    if snapshot_missing:
        collection_problems.append("snapshot must be a mapping")
    snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), Mapping) else {}

    identity = revision_identity(snapshot)
    stale_identity = identity.stale_evidence

    language = data.get("language")
    if not isinstance(language, str) or not language.strip():
        collection_problems.append("language missing or invalid")
        language = ""
    else:
        language = language.strip()

    detector_version = data.get("detector_version")
    if not isinstance(detector_version, str):
        detector_version = ""

    requested_kinds: list[RepositoryFactKind] = []
    requested_raw = data.get("requested_facts")
    if requested_raw is None:
        requested_kinds = list(RepositoryFactKind)
    elif isinstance(requested_raw, (list, tuple)):
        for item in requested_raw:
            try:
                kind = RepositoryFactKind(item)
            except (TypeError, ValueError):
                collection_problems.append(f"requested_facts contains unknown kind: {item!r}")
                continue
            if kind not in requested_kinds:
                requested_kinds.append(kind)
        if not requested_kinds:
            collection_problems.append("requested_facts contains no known fact kinds")
    else:
        collection_problems.append("requested_facts must be a list of known fact kinds")
    requested_kinds.sort(key=lambda kind: list(RepositoryFactKind).index(kind))

    covered_files = _normalize_path_sequence(
        data.get("covered_files"), label="covered_files", collection_problems=collection_problems
    )
    if not covered_files:
        collection_problems.append("no covered_files provided")

    coverage_raw = data.get("detector_coverage")
    if coverage_raw is None:
        collection_problems.append("detector_coverage missing")
        coverage: dict[str, bool] = {}
    elif isinstance(coverage_raw, Mapping):
        coverage = {}
        for key, value in coverage_raw.items():
            if not isinstance(key, str) or key not in {k.value for k in RepositoryFactKind}:
                collection_problems.append(f"detector_coverage has unknown kind: {key!r}")
                continue
            if not isinstance(value, bool):
                collection_problems.append(f"detector_coverage[{key}] must be a boolean")
                continue
            coverage[key] = value
    else:
        collection_problems.append("detector_coverage must be a mapping of kind to boolean")
        coverage = {}

    collection_complete = data.get("collection_complete")
    if collection_complete is None:
        collection_problems.append("collection_complete not declared")
        collection_complete = False
    elif isinstance(collection_complete, bool):
        collection_complete = collection_complete
    else:
        collection_problems.append("collection_complete must be a boolean")
        collection_complete = False

    caller_errors = list(_normalize_errors(data.get("collection_errors")))
    for message in caller_errors:
        collection_problems.append(message)

    observations_input: Sequence[Any]
    if data.get("observations") is None:
        observations_input = ()
    elif isinstance(data.get("observations"), (list, tuple)):
        observations_input = data.get("observations")
    else:
        collection_problems.append("observations must be a list")
        observations_input = ()

    covered_set = set(covered_files)
    observations_raw: list[Mapping[str, Any]] = []
    seen_obs: set[str] = set()
    for item in observations_input:
        if not isinstance(item, Mapping):
            collection_problems.append("observation entry must be an object")
            continue
        key = _obs_key(item)
        if key in seen_obs:
            continue
        seen_obs.add(key)
        scan_problems: list[str] = []
        _, kind, invalid = _validate_observation(
            item, covered_set=covered_set, problems=scan_problems
        )
        if invalid and kind is None:
            collection_problems.extend(scan_problems)
            continue
        observations_raw.append(dict(item))

    snapshot_changed_raw = snapshot.get("changed_files") if isinstance(snapshot, Mapping) else None
    snapshot_changed = _normalize_path_sequence(
        snapshot_changed_raw,
        label="snapshot.changed_files",
        collection_problems=collection_problems,
    )
    explicit_changed_raw = data.get("changed_files")
    if explicit_changed_raw is None:
        changed_files = snapshot_changed
    else:
        explicit_changed = _normalize_path_sequence(
            explicit_changed_raw,
            label="changed_files",
            collection_problems=collection_problems,
        )
        if explicit_changed != snapshot_changed:
            collection_problems.append("changed_files do not match snapshot.changed_files")
        changed_files = snapshot_changed

    collection_errors = tuple(dict.fromkeys(collection_problems))
    if collection_errors:
        collection_complete = False

    facts, limitations, invalid_kinds, obs_problems = _classify_facts(
        identity=identity,
        language=language,
        covered_files=covered_files,
        changed_files=changed_files,
        requested_kinds=tuple(requested_kinds),
        coverage=coverage,
        observations_raw=observations_raw,
        collection_complete=collection_complete,
    )

    gaps: list[str] = list(identity.evidence_gaps)
    if stale_identity:
        gaps.append("stale identity evidence")
    for message in obs_problems:
        gaps.append(message)

    completeness, is_complete = _derive_completeness(
        identity=identity,
        language=language,
        covered_files=covered_files,
        coverage=coverage,
        collection_complete=collection_complete,
        collection_errors=collection_errors,
        invalid_kinds=invalid_kinds,
        requested_kinds=tuple(requested_kinds),
        facts=facts,
    )

    deduped_gaps = tuple(dict.fromkeys(gaps))
    report = StructuredFactsReportV1(
        identity=identity,
        language=language,
        detector_version=detector_version,
        covered_files=covered_files,
        changed_files=changed_files,
        requested_facts=tuple(kind.value for kind in requested_kinds),
        detector_coverage=coverage,
        observations=tuple(observations_raw),
        collection_complete=collection_complete,
        collection_errors=collection_errors,
        facts=tuple(facts),
        limitations=limitations,
        evidence_gaps=deduped_gaps,
        evidence_completeness=completeness,
        is_complete=is_complete,
        content_sha256="",
        claim_ceiling=REPOSITORY_FACTS_CLAIM_CEILING,
    )
    return replace(report, content_sha256=_content_hash(report.to_dict()))


def _identity_from_payload(payload: Mapping[str, Any]) -> RevisionIdentity:
    identity = payload.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("report identity missing or invalid")
    return RevisionIdentity(
        repository=str(identity.get("repository", "")),
        pr_number=identity.get("pr_number") if isinstance(identity.get("pr_number"), int) else 0,
        head_sha=str(identity.get("head_sha", "")),
        base_sha=str(identity.get("base_sha", "")),
        current_main_sha=str(identity.get("current_main_sha", "")),
        declared_base_sha=identity.get("declared_base_sha"),
        declared_head_sha=identity.get("declared_head_sha"),
        declared_main_sha=identity.get("declared_main_sha"),
        stale_base=identity.get("stale_base") is True,
        stale_declared_base=identity.get("stale_declared_base") is True,
        stale_declared_head=identity.get("stale_declared_head") is True,
        stale_declared_main=identity.get("stale_declared_main") is True,
        stale_evidence=identity.get("stale_evidence") is True,
        evidence_gaps=tuple(gap for gap in identity.get("evidence_gaps", []) if isinstance(gap, str)),
        is_valid=identity.get("is_valid") is True,
    )


def verify_structured_facts_report(payload: Mapping[str, Any]) -> bool:
    """Verify the hash binding and all deterministic fact semantics derivable
    from the embedded neutral inputs (observations, coverage, revision, and
    collection contract).

    The verifier rejects payloads that re-hash a different fact status, reason
    code, location, or completeness, because facts are recomputed from the
    embedded evidence rather than trusted.
    """
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != STRUCTURED_FACTS_SCHEMA:
        return False
    if payload.get("claim_ceiling") != REPOSITORY_FACTS_CLAIM_CEILING:
        return False
    supplied = payload.get("content_sha256")
    if not (
        isinstance(supplied, str)
        and len(supplied) == 64
        and supplied == _content_hash(payload)
    ):
        return False

    identity_raw = payload.get("identity")
    if not isinstance(identity_raw, Mapping):
        return False
    expected_review_identity = [
        identity_raw.get("repository"),
        identity_raw.get("pr_number"),
        identity_raw.get("head_sha"),
        identity_raw.get("base_sha"),
        identity_raw.get("current_main_sha"),
    ]
    if identity_raw.get("review_identity") != expected_review_identity:
        return False
    try:
        identity = _identity_from_payload(payload)
    except (ValueError, TypeError):
        return False

    language = payload.get("language")
    if not isinstance(language, str):
        return False
    detector_version = payload.get("detector_version")
    if not isinstance(detector_version, str):
        return False

    covered_files = payload.get("covered_files")
    changed_files = payload.get("changed_files")
    requested_list = payload.get("requested_facts")
    coverage = payload.get("detector_coverage")
    observations = payload.get("observations")
    collection_complete = payload.get("collection_complete")
    collection_errors = payload.get("collection_errors")
    if not isinstance(covered_files, list) or any(not isinstance(p, str) for p in covered_files):
        return False
    if covered_files != sorted(set(covered_files)):
        return False
    if not isinstance(changed_files, list) or any(not isinstance(p, str) for p in changed_files):
        return False
    if changed_files != sorted(set(changed_files)):
        return False
    if not isinstance(requested_list, list) or any(not isinstance(f, str) for f in requested_list):
        return False
    if not isinstance(coverage, Mapping):
        return False
    for key, value in coverage.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            return False
    if not isinstance(observations, list) or any(not isinstance(o, Mapping) for o in observations):
        return False
    if not isinstance(collection_complete, bool):
        return False
    if not isinstance(collection_errors, list) or any(not isinstance(e, str) for e in collection_errors):
        return False

    requested_kinds: list[RepositoryFactKind] = []
    for item in requested_list:
        try:
            requested_kinds.append(RepositoryFactKind(item))
        except (TypeError, ValueError):
            return False
    if requested_kinds != sorted(requested_kinds, key=lambda k: list(RepositoryFactKind).index(k)):
        return False
    if payload.get("requested_facts") != [k.value for k in requested_kinds]:
        return False
    for key in coverage:
        try:
            RepositoryFactKind(key)
        except (TypeError, ValueError):
            return False

    effective_complete = collection_complete and not bool(collection_errors)
    facts, limitations, invalid_kinds, _ = _classify_facts(
        identity=identity,
        language=language,
        covered_files=tuple(covered_files),
        changed_files=tuple(changed_files),
        requested_kinds=tuple(requested_kinds),
        coverage={str(k): bool(v) for k, v in coverage.items()},
        observations_raw=list(observations),
        collection_complete=effective_complete,
    )

    expected_facts = [fact.to_dict() for fact in facts]
    if payload.get("facts") != expected_facts:
        return False
    expected_limitations = {str(k): list(v) for k, v in sorted(limitations.items())}
    if payload.get("limitations") != expected_limitations:
        return False

    derived_completeness, derived_is_complete = _derive_completeness(
        identity=identity,
        language=language,
        covered_files=tuple(covered_files),
        coverage={str(k): bool(v) for k, v in coverage.items()},
        collection_complete=effective_complete,
        collection_errors=tuple(collection_errors),
        invalid_kinds=invalid_kinds,
        requested_kinds=tuple(requested_kinds),
        facts=facts,
    )
    if payload.get("evidence_completeness") != derived_completeness.value:
        return False
    if payload.get("is_complete") is not derived_is_complete:
        return False

    if derived_is_complete:
        gaps = payload.get("evidence_gaps")
        if not isinstance(gaps, list) or gaps:
            return False
        if identity.stale_evidence or not identity.is_valid:
            return False

    for fact in payload.get("facts", []):
        if not isinstance(fact, Mapping):
            return False
        if fact.get("head_sha") != identity.head_sha:
            return False
    return True