"""Deterministic source-to-knowledge applicability evidence.

Issue #56: classify whether repository-bound knowledge artifacts remain current,
need review because exact sources changed, are affected by declared coverage, or
cannot be adjudicated from the supplied evidence.

This module is advisory-only. It never inspects or rewrites knowledge content.
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


KNOWLEDGE_APPLICABILITY_SCHEMA = "reviewer.knowledge_applicability.v1"
KNOWLEDGE_APPLICABILITY_CLAIM_CEILING = (
    "REPOSITORY_KNOWLEDGE_APPLICABILITY_EVIDENCE_ONLY"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeApplicabilityStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE_EXACT_SOURCE = "STALE_EXACT_SOURCE"
    AFFECTED_BY_COVERAGE = "AFFECTED_BY_COVERAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class KnowledgeApplicabilityRelationV1:
    artifact_id: str
    artifact_path: str
    status: KnowledgeApplicabilityStatus
    reason_codes: tuple[str, ...] = ()
    affected_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "affected_paths", tuple(self.affected_paths))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_path": self.artifact_path,
            "status": self.status.value,
            "reason_codes": list(self.reason_codes),
            "affected_paths": list(self.affected_paths),
        }


@dataclass(frozen=True)
class KnowledgeApplicabilityReportV1:
    identity: Mapping[str, Any]
    knowledge_artifacts: tuple[Mapping[str, Any], ...]
    changes: tuple[Mapping[str, Any], ...]
    observed_source_sha256: Mapping[str, str]
    in_scope: tuple[str, ...]
    collection_complete: bool
    collection_errors: tuple[str, ...]
    relations: tuple[KnowledgeApplicabilityRelationV1, ...]
    uncovered_changes: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    is_complete: bool
    content_sha256: str = ""
    schema: str = KNOWLEDGE_APPLICABILITY_SCHEMA
    claim_ceiling: str = KNOWLEDGE_APPLICABILITY_CLAIM_CEILING

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "knowledge_artifacts",
            tuple(MappingProxyType(dict(item)) for item in self.knowledge_artifacts),
        )
        object.__setattr__(
            self,
            "changes",
            tuple(MappingProxyType(dict(item)) for item in self.changes),
        )
        object.__setattr__(
            self,
            "observed_source_sha256",
            MappingProxyType(dict(self.observed_source_sha256)),
        )
        object.__setattr__(self, "in_scope", tuple(self.in_scope))
        object.__setattr__(self, "collection_errors", tuple(self.collection_errors))
        object.__setattr__(self, "relations", tuple(self.relations))
        object.__setattr__(self, "uncovered_changes", tuple(self.uncovered_changes))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "identity": dict(self.identity),
            "knowledge_artifacts": [dict(item) for item in self.knowledge_artifacts],
            "changes": [dict(item) for item in self.changes],
            "observed_source_sha256": {
                key: value
                for key, value in sorted(self.observed_source_sha256.items())
            },
            "in_scope": list(self.in_scope),
            "collection_complete": self.collection_complete,
            "collection_errors": list(self.collection_errors),
            "relations": [relation.to_dict() for relation in self.relations],
            "uncovered_changes": list(self.uncovered_changes),
            "evidence_gaps": list(self.evidence_gaps),
            "is_complete": self.is_complete,
            "claim_ceiling": self.claim_ceiling,
            "content_sha256": self.content_sha256,
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


def _normalise_artifacts(
    value: Any,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...], bool]:
    problems: list[str] = []
    inventory_structurally_complete = True
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return (), ("KNOWLEDGE_ARTIFACTS_INVALID",), False
    artifacts: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            problems.append(f"KNOWLEDGE_ARTIFACT_INVALID:{index}")
            inventory_structurally_complete = False
            continue
        refs = raw.get("source_refs", [])
        covers = raw.get("covers", [])
        norm_refs: list[dict[str, str]] = []
        if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes, bytearray)):
            problems.append(f"SOURCE_REFS_INVALID:{index}")
            inventory_structurally_complete = False
            refs = []
        for ref_index, ref in enumerate(refs):
            if not isinstance(ref, Mapping):
                problems.append(f"SOURCE_REF_INVALID:{index}:{ref_index}")
                continue
            source_path = ref.get("source_path")
            expected = ref.get("expected_content_sha256")
            ref_valid = True
            if not isinstance(source_path, str) or not source_path:
                problems.append(f"SOURCE_PATH_INVALID:{index}:{ref_index}")
                ref_valid = False
            if (
                not isinstance(expected, str)
                or not _SHA256_RE.fullmatch(expected.lower())
            ):
                problems.append(f"SOURCE_SHA256_INVALID:{index}:{ref_index}")
                ref_valid = False
            if not ref_valid:
                continue
            norm_refs.append(
                {
                    "source_path": source_path,
                    "expected_content_sha256": expected.lower(),
                }
            )

        norm_covers: list[str] = []
        if not isinstance(covers, Sequence) or isinstance(
            covers, (str, bytes, bytearray)
        ):
            problems.append(f"COVERS_INVALID:{index}")
            inventory_structurally_complete = False
            covers = []
        for cover_index, item in enumerate(covers):
            if not isinstance(item, str) or not item:
                problems.append(f"COVER_INVALID:{index}:{cover_index}")
                continue
            norm_covers.append(item)

        artifact_id = raw.get("artifact_id")
        artifact_path = raw.get("path")
        if not isinstance(artifact_id, str) or not artifact_id:
            problems.append(f"ARTIFACT_ID_INVALID:{index}")
            artifact_id = ""
        if not isinstance(artifact_path, str) or not artifact_path:
            problems.append(f"ARTIFACT_PATH_INVALID:{index}")
            artifact_path = ""

        artifacts.append(
            {
                "artifact_id": artifact_id,
                "path": artifact_path,
                "source_refs": sorted(
                    norm_refs,
                    key=lambda item: (
                        item["source_path"],
                        item["expected_content_sha256"],
                    ),
                ),
                "covers": sorted(norm_covers),
            }
        )
    return (
        tuple(sorted(artifacts, key=lambda item: (item["artifact_id"], item["path"]))),
        tuple(sorted(set(problems))),
        inventory_structurally_complete,
    )


def _normalise_changes(
    value: Any,
) -> tuple[tuple[dict[str, str], ...], tuple[str, ...]]:
    problems: list[str] = []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return (), ("CHANGES_INVALID",)
    changes: list[dict[str, str]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            problems.append(f"CHANGE_INVALID:{index}")
            continue
        kind_raw = raw.get("kind")
        kind = kind_raw.upper() if isinstance(kind_raw, str) else ""
        path_raw = raw.get("path")
        path = path_raw if isinstance(path_raw, str) else ""
        item = {"kind": kind, "path": path}

        if not isinstance(path_raw, str):
            problems.append(f"CHANGE_PATH_INVALID:{index}")
        if not isinstance(kind_raw, str) or kind not in {
            "ADD",
            "MODIFY",
            "DELETE",
            "RENAME",
        }:
            problems.append(f"CHANGE_KIND_INVALID:{index}")
        if kind in {"ADD", "MODIFY", "RENAME"} and not path:
            problems.append(f"CHANGE_PATH_MISSING:{index}")

        old_path = raw.get("old_path")
        if old_path is not None:
            if isinstance(old_path, str):
                item["old_path"] = old_path
            else:
                problems.append(f"CHANGE_OLD_PATH_INVALID:{index}")
        if kind in {"DELETE", "RENAME"} and not item.get("old_path"):
            problems.append(f"CHANGE_OLD_PATH_MISSING:{index}")
        changes.append(item)
    return (
        tuple(
            sorted(
                changes,
                key=lambda item: (
                    item.get("path", ""),
                    item.get("old_path", ""),
                    item.get("kind", ""),
                ),
            )
        ),
        tuple(sorted(set(problems))),
    )


def _changed_paths(changes: Sequence[Mapping[str, str]]) -> tuple[str, ...]:
    paths: set[str] = set()
    for change in changes:
        path = change.get("path", "")
        old_path = change.get("old_path", "")
        kind = change.get("kind", "")
        if path:
            paths.add(path)
        if old_path and kind in {"DELETE", "RENAME"}:
            paths.add(old_path)
    return tuple(sorted(paths))


def _removed_or_renamed_paths(
    changes: Sequence[Mapping[str, str]],
) -> frozenset[str]:
    return frozenset(
        change.get("old_path", "")
        for change in changes
        if change.get("kind") in {"DELETE", "RENAME"} and change.get("old_path")
    )


def _matches_any(path: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def _identity_dict(snapshot: Any) -> tuple[dict[str, Any], bool]:
    identity = revision_identity(snapshot)
    payload = identity.to_dict()
    identity_ok = bool(identity.is_valid and not identity.stale_evidence)
    return payload, identity_ok


def analyze_knowledge_applicability(
    evidence: Mapping[str, Any],
) -> KnowledgeApplicabilityReportV1:
    """Compute deterministic source-to-knowledge applicability evidence."""
    if not isinstance(evidence, Mapping):
        evidence = {}

    identity, identity_ok = _identity_dict(evidence.get("snapshot", {}))
    artifacts, artifact_problems, artifact_inventory_structurally_complete = (
        _normalise_artifacts(evidence.get("knowledge_artifacts", []))
    )
    changes, change_problems = _normalise_changes(evidence.get("changes", []))

    normalisation_problems: list[str] = [
        *artifact_problems,
        *change_problems,
    ]
    observed_raw = evidence.get("observed_source_sha256", {})
    if isinstance(observed_raw, Mapping):
        observed = {}
        for index, (path, digest) in enumerate(observed_raw.items()):
            if not isinstance(path, str) or not path:
                normalisation_problems.append(
                    f"OBSERVED_SOURCE_PATH_INVALID:{index}"
                )
                continue
            if (
                not isinstance(digest, str)
                or not _SHA256_RE.fullmatch(digest.lower())
            ):
                normalisation_problems.append(
                    f"OBSERVED_SOURCE_SHA256_INVALID:{path}"
                )
                continue
            observed[path] = digest.lower()
    else:
        observed = {}
        normalisation_problems.append("OBSERVED_SOURCE_IDENTITIES_INVALID")

    scope_raw = evidence.get("in_scope", [])
    scope_items: list[str] = []
    if not isinstance(scope_raw, Sequence) or isinstance(
        scope_raw, (str, bytes, bytearray)
    ):
        normalisation_problems.append("IN_SCOPE_INVALID")
        scope_raw = []
    for index, item in enumerate(scope_raw):
        if not isinstance(item, str) or not item:
            normalisation_problems.append(f"IN_SCOPE_ITEM_INVALID:{index}")
            continue
        scope_items.append(item)
    in_scope = tuple(sorted(scope_items))

    collection_complete = evidence.get("collection_complete") is True
    errors_raw = evidence.get("collection_errors", [])
    caller_errors: list[str] = []
    collection_errors_input_valid = True
    if not isinstance(errors_raw, Sequence) or isinstance(
        errors_raw, (str, bytes, bytearray)
    ):
        normalisation_problems.append("COLLECTION_ERRORS_INVALID")
        collection_errors_input_valid = False
    else:
        for index, item in enumerate(errors_raw):
            if not isinstance(item, str) or not item:
                normalisation_problems.append(
                    f"COLLECTION_ERROR_INVALID:{index}"
                )
                continue
            caller_errors.append(item)
    collection_errors = tuple(
        sorted(set(caller_errors + normalisation_problems))
    )

    evidence_gaps: list[str] = []
    if not identity_ok:
        evidence_gaps.append("REVISION_IDENTITY_INVALID_OR_STALE")
    if not collection_complete:
        evidence_gaps.append("COLLECTION_INCOMPLETE")
    evidence_gaps.extend(f"COLLECTION_ERROR:{item}" for item in collection_errors)
    if not in_scope:
        evidence_gaps.append("IN_SCOPE_MISSING")

    changed_paths = _changed_paths(changes)
    removed_or_renamed = _removed_or_renamed_paths(changes)

    relations: list[KnowledgeApplicabilityRelationV1] = []
    claimed_paths: set[str] = set()

    for artifact in artifacts:
        artifact_id = artifact["artifact_id"]
        artifact_path = artifact["path"]
        refs = artifact["source_refs"]
        covers = artifact["covers"]
        reasons: list[str] = []
        affected_paths: set[str] = set()
        stale = False
        global_unknown = (
            not identity_ok or not collection_complete or bool(collection_errors)
        )
        unknown = global_unknown

        claim_eligible = bool(artifact_id and artifact_path)
        if not claim_eligible:
            unknown = True
            reasons.append("ARTIFACT_IDENTITY_INVALID")

        exact_paths = {ref["source_path"] for ref in refs if ref["source_path"]}
        if claim_eligible:
            claimed_paths.update(exact_paths)

        for ref in refs:
            source_path = ref["source_path"]
            expected = ref["expected_content_sha256"]
            if not source_path or not _SHA256_RE.fullmatch(expected):
                unknown = True
                reasons.append(f"SOURCE_REF_INVALID:{source_path or '<missing>'}")
                continue
            if source_path in removed_or_renamed:
                stale = True
                reasons.append(f"SOURCE_REMOVED_OR_RENAMED:{source_path}")
                affected_paths.add(source_path)
                continue
            actual = observed.get(source_path)
            if actual is None or not _SHA256_RE.fullmatch(actual):
                unknown = True
                reasons.append(f"SOURCE_IDENTITY_UNOBSERVED:{source_path}")
                continue
            if actual != expected:
                stale = True
                reasons.append(f"SOURCE_HASH_MISMATCH:{source_path}")
                affected_paths.add(source_path)

        for path in changed_paths:
            if path in exact_paths:
                continue
            if _matches_any(path, covers):
                affected_paths.add(path)
                if claim_eligible:
                    claimed_paths.add(path)

        if global_unknown or unknown:
            status = KnowledgeApplicabilityStatus.UNKNOWN
        elif stale:
            status = KnowledgeApplicabilityStatus.STALE_EXACT_SOURCE
        elif affected_paths:
            status = KnowledgeApplicabilityStatus.AFFECTED_BY_COVERAGE
            reasons.extend(
                f"COVERED_PATH_CHANGED:{path}" for path in sorted(affected_paths)
            )
        else:
            status = KnowledgeApplicabilityStatus.CURRENT

        relations.append(
            KnowledgeApplicabilityRelationV1(
                artifact_id=artifact_id,
                artifact_path=artifact_path,
                status=status,
                reason_codes=tuple(sorted(set(reasons))),
                affected_paths=tuple(sorted(affected_paths)),
            )
        )

    claim_inventory_complete = (
        identity_ok
        and collection_complete
        and artifact_inventory_structurally_complete
        and collection_errors_input_valid
        and not caller_errors
    )
    uncovered = (
        tuple(
            path
            for path in changed_paths
            if _matches_any(path, in_scope) and path not in claimed_paths
        )
        if claim_inventory_complete
        else ()
    )

    is_complete = (
        identity_ok
        and collection_complete
        and not collection_errors
        and bool(in_scope)
        and all(
            relation.status is not KnowledgeApplicabilityStatus.UNKNOWN
            for relation in relations
        )
    )
    report = KnowledgeApplicabilityReportV1(
        identity=identity,
        knowledge_artifacts=artifacts,
        changes=changes,
        observed_source_sha256=observed,
        in_scope=in_scope,
        collection_complete=collection_complete,
        collection_errors=collection_errors,
        relations=tuple(relations),
        uncovered_changes=uncovered,
        evidence_gaps=tuple(sorted(set(evidence_gaps))),
        is_complete=is_complete,
        content_sha256="",
    )
    return replace(report, content_sha256=_hash_payload(report.to_dict()))


def verify_knowledge_applicability_report(payload: Mapping[str, Any]) -> bool:
    """Recompute the report from embedded neutral inputs and reject tampering."""
    if not isinstance(payload, Mapping):
        return False
    if payload.get("schema") != KNOWLEDGE_APPLICABILITY_SCHEMA:
        return False
    if payload.get("claim_ceiling") != KNOWLEDGE_APPLICABILITY_CLAIM_CEILING:
        return False
    supplied_hash = payload.get("content_sha256")
    if not isinstance(supplied_hash, str) or not _SHA256_RE.fullmatch(supplied_hash):
        return False
    if _hash_payload(payload) != supplied_hash:
        return False

    identity = payload.get("identity")
    if not isinstance(identity, Mapping):
        return False
    neutral = {
        "snapshot": {
            "repository": identity.get("repository", ""),
            "pr_number": identity.get("pr_number", 0),
            "head_sha": identity.get("head_sha", ""),
            "base_sha": identity.get("base_sha", ""),
            "current_main_sha": identity.get("current_main_sha", ""),
            "declared_base_sha": identity.get("declared_base_sha"),
            "declared_head_sha": identity.get("declared_head_sha"),
            "declared_main_sha": identity.get("declared_main_sha"),
        },
        "knowledge_artifacts": payload.get("knowledge_artifacts", []),
        "changes": payload.get("changes", []),
        "observed_source_sha256": payload.get("observed_source_sha256", {}),
        "in_scope": payload.get("in_scope", []),
        "collection_complete": payload.get("collection_complete") is True,
        "collection_errors": payload.get("collection_errors", []),
    }
    try:
        expected = analyze_knowledge_applicability(neutral).to_dict()
    except (TypeError, ValueError):
        return False
    return dict(payload) == expected
