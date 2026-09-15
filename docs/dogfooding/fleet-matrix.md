# Fleet Dogfooding Coverage Matrix

This is a human-readable projection of `corpus.v1.json`. The JSON corpus is the machine-validated evidence registry; this file does not add authority or evidence by itself.

## Repository coverage

| Repository | Sidecar | Current evidence state | Recorded case | What is actually proven |
|---|---|---|---|---|
| `James3014/Nexus-new` | integrated | `CANARY_ONLY` | — | Canonical sidecar was integrated after the original canary/governed rollout. No separately inspected post-rollout case is claimed by this corpus yet. |
| `James3014/devspace` | integrated | `FAILURE_WITNESS` | `DEVSPACE-158-STALE-BASE`, `DEVSPACE-171-POST-ROLLOUT` | A real stale-base condition was surfaced and blocked; later post-rollout exact-head artifact acquisition also succeeded. |
| `James3014/nexus-core` | integrated | `CANARY_ONLY` | — | Initial fleet canary/integration succeeded. No later case is asserted here. |
| `James3014/nexus-learning` | integrated | `CANARY_ONLY` | — | Initial fleet canary/integration succeeded. No later case is asserted here. |
| `James3014/nexus-open-swe-runtime` | integrated | `CANARY_ONLY` | — | Initial fleet canary/integration succeeded. No later case is asserted here. |
| `James3014/repository-intelligence-engine` | integrated | `POST_ROLLOUT_WITNESS` | `RIE-17-POST-ROLLOUT` | Self-dogfooding continued after rollout with an exact-head advisory artifact. |
| `James3014/nexus-runtime` | integrated | `CANARY_ONLY` | — | Initial fleet canary/integration succeeded. No later case is asserted here. |
| `James3014/nexus-opencli-reviewer` | integrated | `CANARY_ONLY` | — | Canonical sidecar coexists with the legacy reviewer path; no later case is asserted here. |

## Failure-family evidence matrix

| Failure family | Live fleet witness | Controlled reproduction | Source forensics | Current bounded interpretation |
|---|---|---|---|---|
| `STALE_BASE` | **Yes** — `devspace` #158 | not required for this claim | prior semantics/tests exist | Demonstrated in normal fleet operation; RIE returned stale/block semantics before the rollout PR was recreated against a fresh base. |
| `COMMIT_STATUS_CHANNEL_OMISSION` | not claimed | **Yes** — RIE Issue #10 / PR #11 | repair source merged | A false-completeness mechanism was reproduced and repaired; no fleet incidence rate is claimed. |
| `COMMIT_STATUS_HEAD_BINDING` | not claimed | not claimed | **Open** — RIE PR #17 | A concrete REST identity-binding seam has a tested Candidate; the corpus does not promote it to an accepted/merged repair. |
| `EVIDENCE_INCOMPLETE` | not yet recorded | test coverage exists outside this corpus | semantics exist | The engine has an explicit family/state, but Wave C has not observed a qualifying live fleet case. |
| `UNEXPECTED_TERMINAL_CI_FAILURE` | not yet recorded | test coverage exists outside this corpus | semantics exist | The engine can represent it, but Wave C has not yet admitted a live exact-head fleet witness. |

## Positive operating witnesses

### `DEVSPACE-171-POST-ROLLOUT`

- repo / PR: `James3014/devspace#171`
- exact head: `0eac76ec2e6b05d5cb668b9ae648a52dc3a2ff58`
- RIE run: `35025580873`
- artifact: `10419078098`
- artifact digest: `sha256:981b67e395ac950de7c634d7cb9479e3aeccd2769207273abb0fb8eb7f1e2603`
- bundle: `ADVISORY_EVIDENCE_ONLY`, `REVIEW_READY`, `COMPLETE`
- CFI snapshot: `NO_TERMINAL_FAILURE`, 12 checks observed

This proves exact-head sidecar operation on that PR. It does not turn the PR-event snapshot into a terminal-CI verdict.

### `RIE-17-POST-ROLLOUT`

- repo / PR: `James3014/repository-intelligence-engine#17`
- exact head: `6e53fd6b9f3385b2180d54d3e32d9dafac973a5c`
- RIE run: `34980563204`
- artifact: `10401261505`
- artifact digest: `sha256:b9399f8a8c105b3442da051a0fd569c9526e3af56cf9cb8cbe2194272e125964`
- bundle: `ADVISORY_EVIDENCE_ONLY`, `REVIEW_READY`, `COMPLETE`
- CFI snapshot: `NO_TERMINAL_FAILURE`, 3 checks observed

This is a self-dogfooding operating witness. The same PR is separately recorded as `SOURCE_FORENSICS` for `COMMIT_STATUS_HEAD_BINDING`; the positive sidecar artifact is not evidence that the proposed code repair is correct.

## Wave C closure criterion

Wave C infrastructure is complete when the corpus, validator, extractor, tests, and this matrix are integrated and verified. The matrix is intentionally allowed to contain unobserved failure families.

Long-term value evidence continues to accumulate as normal repository work creates new exact cases. Wave C completion does **not** require fabricating every failure family or waiting until every repository happens to fail.
