# Changelog

All notable changes to Repository Intelligence Engine are documented here.

The project follows semantic versioning while it remains in the `0.x` series. Immutable release tags are never moved after publication.

## [Unreleased]

### Added

- New `facts` operation emitting a `reviewer.structured_facts.v1` report of revision-bound, deterministic semantic-pattern facts with exact `content_sha256`.
- `RepositoryFactKind`, `RepositoryFactStatus`, evidence, fact, and report contracts plus the `REPOSITORY_FACTS_ONLY` claim ceiling.
- `analyze_structured_facts` classification engine and `verify_structured_facts_report` semantic verifier (recomputes derived facts from embedded neutral inputs and rejects tampering, not only byte-hash mismatch).
- Python AST pattern collector `adapters/python_fact_detector.py` (stdlib `ast` only); classes `EMPTY_EXCEPTION_HANDLER`, `BROAD_EXCEPTION_HANDLER`, `SUBPROCESS_CALL`, and `SILENT_RETRY_PATTERN` are covered deterministically; `NETWORK_ENDPOINT_ADDED` and `VISIBLE_AUTH_CHECK` remain `UNKNOWN` pending detectors.
- `RELATED_TEST_CHANGED` derived from `changed_files` and scoped to the exact revision identity.

### Changed

- CLI now exposes eight operations (`facts` added); public verification surface adds `verify_structured_facts_report`.
- The `facts` operation is not yet claimed live through Dev MCP; that projection requires a separate DevSpace cutover.
- README documents the `facts` capability, its fail-closed behavior, and the `REPOSITORY_FACTS_ONLY` claim ceiling.

### Safety boundary

- Structured facts describe code shape only and never grant approval, merge, release, worker dispatch, or production authority.
- Stale or incomplete observation sets fail closed to `UNRESOLVED` rather than reporting a false green.

### Verification

- Full test suite: 248 passed.

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
