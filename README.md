# Repository Intelligence Engine

`repository-intelligence-engine` is a pure, deterministic, transport-neutral
advisory engine for repository and pull-request evidence. It does not crawl a
repository by itself. Callers acquire facts, normalize them into the accepted
JSON contracts, and choose one of the engine operations.

Canonical Python package: `repository_intelligence`

## Operations and claim ceilings

| Operation | Purpose | Maximum claim |
|---|---|---|
| `revision` | Bind repository, PR, base/head, and current-main identity | `PR_INTELLIGENCE_ONLY` |
| `readiness` | Classify advisory PR readiness | `PR_INTELLIGENCE_ONLY` |
| `overlap` | Detect cross-PR path and issue overlap | `PR_INTELLIGENCE_ONLY` |
| `ci` | Fingerprint terminal CI failure evidence | `CI_EVIDENCE_ONLY` |
| `impact` | Analyze normalized dependency-graph blast radius | `PR_INTELLIGENCE_ONLY` |
| `cfi` | Classify CI Failure Intelligence evidence | `CI_EVIDENCE_ONLY` |
| `eia` | Decide whether external diagnosis may be considered | `AUTOMATION_ADVISORY_ONLY` |

No operation can comment, approve, merge, release, publish, dispatch a worker,
or execute pull-request source.

## GitHub Action

Any GitHub repository can run Repository Intelligence on pull requests without
copying engine code:

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

The action uses GitHub REST to acquire repository identity, PR number,
base/head SHA, current default-branch SHA, changed filenames, and check-run
evidence. It never invokes `actions/checkout`, reads PR blobs, or executes PR
code. Its hash-bound output includes revision, readiness, CFI, EIA, exact review
identity, and top-level `ADVISORY_EVIDENCE_ONLY`.

## CLI and Python package

```bash
python -m repository_intelligence.cli \
  --operation readiness \
  --input snapshot.json

python -m repository_intelligence.cli \
  --operation impact \
  --input impact.json
```

The CLI supports all seven operations and writes no network or persistent state.
Python consumers can import the same functions directly from
`repository_intelligence`.

## Architecture

```text
GitHub Action / Dev MCP / local Git / CI / custom adapter
                          |
                          v
                 normalized evidence
                          |
                          v
              repository_intelligence
                          |
                          v
                  advisory evidence
```

Acquisition and transport remain adapters. The canonical package owns only
contracts and deterministic advisory decisions, so every consumer reaches one
authority instead of reimplementing classifier, overlap, CI, CFI, or EIA logic.

## Provenance

- Accepted behavior baseline: `aab512ff738650cbffcbc44532b9d99f3787d138`
- Extraction acceptance and cleanup: `James3014/nexus-opencli-reviewer` PR #24
- Initial published engine source: `693ae7cf59e3b090ee873b7196ee330b30e26221`
- Package version: `0.1.0`
