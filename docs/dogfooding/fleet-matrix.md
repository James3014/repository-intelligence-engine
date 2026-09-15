# Fleet Dogfooding Coverage Matrix

This is a human-readable projection of `corpus.v1.json`. The JSON corpus is the machine-validated evidence registry; this file does not add authority or evidence by itself.

## Repository coverage

| Repository | Snapshot sidecar | Terminal sidecar | Current evidence state | Latest terminal witness | What is actually proven |
|---|---|---|---|---|---|
| `James3014/Nexus-new` | integrated | integrated | `CANARY_ONLY` | — | Both workflow stages are integrated. No separately admitted post-rollout terminal artifact is claimed by this corpus yet. |
| `James3014/devspace` | integrated | integrated | `FAILURE_WITNESS` | — | A real stale-base condition was surfaced and blocked; later snapshot operation also succeeded. Terminal integration exists, but no terminal artifact is admitted here yet. |
| `James3014/nexus-core` | integrated | integrated | `CANARY_ONLY` | — | Both workflow stages are integrated; no later terminal case is asserted here. |
| `James3014/nexus-learning` | integrated | integrated | `CANARY_ONLY` | — | Both workflow stages are integrated; no later terminal case is asserted here. |
| `James3014/nexus-open-swe-runtime` | integrated | integrated | `CANARY_ONLY` | — | Both workflow stages are integrated; no later terminal case is asserted here. |
| `James3014/repository-intelligence-engine` | integrated | integrated | `POST_ROLLOUT_WITNESS` | `RIE-25-TERMINAL-RELEASE-CANDIDATE` | PR #25 produced exact-head snapshot and terminal artifacts before the v0.1.2 release was published from the merged Candidate. |
| `James3014/nexus-runtime` | integrated | integrated | `CANARY_ONLY` | — | Both workflow stages are integrated; no later terminal case is asserted here. |
| `James3014/nexus-opencli-reviewer` | integrated | integrated | `FAILURE_WITNESS` | `OPENCLI-31-TERMINAL-FINAL` | v0.1.2 terminal observation caught a real CI failure on one head and a later exact-head terminal-success witness before merge. |

`integrated` is source/configuration evidence only. It is not a claim that a retained terminal artifact has been inspected for every repository.

## Failure-family evidence matrix

| Failure family | Live fleet witness | Controlled reproduction | Source forensics | Current bounded interpretation |
|---|---|---|---|---|
| `STALE_BASE` | **Yes** — `devspace` #158 | not required for this claim | prior semantics/tests exist | Demonstrated in normal fleet operation; RIE surfaced stale/block semantics before rollout was recreated against a fresh base. |
| `COMMIT_STATUS_CHANNEL_OMISSION` | not claimed | **Yes** — RIE Issue #10 / PR #11 | repair source merged | A false-completeness mechanism was reproduced and repaired; no fleet incidence rate is claimed. |
| `COMMIT_STATUS_HEAD_BINDING` | not claimed | not claimed | recorded — RIE PR #17 | Source/API-contract evidence identifies the exact-head binding seam. The historical corpus entry preserves the evidence ceiling of that observation. |
| `EVIDENCE_INCOMPLETE` | not yet recorded | test coverage exists outside this corpus | semantics exist | The engine represents this family, but the corpus does not invent a fleet witness. |
| `UNEXPECTED_TERMINAL_CI_FAILURE` | **Yes** — OpenCLI PR #31 head `7ddea3a…` | test coverage exists | semantics exist | The PR-event snapshot saw no terminal failure; the later terminal surface observed a real external CI failure on the same exact head. |

## Terminal operating witnesses

### `RIE-25-TERMINAL-RELEASE-CANDIDATE`

- repo / PR: `James3014/repository-intelligence-engine#25`
- exact head: `a8c502fe809dca39385aacafd595ea36b8b5700c`
- run: `35036708949`
- terminal artifact: `10424175091`
- terminal artifact digest: `sha256:962191c45151a751d74c00ec6bdd154095ee99fdf51029f3747a85f612e3a4e9`
- terminal bundle hash: `d64d85b51bd6212b0ba9ea5d447184b5be2d46f34eb82a0206abe241db0fdb7b`
- observed external checks: `1`
- terminal result: `REVIEW_READY / NO_TERMINAL_FAILURE / NO_ACTION`

This proves bounded terminal observation on the exact release-candidate head. The workflow used the pre-release exact terminal commit pin; it does not retroactively claim that PR #25 consumed the later-created `v0.1.2` tag.

### `OPENCLI-31-TERMINAL-CI-FAILURE`

- repo / PR: `James3014/nexus-opencli-reviewer#31`
- exact head: `7ddea3ad4b56407ada724e9fb687eb4a7561dbd7`
- run: `35037059986`
- terminal artifact: `10424050547`
- terminal artifact digest: `sha256:6c80d5f767b80c49e7a8efd8f3ff039c146338b3888727cd20dc2d6fe695b45a`
- terminal bundle hash: `d9132d16a6de6ec4b8bf770507105ed7921a8ddcef36de0090abf6f418b394d4`
- observed external checks: `1`
- terminal result: `REVIEW_READY / UNEXPECTED_FAILURE_OBSERVED / READY`

The root PR-event snapshot on the same head reported `NO_TERMINAL_FAILURE`, while the later terminal observation captured the external CI failure. `READY` is EIA advisory eligibility only; it did not dispatch a worker or grant merge authority.

### `OPENCLI-31-TERMINAL-FINAL`

- repo / PR: `James3014/nexus-opencli-reviewer#31`
- exact head: `deb5143180f4dfcfb7755988778e8ad2a9179bbc`
- run: `35037181503`
- terminal artifact: `10423602713`
- terminal artifact digest: `sha256:af46e3e46b65ca6043912c38cf90a4bd9431597bb903158b2faaedb255b3a2fd`
- terminal bundle hash: `35324143f806b5f9d177aed82debaad600533dee73d5a26c4a6adac129f8bc94`
- observed external checks: `1`
- terminal result: `REVIEW_READY / NO_TERMINAL_FAILURE / NO_ACTION`

The final exact head also had successful repository CI before merge. This is a bounded first-party operating witness, not Candidate acceptance, required-check completeness, or third-party adoption evidence.

## Evidence authority boundary

The corpus and this matrix remain `OBSERVATIONAL_EVIDENCE_ONLY`.

```text
GitHub Actions artifacts
        ↓
corpus.v1.json            canonical retained dogfooding registry
        ↓
fleet-matrix.md           human-readable derived projection
```

Neither the corpus nor the matrix is a second Repository Intelligence implementation. Neither grants approval, Candidate acceptance, worker dispatch, merge, release, deployment, or production authority.
