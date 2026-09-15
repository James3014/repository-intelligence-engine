# Repository Intelligence Engine — Agent Contract

This file is the repository-local operating contract for AI coding agents and automated contributors. It applies to the whole repository unless a deeper `AGENTS.md` narrows the rules for a subtree.

## Repository authority

This repository is the canonical implementation owner of the `repository_intelligence` package and its deterministic repository/pull-request intelligence contracts.

It owns:

- deterministic revision, readiness, overlap, CI, impact, CFI, and EIA semantics;
- hash-bound advisory evidence and public verification behavior;
- the canonical CLI and read-only adapter contracts that invoke this engine.

It does not own:

- semantic LLM review authority;
- coding/repair-worker dispatch authority;
- Candidate acceptance, approval, merge, release, deployment, or production truth;
- DevSpace, OpenCLI, Nexus runtime, or another consumer's policy authority.

Claim ceilings remain advisory. In particular, `REVIEW_READY`, `diagnosis_eligible=true`, or `EIA READY` never grants approval, mutation, merge, release, or dispatch authority.

## Required reading before mutation

Read the smallest relevant set:

- `README.md` for current product/ownership boundaries and public contracts;
- `CONTRIBUTING.md` for contribution and verification expectations;
- `docs/semantic-review-and-agent-boundary.md` when work touches semantic review, agents, Dev MCP, OpenCLI, or automation boundaries.

Do not import `Nexus-new` governance into this repository. A cross-repository document is evidence for its own repository only unless this repository explicitly adopts it.

## Change rules

1. Bind the current repository root, default branch, HEAD, and local dirty state before editing. Do not hard-code a historical SHA as standing authority.
2. Keep one bounded objective per change. Preserve unrelated user work and compatibility behavior outside the approved scope.
3. Behavior changes, bug fixes, and non-trivial refactors should reference a GitHub Issue or another explicit bounded contract. Small unambiguous documentation fixes may be direct.
4. Preserve a single intelligence authority. Adapters and compatibility shims may acquire, transport, serialize, or forward; they must not reimplement canonical intelligence decisions.
5. Preserve evidence identity, hashing, fail-closed behavior, and existing claim ceilings unless an explicit repository-local decision authorizes a semantic change.
6. Do not add model/provider selection, worker dispatch, repository writes, approval, merge, release, deployment, or production authority to the engine as a side effect of another task.
7. Cross-repository mutation requires separate explicit authority in the target repository and must follow that repository's own contract.
8. Do not self-authorize merge, release, tag movement, or publication. Those actions require explicit user/repository authority in addition to implementation correctness.

## Verification

Use the smallest meaningful verification for the changed surface and report only commands actually run.

- Documentation-only: inspect the physical diff and run `git diff --check` when a local Git checkout is available.
- Python or contract behavior: run targeted tests for the changed behavior, then `python3 -m pytest -q` when the environment supports the full suite.
- Evidence identity, hashing, or verification changes: include negative coverage for stale, incomplete, substituted, or tampered evidence.
- Adapter changes: verify the adapter still delegates decisions to the canonical engine rather than creating adapter-local semantics.

A skipped, unavailable, or not-run check is not a pass. Record the exact gap.

## Completion and stop boundary

Implementation output is a Candidate until applicable verification and repository integration are complete. A green test or advisory RI result is not acceptance, merge, release, deployment, or production evidence.

Stop and request/rebind authority when a task would:

- create a second intelligence/decision owner;
- expand this repository into semantic review or worker-dispatch authority;
- change public claim ceilings;
- mutate another repository without separate target-repo authority;
- perform merge, release, deployment, or another irreversible external effect without explicit authorization.
