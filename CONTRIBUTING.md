# Contributing to Repository Intelligence Engine

Thank you for helping improve Repository Intelligence Engine.

This project is intentionally narrow: it provides deterministic, transport-neutral advisory intelligence over repository and pull-request evidence. Contributions should preserve that authority boundary.

## Before opening a change

Please open or reference a GitHub Issue for behavior changes, bug fixes, or non-trivial refactors. The Issue should describe the observed behavior, the desired bounded outcome, and any compatibility constraints.

Small documentation fixes may be submitted directly when the intent is unambiguous.

## Development setup

Requirements:

- Python 3.10+
- `pytest`

Clone the repository and run the test suite:

```bash
git clone https://github.com/James3014/repository-intelligence-engine.git
cd repository-intelligence-engine
python3 -m pytest -q
```

Also check the diff for whitespace errors:

```bash
git diff --check
```

## Pull requests

A pull request should:

- have one bounded objective;
- reference the relevant Issue when one exists;
- explain externally observable behavior changes;
- add or update tests for semantic changes;
- preserve backward compatibility unless the change explicitly requires otherwise;
- state the verification commands that were actually run and their results;
- avoid mixing advisory intelligence with approval, merge, release, deployment, worker-dispatch, or Candidate-acceptance authority.

When evidence identity, hashing, or verification semantics change, include negative tests showing that stale, incomplete, substituted, or tampered evidence still fails closed.

## Architecture boundary

The canonical `repository_intelligence` package owns deterministic intelligence contracts and classifications. Adapters acquire and normalize evidence. Higher-level systems own authority-bearing actions.

In particular, this project does not grant:

- pull-request approval;
- merge authority;
- release or deployment authority;
- worker dispatch;
- semantic code-review authority;
- production truth.

Please avoid adding a parallel implementation of an existing intelligence decision in an adapter or consumer. Extend the canonical engine when the semantics belong in the engine; otherwise keep repository-specific acquisition or policy outside it.

## Licensing

By submitting a contribution, you agree that your contribution is provided under the Apache License 2.0, consistent with the repository license.
