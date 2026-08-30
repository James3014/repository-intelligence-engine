# Repository Intelligence Engine

`repository-intelligence-engine` is an independent, deterministic, transport-neutral advisory engine for repository and pull-request intelligence.

It answers questions such as:

- Is this PR still bound to the repository state we think it is?
- Is the PR structurally ready for review, or is it stale / incomplete / excluded?
- Are multiple PRs colliding on the same files or Issue chain?
- Which CI failures are terminal, expected, unexpected, complete, or safe to escalate for diagnosis?
- If a changed file is part of a dependency graph, what is the direct and transitive blast radius?
- Is there enough exact CI evidence for an external diagnosis workflow to be considered?

The engine is deliberately **advisory-only**. It can describe repository state and produce hash-bound evidence, but it cannot approve, merge, release, publish, dispatch workers, or execute pull-request source.

Current release: **`v0.1.0`**

Canonical Python package: **`repository_intelligence`**

Python: **3.10+**

Runtime dependencies: **none**

---

## Why this exists

Repository tooling often mixes together three different responsibilities:

1. collecting facts from GitHub or a local checkout;
2. interpreting those facts;
3. taking authority-bearing actions such as merge, release, or worker dispatch.

Repository Intelligence separates those concerns.

```text
GitHub / local Git / CI / custom collector
                  |
                  | normalized evidence
                  v
       repository-intelligence-engine
                  |
                  | deterministic advisory output
                  v
      GPT / Codex / CI / Nexus / humans
                  |
                  | separate authority layer
                  v
      review / execution / merge decision
```

The engine owns only deterministic intelligence contracts and decisions. Acquisition stays in adapters, and authority stays outside the engine.

This makes the same intelligence reusable from GitHub Actions, Dev MCP, a CLI, Python code, or another system without creating multiple competing implementations.

---

## What is independent now?

The following are canonical in this repository:

- the `repository_intelligence` Python package;
- all seven V1/V1.1 intelligence operations;
- the CLI adapter;
- the read-only GitHub Action;
- the GitHub REST acquisition adapter;
- public verification functions for hash-bound reports;
- consumer compatibility tests.

`nexus-opencli-reviewer` is now a legacy consumer / compatibility surface rather than the implementation owner of Repository Intelligence.

DevSpace can project the same engine through MCP, but DevSpace is a **consumer adapter**, not the Repository Intelligence source of truth.

---

## Capabilities

| Operation | What it answers | Typical development value | Maximum claim |
|---|---|---|---|
| `revision` | "Am I looking at the exact PR/base/main revisions I think I am?" | prevents stale review, wrong-head evidence, and base drift | `PR_INTELLIGENCE_ONLY` |
| `readiness` | "Is this PR structurally ready to review?" | surfaces draft, non-mergeable, stale, do-not-merge, incomplete collection, protected-path and related findings | `PR_INTELLIGENCE_ONLY` |
| `overlap` | "Do active PRs collide?" | detects shared changed paths and shared Issue chains before parallel work conflicts | `PR_INTELLIGENCE_ONLY` |
| `ci` | "What exact terminal CI failure evidence exists?" | creates a stable fingerprint with expected/unexpected failure provenance | `CI_EVIDENCE_ONLY` |
| `impact` | "What downstream files can this change affect?" | computes direct/transitive blast radius from caller-supplied dependency graph evidence | `PR_INTELLIGENCE_ONLY` |
| `cfi` | "Is CI failure evidence complete and diagnosis-worthy?" | separates no failure, expected-only failure, unexpected failure, and insufficient evidence | `CI_EVIDENCE_ONLY` |
| `eia` | "May an external diagnosis action be considered for this exact evidence?" | creates a hash-bound, idempotent advisory envelope for unattended/cloud consumers | `AUTOMATION_ADVISORY_ONLY` |

### Readiness dispositions

`readiness` can return:

- `REVIEW_READY`
- `WAIT_REBIND`
- `NEEDS_ATTENTION`
- `EVIDENCE_ONLY`
- `STALE`
- `EXCLUDED`

A `REVIEW_READY` result is still advisory. It is not approval or merge authority.

---

## Capability details

### 1. Revision identity

Repository Intelligence binds review evidence to a five-part identity:

```text
(repository, pr_number, head_sha, base_sha, current_main_sha)
```

It can also compare declared evidence identity against observed identity and surface:

- stale base;
- stale declared base;
- stale declared head;
- stale declared main;
- invalid or incomplete identity evidence.

This prevents a common development failure mode: reviewing or acting on evidence that belonged to a different PR head or an older `main`.

