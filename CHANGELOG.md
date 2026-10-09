# Changelog

All notable changes to Repository Intelligence Engine are documented here.

The project follows semantic versioning while it remains in the `0.x` series. Immutable release tags are never moved after publication.

## [Unreleased]

### Added

- Terminal observation failures now write a deterministic, hash-bound `reviewer.repository_intelligence_terminal_error.v1` envelope to the `--output` / `report-path` file (and set the `report-path` / `content-sha256` Action outputs) in addition to the existing stderr JSON and exit code 1. The envelope records `status=ERROR`, an `error_class` (`OBSERVATION_TIMEOUT`, `HEAD_CHANGED`, `GITHUB_RATE_LIMITED`, `GITHUB_READ_FAILED`, `INVALID_INPUT`, `UNKNOWN`), a bounded `error` message, the observation parameters, `observed_at`, and `content_sha256`. This lets consumers distinguish a genuine observation timeout from a GitHub read failure. Refs the terminal error-reporting gap.

### Safety boundary

- The error envelope is advisory evidence only under the existing `ADVISORY_EVIDENCE_ONLY` claim ceiling. The step still fails closed, the success bundle schema is unchanged, and no approval, merge, or release authority is granted.

## [0.1.3] - 2026-10-08

### Added

- New `facts` operation emitting a `reviewer.structured_facts.v1` report of revision-bound, deterministic semantic-pattern facts with exact `content_sha256` (Issue #27). Adds the `REPOSITORY_FACTS_ONLY` claim ceiling, the `analyze_structured_facts` engine, the `verify_structured_facts_report` semantic verifier (recomputes derived facts from embedded neutral inputs, so tampering is rejected and not only byte-hash mismatch), and the stdlib-`ast` collector `adapters/python_fact_detector.py`. `EMPTY_EXCEPTION_HANDLER`, `BROAD_EXCEPTION_HANDLER`, `SUBPROCESS_CALL`, and `SILENT_RETRY_PATTERN` are detected deterministically; `NETWORK_ENDPOINT_ADDED` and `VISIBLE_AUTH_CHECK` remain `UNKNOWN` pending detectors; `RELATED_TEST_CHANGED` is derived from `changed_files`.
- New `query` operation emitting a `reviewer.repository_query_evidence.v1` report that narrows repository candidates before any semantic review (Issue #29). Adds the `REPOSITORY_QUERY_EVIDENCE_ONLY` claim ceiling, the `analyze_repository_query` reciprocal-rank-fusion engine (`k=60`), the `verify_repository_query_evidence` semantic verifier, retriever/candidate/report contracts, and `scripts/benchmark_retrieval.py`.
- Task-aware retrieval extension (Issue #31): `analyze_task_aware_query` / `verify_task_aware_query_evidence` produce a `reviewer.task_aware_repository_query_evidence.v1` report under the `TASK_AWARE_REPOSITORY_QUERY_EVIDENCE_SHADOW_ONLY` ceiling, with weighted fusion order, per-source contribution, missing-source and evidence-gap reporting, and candidate-reduction accounting. The canonical query evidence is preserved and weighted projections are recomputed by the verifier. This is a Python-level API in `repository_intelligence.retrieval`, not a separate CLI operation. Also adds `scripts/benchmark_real_repository_retrieval.py`.
- Check-role classification `repository_intelligence/check_roles.py` (Issues #32, #44): `classify_check_roles` and `verify_check_role_report` emit a `repository_intelligence.check_roles.v1` report that separates `REQUIRED_GATE` from `ADVISORY_CHECK` checks using caller-supplied policy roles, under the `CI_POLICY_ROLE_EVIDENCE_ONLY` ceiling. Checks with a missing name, a duplicate name, or no policy role are `UNKNOWN_POLICY_ROLE`. Each check is bound to the exact review head: a check whose `head_sha` is missing or differs from the review head is not counted as successful (`CHECK_HEAD_MISSING` / `CHECK_HEAD_MISMATCH`), and an incomplete exact review identity (repository, head, base, current main) is rejected. The report also records check-set stability against previously observed names.
- GitHub installation rate-limit retry in `adapters/github_action.py` (Issue #45): `GitHubReadClient` performs bounded, header-aware retries (`Retry-After`, `X-RateLimit-Reset`, bounded wait with a fallback; defaults of 2 retries and 60 s maximum wait) on primary and secondary rate limits. Ordinary 403 responses remain fail-closed.
- Advisory-unavailable evidence (Issue #49): when rate-limit retries are exhausted the Action emits a hash-bound `reviewer.repository_intelligence_unavailable.v1` bundle (`status=UNAVAILABLE`, `reason=RATE_LIMIT_EXHAUSTED`, `cfi_status=INSUFFICIENT_EVIDENCE`) with its own self-verification, step summary, and outputs instead of failing silently or reporting a false green. All other failures remain fail-closed.
- New `knowledge` operation in `repository_intelligence/knowledge.py` (Issue #56): `analyze_knowledge_applicability` / `verify_knowledge_applicability_report` emit a `reviewer.knowledge_applicability.v1` report classifying repository-bound knowledge artifacts as `CURRENT`, `STALE_EXACT_SOURCE`, `AFFECTED_BY_COVERAGE`, or `UNKNOWN` from exact source changes and declared coverage, under the `REPOSITORY_KNOWLEDGE_APPLICABILITY_EVIDENCE_ONLY` ceiling. It never inspects or rewrites knowledge content.
- New `guard-delta` operation in `repository_intelligence/guard_delta.py` (Issue #57): `analyze_guard_semantic_delta` / `verify_guard_semantic_delta_report` emit a `reviewer.guard_semantic_delta.v1` report classifying mechanically observable changes in normalized policy/gate structure as `TIGHTENS`, `LOOSENS`, `MIXED`, `UNCHANGED`, or `UNKNOWN`, under the `GUARD_SEMANTIC_DELTA_ADVISORY_EVIDENCE_ONLY` ceiling.
- CLI projection of `knowledge` and `guard-delta` (Issue #60), with tests covering all projected operations.

### Changed

- CLI now exposes eleven operations: `cfi`, `ci`, `eia`, `facts`, `guard-delta`, `impact`, `knowledge`, `overlap`, `query`, `readiness`, `revision`. The public verification surface adds `verify_structured_facts_report`, `verify_repository_query_evidence`, `verify_check_role_report`, `verify_knowledge_applicability_report`, and `verify_guard_semantic_delta_report`.
- Repository governance adopts the Nexus Core v2 evidence contract in `.nexus-core/config.toml` (Issue #53): version 2 config with `pytest` (`test-result`) and `diff-check` (`static-check`) verifiers and a pinned v2 `nexus-certify`, plus the Issue-bound PR gate and trusted default-branch Core gate. These are repository governance changes and do not alter engine behavior.
- Added the hybrid replication capture observer workflow and hardened its admission observer; retained terminal fleet dogfooding evidence (Issue #24).
- README documents the eleven-operation capability table and check-role classification and pins release examples to `v0.1.3`; `pyproject.toml` version is `0.1.3`.
- `facts`, `query`, `knowledge`, and `guard-delta` are not claimed live through Dev MCP; that projection requires a separate DevSpace cutover.

### Safety boundary

- All new evidence is advisory and hash-bound. None of it grants approval, merge, release, worker dispatch, routing, Candidate acceptance, or production authority.
- Structured facts describe code shape only; stale or incomplete observation sets fail closed to `UNRESOLVED`.
- Empty retrieval is never proof of absence (`EMPTY_RETRIEVAL_NOT_ABSENCE`); stale/different-revision candidates, retriever-index substitution, duplicate candidate inflation, and dropped exact-match evidence are rejected by the verifier.
- Check-role evidence does not infer repository required-check topology; roles come only from caller-supplied policy, and unbound or unclassifiable checks fail closed.
- Rate-limit exhaustion yields `UNAVAILABLE` / `INSUFFICIENT_EVIDENCE` evidence, never a passing result.
- This release changes documentation and version metadata only; no engine semantics or claim ceilings change in the release PR.

### Verification

- Full test suite: 344 passed (`python -m pytest -q`, Python 3.12).

## [0.1.2] - 2026-09-16

### Added

- Published `terminal/` as an optional second-stage GitHub Action that waits for one exact PR head's observed external Check Run / Commit Status set to become terminal and stable for a bounded quiescence window.
- Terminal evidence records its observation semantics and remains hash-bound under `ADVISORY_EVIDENCE_ONLY`.

### Changed

- Public installation and GitHub Action examples now pin the immutable `v0.1.2` release.
- Documentation now distinguishes PR-event snapshot evidence from terminal observed-check evidence.

### Safety boundary

- Terminal observation does not infer repository required-check topology, Candidate acceptance, all-green CI, or merge readiness.
- The release adds no repository write, worker-dispatch, approval, merge, deployment, or production authority.

### Verification

- Full test suite: 212 passed on the `v0.1.2` release candidate.
- Wheel build: `repository_intelligence_engine-0.1.2-py3-none-any.whl` built successfully with Python 3.12.
- Hosted PR #25 checks: package test, PR-event snapshot, and terminal observation all passed on the exact Candidate head.

## [0.1.1] - 2026-09-15

### Fixed

- GitHub Action evidence acquisition now includes GitHub Commit Statuses together with Check Runs for the exact pull-request head.
- CI evidence completeness fails closed when either required status channel cannot be acquired.

### Changed

- Public installation and GitHub Action examples pin the immutable `v0.1.1` release so documented behavior matches the published consumer ref.
- Package metadata declares the Apache-2.0 license and project URLs.
- Added contributor and security guidance for external maintainers and consumers.

### Verification

- Full test suite: 180 passed on the `v0.1.1` release candidate.
- Wheel build: `repository_intelligence_engine-0.1.1-py3-none-any.whl` built successfully.
- Fresh cross-repository GitHub Actions canary completed successfully against `James3014/Nexus-new` PR #967 using `repository-intelligence-engine@v0.1.1`; the report was exact-identity-bound with `evidence_completeness=COMPLETE` and `ADVISORY_EVIDENCE_ONLY`.

## [0.1.0]

Initial consumer-productized release with the canonical deterministic engine, CLI, read-only GitHub Action, hash-bound report verification, and the initial cross-repository canary against `James3014/Nexus-new`.

Verified by the Nexus Core two-job gate (container isolation, signed receipts) since 2026-10-09.
