# Changelog

All notable changes to Repository Intelligence Engine are documented here.

The project follows semantic versioning while it remains in the `0.x` series. Immutable release tags are never moved after publication.

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