### 2. PR readiness

`readiness` deterministically classifies normalized PR evidence. Depending on the supplied evidence and policy, findings can include conditions such as:

- stale base / stale evidence;
- draft PR;
- non-mergeable PR;
- do-not-merge signal;
- incomplete evidence collection;
- expected or unexpected CI failure;
- consumer-defined protected-path overlap;
- stale/long-lived labels.

Generic Repository Intelligence does **not** hard-code Nexus governance paths. Consumers can inject their own `RepositoryIntelligencePolicyV1`, including protected path patterns and stale-label policy.

### 3. Cross-PR overlap

`overlap` accepts multiple normalized PR snapshots and detects:

- shared changed paths;
- multiple PRs referring to the same Issue chain.

When otherwise review-ready PRs collide, the engine can move them to `WAIT_REBIND` rather than silently treating both as independently safe.

This is especially useful when several agents or developers work in parallel.

### 4. CI failure fingerprinting

`ci` produces hash-bound terminal failure evidence with fields such as:

- exact review identity;
- expected vs unexpected failures;
- check-run / run / job / artifact identity when supplied;
- failed check metadata;
- evidence completeness;
- a deterministic failure fingerprint;
- `content_sha256`.

The corresponding verifier rejects semantic tampering, not only a bad file hash.

### 5. Change Impact Intelligence

`impact` is language-neutral. It does **not** parse source code by itself.

A caller supplies normalized graph evidence:

```json
{
  "snapshot": {
    "repository": "owner/repo",
    "pr_number": 50,
    "head_sha": "h50",
    "base_sha": "m50",
    "current_main_sha": "m50",
    "changed_files": ["pkg/leaf.py"]
  },
  "covered_files": ["pkg/leaf.py", "pkg/mid.py", "pkg/root.py"],
  "dependency_edges": [
    {"consumer": "pkg/mid.py", "dependency": "pkg/leaf.py"},
    {"consumer": "pkg/root.py", "dependency": "pkg/mid.py"}
  ],
  "observed_symbols": {
    "pkg/leaf.py": ["compute_value"]
  },
  "graph_complete": true,
  "graph_errors": []
}
```

The engine returns direct, transitive, and total impact sets. In the example above:

```text
pkg/leaf.py changed
    |
    v
pkg/mid.py       direct impact
    |
    v
pkg/root.py      transitive impact
```

This lets a repository-specific parser, AST index, dependency service, or build graph provide evidence while the canonical impact semantics stay language-neutral.

### 6. CI Failure Intelligence (CFI)

`cfi` converts exact CI failure evidence into one of four deterministic states:

- `NO_TERMINAL_FAILURE`
- `EXPECTED_FAILURE_ONLY`
- `UNEXPECTED_FAILURE_OBSERVED`
- `INSUFFICIENT_EVIDENCE`

It also emits `diagnosis_eligible`.

Important: `diagnosis_eligible=true` means there is enough bounded evidence to consider diagnosis. CFI does **not** claim root cause, regression attribution, repair correctness, merge readiness, or production safety.

### 7. External Intelligence Automation (EIA)

`eia` consumes either:

```json
{"snapshot": {"...": "normalized PR snapshot"}}
```

or a verified CFI report:

```json
{"cfi_report": {"...": "verified reviewer.ci_failure_intelligence.v1"}}
```

It returns:

- `READY`
- `NO_ACTION`
- `BLOCKED`

plus:

- `action_kind`;
- an idempotency key;
- exact evidence references;
- reason codes;
- evidence gaps;
- `content_sha256`.

`READY` means only that a downstream controller may **consider** the described action using the exact evidence reference. It does not dispatch anything and grants no execution authority.

---

## How it helps development

### Prevent stale or misbound review

A PR review can look correct while actually referring to an older head or an old base. `revision` makes repository, PR, head, base, and current-main identity explicit before downstream reasoning begins.

### Reduce parallel-agent collisions

When several developers, Codex sessions, or autonomous workers produce PRs concurrently, `overlap` can identify shared files or Issue chains before two changes are reviewed as if they were independent.

### Separate CI facts from diagnosis guesses

`ci` and `cfi` turn raw checks into typed, hash-bound evidence. This lets a later model reason from a stable evidence object instead of from an unstructured "CI is red" narrative.

### Make blast radius explicit

`impact` lets a repository-specific dependency graph answer "what could this change affect?" without moving parsing or language-specific logic into the intelligence core.

### Make automation fail closed

