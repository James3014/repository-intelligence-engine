# Repository Intelligence Dogfooding Corpus

This directory is the bounded Wave C evidence registry for Repository Intelligence dogfooding.

Its purpose is to move the project from **compatibility proof** (the engine can run across repositories) toward **value proof** (specific failure families have been observed or reproduced and can be preserved without overstating what the evidence proves).

The corpus is observational. Its maximum claim is:

```text
OBSERVATIONAL_EVIDENCE_ONLY
```

It is not a second Repository Intelligence implementation and it does not grant approval, Candidate acceptance, worker dispatch, merge, release, deployment, or production authority.

## Evidence admission classes

Every case must use exactly one class:

- `LIVE_FLEET_DOGFOOD` — the evidence came from a real PR in the eight-repository fleet and is bound to an exact repository / PR / head. This can be a failure witness or a positive operating witness.
- `CONTROLLED_REPRODUCTION` — a source-bound controlled reproduction proves that a failure mechanism is reachable. It must not be described as fleet incidence.
- `SOURCE_FORENSICS` — source/API-contract investigation identifies a concrete defect mechanism or Candidate repair. It must not be described as a live fleet incident or accepted repair unless separate evidence proves that.

These classes are deliberately not ordered as quality scores. They answer different questions.

## Retention contract

A case retains, when the evidence supports them:

- repository and PR number;
- exact head SHA and base/current-main identity;
- failure-family ID or positive-witness classification;
- evidence class and case status;
- stable GitHub evidence references;
- RIE workflow run, artifact ID/digest, bundle content hash, and report fields when physically observed;
- observation time;
- one bounded supported claim;
- explicit non-claims.

When a physically inspected terminal bundle exists, the same case may also retain a `terminal_observation` object containing the exact action ref, expected head, terminal semantics, run/artifact identity, artifact digest, bundle content hash, observed external-check count, and advisory result fields. Terminal fields are optional because missing evidence stays missing; when present, the validator binds them back to the case head and fails closed on authority escalation or malformed hashes.

Missing evidence stays missing. Do not fabricate a run ID, artifact digest, source SHA, occurrence rate, or external-adoption claim merely to make the matrix look complete.

## Failure families

`corpus.v1.json` currently tracks:

- `STALE_BASE`
- `COMMIT_STATUS_CHANNEL_OMISSION`
- `COMMIT_STATUS_HEAD_BINDING`
- `EVIDENCE_INCOMPLETE`
- `UNEXPECTED_TERMINAL_CI_FAILURE`

A family may exist before a live fleet witness exists. That is intentional: the matrix can show what remains unobserved instead of turning absence of evidence into a pass.

## Case status semantics

- `OPEN` — the evidence identifies a still-open source/Candidate or unresolved failure subject.
- `FIXED` — the exact recorded subject was repaired or operationally requalified. This does not imply fleet-wide eradication.
- `OBSERVED` — a failure was observed but this corpus does not claim a repair.
- `POSITIVE` — a bounded operating witness succeeded under its stated advisory ceiling.

## Validation

Run:

```bash
python3 scripts/validate_dogfooding_corpus.py
```

The validator is stdlib-only and fails closed on malformed evidence classes, identities, case/family references, fleet coverage, or claim ceilings.

Focused tests:

```bash
python3 -m pytest -q tests/test_dogfooding_corpus.py
```

## Candidate extraction from RIE artifacts

The validator can inspect an already-downloaded root `repository-intelligence.json` snapshot bundle or `repository-intelligence-terminal.json` terminal bundle without mutating either the corpus or GitHub:

```bash
python3 scripts/validate_dogfooding_corpus.py \
  --extract-report /path/to/repository-intelligence.json
```

It emits candidate observations only for report-visible families currently supported by the extractor. Terminal bundles are unwrapped only after their advisory ceiling, terminal semantics, and outer/inner review identity agree; extracted terminal candidates are marked `TERMINAL_OBSERVED_CHECK_SET`:

- `STALE_BASE`
- `EVIDENCE_INCOMPLETE`
- `UNEXPECTED_TERMINAL_CI_FAILURE`

The output is a candidate for human/controller evidence admission, not an automatic corpus write. Evidence class, GitHub provenance, observation time, supported claim, and non-claims must still be established before a durable case is admitted.

## Important timing boundary

Repository Intelligence now has two deliberately distinct GitHub Action surfaces:

- the root Action is a **PR-event snapshot** and can legitimately report `COMPLETE / NO_TERMINAL_FAILURE` while later repository CI is still running;
- `terminal/` performs a bounded **terminal observed-check** pass for one exact PR head, excluding its own run and waiting until the observed external check/status set is non-empty, terminal, and stable for the configured quiescence window.

Therefore:

```text
successful PR-event snapshot
!= terminal observed-check evidence

terminal observed-check evidence
!= proof of repository required-check completeness
!= Candidate acceptance
!= merge readiness
```

The corpus must preserve which surface produced each observation instead of silently upgrading snapshot evidence into terminal evidence. Neither surface is a required merge gate.

## Updating the corpus

When a new real case appears:

1. preserve the exact PR/head evidence before interpreting it;
2. verify the RIE artifact when one exists;
3. classify it as live dogfood, controlled reproduction, or source forensics;
4. add or reuse one narrowly defined failure family;
5. state the smallest supported claim and explicit non-claims;
6. run the validator and focused tests;
7. update `fleet-matrix.md` only when the machine-readable corpus changes.

Do not convert a fixture into a live witness, or a source Candidate into an accepted repair, by changing prose alone.