`eia` blocks stale identity and insufficient evidence, and emits an idempotency key tied to exact evidence. This is useful for unattended systems that must not repeatedly or ambiguously react to the same CI event.

### Give humans and agents one deterministic substrate

GitHub Actions, GPT, Codex, Dev MCP, local scripts, and other consumers can all call the same engine. That reduces logic drift between CI automation and interactive agent workflows.

### Improve evidence provenance

Hash-bound reports and explicit evidence completeness make it easier to tell whether a downstream conclusion is based on complete, partial, stale, or tampered evidence.

---

## Ways to use it

There are four primary consumption modes.

### A. GitHub Action — easiest for any repository

Use this when you want every pull request to produce Repository Intelligence automatically.

```yaml
name: Repository Intelligence

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: read
  pull-requests: read
  checks: read

jobs:
  repository-intelligence:
    runs-on: ubuntu-latest
    steps:
      - id: ri
        uses: James3014/repository-intelligence-engine@v0.1.0

      - uses: actions/upload-artifact@v4
        with:
          name: repository-intelligence
          path: ${{ steps.ri.outputs.report-path }}
```

The action automatically acquires, through GitHub REST:

- repository identity;
- PR number;
- base SHA;
- head SHA;
- current default-branch SHA;
- changed filenames;
- labels / draft / mergeability metadata;
- check-run evidence.

It deliberately does **not**:

- invoke `actions/checkout`;
- read PR blobs;
- execute PR code;
- comment on the PR;
- approve or merge;
- dispatch a worker.

The GitHub Action currently emits a cloud bundle containing:

- `revision`;
- `readiness`;
- `cfi`;
- `eia`;
- exact `review_identity`;
- top-level `ADVISORY_EVIDENCE_ONLY`;
- bundle `content_sha256`.

Operations such as cross-PR `overlap` and graph-based `impact` require evidence that one PR event alone does not provide, so they are available through CLI, Python, Dev MCP, or custom adapters instead of being guessed by the Action.

#### Action inputs

| Input | Default | Description |
|---|---|---|
| `pr-number` | current `pull_request` event | Explicit PR number, useful outside a normal PR event |
| `report-path` | `repository-intelligence.json` | Output JSON path in the caller workspace |

#### Action outputs

| Output | Meaning |
|---|---|
| `report-path` | Generated JSON evidence bundle path |
| `content-sha256` | Canonical SHA-256 of the bundle |
| `readiness` | PR readiness disposition |
| `cfi-status` | CFI status |
| `eia-decision` | EIA advisory decision |
| `claim-ceiling` | Top-level `ADVISORY_EVIDENCE_ONLY` |

### B. CLI — easiest for local tools and pipelines

Install directly from the immutable release tag:

```bash
python3 -m pip install \
  "git+https://github.com/James3014/repository-intelligence-engine.git@v0.1.0"
```

Then:

```bash
repository-intelligence --help
```

or:

```bash
python3 -m repository_intelligence.cli --help
```

Supported operations:

```text
revision
readiness
overlap
ci
impact
cfi
eia
```

Example:

```bash
repository-intelligence \
  --operation readiness \
  --input snapshot.json
```

STDIN is also supported:

```bash
cat snapshot.json | repository-intelligence \
  --operation readiness \
  --input -
```

The CLI performs no GitHub/network writes and persists no engine state.

### C. Python package — best for custom integrations

```python
import repository_intelligence as ri

snapshot = {
    "repository": "owner/repo",
    "pr_number": 42,
    "head_sha": "head_sha",
    "base_sha": "main_sha",
    "current_main_sha": "main_sha",
    "changed_files": ["src/core.py"],
    "checks": [],
    "collection_complete": True,
    "collection_errors": [],
}

identity = ri.revision_identity(snapshot)
readiness = ri.classify_readiness(snapshot)

print(identity.review_identity)
print(readiness.disposition.value)
```

For repositories with custom governance paths, inject policy instead of modifying the core:

```python
policy = ri.RepositoryIntelligencePolicyV1(
    protected_path_patterns=("infra/", "security/", "policy/"),
    stale_labels=("stale", "long-lived"),
)

result = ri.classify_readiness(snapshot, policy=policy)
```

Public verification functions include:

```text
verify_ci_failure_evidence
verify_change_impact_report
verify_ci_failure_intelligence_report
verify_external_intelligence_automation_envelope
verify_repository_intelligence_report
```

### D. Dev MCP — best for GPT / Codex interactive workflows

DevSpace can expose the engine as seven read-only MCP tools:

```text
repository_intelligence_revision
repository_intelligence_readiness
repository_intelligence_overlap
repository_intelligence_ci
repository_intelligence_impact
repository_intelligence_cfi
repository_intelligence_eia
```

The Dev MCP projection is a consumer of this repository. Each result can report the exact engine HEAD used for the call.

A typical interactive flow is:

```text
GPT / Codex
    |
    | acquire repository / PR evidence
    v
Dev MCP
    |
    | one of seven RI native calls
    v
repository-intelligence-engine
    |
    v
hash-bound advisory evidence
```

This gives agents structured intelligence without giving Repository Intelligence merge, approval, or worker-dispatch authority.

---

## Common normalized snapshot

Several operations accept a normalized PR snapshot. A useful common shape is:

```json
{
  "repository": "owner/repo",
  "pr_number": 77,
  "head_sha": "head777",
  "base_sha": "main000",
  "current_main_sha": "main000",
  "declared_head_sha": "head777",
  "declared_base_sha": "main000",
  "declared_main_sha": "main000",
  "changed_files": ["src/core.py"],
  "issue_numbers": [123],
  "labels": [],
  "draft": false,
  "mergeable": true,
  "checks": [
    {
      "name": "pytest",
      "status": "failure",
      "head_sha": "head777",
      "check_run_id": 1002,
      "expected_failure": false
    }
  ],
  "collection_complete": true,
  "collection_errors": []
}
```

Adapters are responsible for acquiring and normalizing evidence. The engine intentionally does not silently fetch missing facts.

---

## Cross-PR overlap input

```json
{
  "snapshots": [
    {
      "repository": "owner/repo",
      "pr_number": 1,
      "head_sha": "h1",
      "base_sha": "m1",
      "current_main_sha": "m1",
      "changed_files": ["pkg/common.py", "pkg/a.py"]
    },
    {
      "repository": "owner/repo",
      "pr_number": 2,
      "head_sha": "h2",
      "base_sha": "m1",
      "current_main_sha": "m1",
      "changed_files": ["pkg/common.py", "pkg/b.py"]
    }
  ]
}
```

```bash
repository-intelligence --operation overlap --input overlap.json
```

The result identifies `pkg/common.py` as a shared path and can move otherwise-ready PRs to `WAIT_REBIND`.

---

## Evidence completeness and fail-closed behavior

Repository Intelligence distinguishes:

- `COMPLETE`
- `PARTIAL`
- `INCOMPLETE`

Missing or malformed identity does not produce a claimable green result.

Change Impact also fails closed when graph evidence is incomplete, changed files are outside graph coverage, or graph evidence is inconsistent.

CFI does not mark diagnosis eligible unless failure evidence is complete and contains an unexpected terminal failure.

EIA blocks stale identity and insufficient evidence instead of converting uncertainty into automation permission.

---

## Hash binding and verification

Several reports include a canonical `content_sha256`.

The engine also exposes verification functions that recompute derivable semantics. This is stronger than checking only whether a JSON file has the same byte hash.

For example, a CFI report that is re-hashed after someone changes `diagnosis_eligible` is still rejected because the verifier recomputes the expected triage semantics from the embedded evidence.

The GitHub Action cloud bundle also verifies cross-report identity consistency so one report cannot be silently substituted from another PR head and then merely re-hashed.

---

## Architecture and ownership boundary

```text
                    external world
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
     GitHub REST      local Git       CI / graph
          |              |               |
          +--------------+---------------+
                         |
                         v
                 adapter / collector
                         |
                 normalized evidence
                         |
                         v
             repository_intelligence
          +--------------+---------------+
          |              |               |
          v              v               v
       PR facts       CI facts       impact facts
          |              |               |
          +--------------+---------------+
                         |
                         v
                advisory evidence
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
        human          agent           Nexus
                                       governance
```

### Engine owns

- contracts;
- deterministic classification;
- exact review identity;
- overlap semantics;
- CI failure evidence and fingerprints;
- change-impact semantics over supplied graph evidence;
- CFI triage;
- EIA advisory envelopes;
- hash-bound verification.

### Adapters own

- GitHub REST calls;
- local Git inspection;
- dependency graph construction;
- source parsing;
- CI log/artifact acquisition;
- MCP transport;
- authentication and secrets.

### Engine explicitly does not own

- semantic code review by an LLM;
- root-cause diagnosis;
- code generation or repair;
- worker selection / dispatch;
- Candidate acceptance;
- PR approval;
- merge authority;
- release or deployment;
- production claims.

This boundary is intentional: **intelligence is evidence, not authority**.

---

## Suggested development workflows

### PR opened or synchronized

```text
GitHub PR
   |
   v
revision
   |
   v
readiness
   |
   +----> stale/incomplete? -> fix evidence or rebind
   |
   v
review / agent reasoning
```

### Several agents working in parallel

```text
active PR snapshots
       |
       v
    overlap
       |
       +----> shared paths / Issue chain
                 |
                 v
            coordinate first
```

### CI turns red

```text
GitHub checks
     |
     v
     ci
     |
     v
    cfi
     |
     +---- NO_TERMINAL_FAILURE
     +---- EXPECTED_FAILURE_ONLY
     +---- INSUFFICIENT_EVIDENCE
     +---- UNEXPECTED_FAILURE_OBSERVED
                         |
                         v
                        eia
                         |
                  READY / BLOCKED /
                    NO_ACTION
```

A downstream diagnosis system may consume `EIA READY`, but it still needs its own execution authority.

### Change blast radius

```text
repo-specific graph builder
        |
        v
covered files + dependency edges
        |
        v
      impact
        |
        +---- direct impacted files
        +---- transitive impacted files
        +---- evidence completeness
```

---

## Reuse in another repository

The fastest adoption path is to add the GitHub Action workflow shown above.

For richer intelligence:

- use a custom collector to feed `overlap` across multiple PRs;
- generate a language-specific dependency graph and feed it to `impact`;
- expose the package through your own MCP/server adapter;
- use `ci -> cfi -> eia` as a deterministic evidence front-end before an LLM diagnosis service.

You do **not** copy the engine into each repository. All consumers should depend on the canonical package or immutable release tag.

---

## Release pinning

For CI and automation, prefer immutable version pinning:

```yaml
uses: James3014/repository-intelligence-engine@v0.1.0
```

For environments that require a commit-level pin, use the release commit associated with the tag.

The engine outputs exact revision identity and content hashes so downstream systems can additionally bind their own receipts or artifacts to the evidence they consumed.

---

## Development

Clone and run the test suite:

```bash
git clone https://github.com/James3014/repository-intelligence-engine.git
cd repository-intelligence-engine
python3 -m pytest -q
```

At `v0.1.0`, the consumer productization suite contains **40 passing tests**, covering:

- package importability and decoupling;
- all seven public operations;
- CLI behavior;
- GitHub Action acquisition and output;
- tamper / identity-substitution rejection;
- adapter-consumer compatibility;
- claim ceilings and authority exclusions.

A real cross-repository GitHub Actions canary was also completed against `James3014/Nexus-new` using `repository-intelligence-engine@v0.1.0`.

---

## Security and authority model

Repository Intelligence is intentionally narrow.

The GitHub Action requests only:

```yaml
permissions:
  contents: read
  pull-requests: read
  checks: read
```

The Action never checks out or executes PR code.

The engine and its adapters do not grant:

```text
approve
merge
release
publication
deployment
worker dispatch
Candidate acceptance
production truth
```

Claim ceilings are part of the public contract:

```text
PR intelligence      -> PR_INTELLIGENCE_ONLY
CI evidence          -> CI_EVIDENCE_ONLY
external automation  -> AUTOMATION_ADVISORY_ONLY
GitHub cloud bundle  -> ADVISORY_EVIDENCE_ONLY
```

A higher-level controller may use Repository Intelligence as evidence, but authority must be granted and verified elsewhere.

---

## Current status

`v0.1.0` has been validated as an independent consumer product:

- canonical engine / CLI / GitHub Action are hosted in this repository;
- seven native Repository Intelligence operations are available;
- Dev MCP can project all seven operations for GPT/Codex workflows;
- a real GitHub Actions cross-repository canary succeeded against `Nexus-new`;
- legacy reviewer code now consumes / forwards to the independent engine rather than owning duplicate intelligence implementations.

This supports the claim that Repository Intelligence is reusable across repositories as an advisory intelligence layer. It does **not** imply standalone merge, release, deployment, or production authority.

---

## Provenance

- Accepted V1.1 behavior baseline: `aab512ff738650cbffcbc44532b9d99f3787d138`
- Initial extracted engine source: `693ae7cf59e3b090ee873b7196ee330b30e26221`
- Consumer-productized release: `v0.1.0`
- Canonical release commit: `a8b9a00a6f3ea3e9ade0c6ef494d0fa88a2d73b2`
- Historical extraction / compatibility source: `James3014/nexus-opencli-reviewer`

Repository Intelligence should remain one canonical advisory engine with multiple adapters, not multiple copies of the same decision logic.
