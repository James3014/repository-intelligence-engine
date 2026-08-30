# Semantic Review and Agent Boundary

Repository Intelligence is a deterministic advisory engine. It is not itself an LLM reviewer, coding agent, worker dispatcher, or merge authority.

This document defines the boundary between Repository Intelligence, the retained OpenCLI/ChatGPT semantic reviewer, and any future diagnosis or coding-agent automation.

## Current product boundary

The current architecture has three distinct layers:

```text
GitHub / local Git / CI / graph evidence
                  |
                  v
       Repository Intelligence
  revision / readiness / overlap / CI
       impact / CFI / EIA
                  |
                  | exact, hash-bound advisory evidence
                  v
        external consumers
          /       |        \
         /        |         \
        v         v          v
  GPT/ChatGPT   GPT/Codex   other systems
  semantic     via Dev MCP
  reviewer
        |
        v
 optional advisory publication
```

The separation is intentional:

- **Repository Intelligence answers what repository evidence says.**
- **Semantic review interprets code and evidence using an LLM.**
- **Diagnosis/coding agents investigate or modify code under a separate execution authority.**
- **Acceptance, approval, merge, release, and production claims stay outside all three unless separately authorized.**

## Repository Intelligence is not an agent

The canonical `repository_intelligence` package does not:

- invoke GPT, Claude, Gemini, Codex, OpenCode, or another model;
- select or dispatch a worker;
- inspect source semantically with an LLM;
- diagnose root cause;
- generate or modify code;
- comment on or approve a pull request;
- merge, release, deploy, or publish;
- grant Candidate acceptance or production authority.

It produces deterministic evidence and advisory decisions only.

The public claim ceilings remain:

```text
PR intelligence      -> PR_INTELLIGENCE_ONLY
CI evidence          -> CI_EVIDENCE_ONLY
external automation  -> AUTOMATION_ADVISORY_ONLY
GitHub cloud bundle  -> ADVISORY_EVIDENCE_ONLY
```

`EIA READY` means only that a downstream controller may consider a specific action from exact evidence. It does not dispatch anything.

## The OpenCLI/ChatGPT semantic reviewer still exists

Extraction of Repository Intelligence did **not** remove or replace the semantic reviewer.

The retained `nexus-opencli-reviewer` application contains a separate optional semantic-review surface:

```text
reviewer.scan
    |
    | deterministic eligibility / exact context
    v
reviewer.review_context
    |
    v
reviewer.opencli.OpenCLITransport
    |
    | opencli chatgpt ask ...
    v
ChatGPT
    |
    v
reviewer.semantic_response.v1
    |
    v
PRE_REVIEW_ONLY receipt
    |
    +--> optional idempotent advisory GitHub comment
```

The transport currently invokes ChatGPT through OpenCLI using an ephemeral site session. The semantic result is parser-validated and bound to exact review identity, prompt/context hashes, transport provenance, and durable attempt state.

The semantic reviewer may return statuses such as `PASS`, `FINDINGS`, or `BLOCKED`, with findings and evidence gaps. Its maximum claim remains `PRE_REVIEW_ONLY`.

It is an **LLM semantic reviewer**, not a coding worker. It does not itself edit code, produce a repair Candidate, merge, or release.

## Current unattended runtime

`nexus-opencli-reviewer` also contains an unattended local service. When enabled, it can:

1. poll configured repositories;
2. acquire current PR/CI evidence;
3. identify eligible exact PR identities;
4. invoke the OpenCLI/ChatGPT semantic reviewer at semantic concurrency `1`;
5. persist crash-safe semantic attempt and PRE_REVIEW evidence;
6. optionally publish one advisory GitHub comment after a fresh identity rebind.

The macOS `LaunchAgent` used to keep this service running is an operating-system background-service mechanism. It is not an AI agent.

## Dev MCP is another Repository Intelligence consumer

DevSpace exposes the seven Repository Intelligence operations as read-only native MCP tools:

```text
repository_intelligence_revision
repository_intelligence_readiness
repository_intelligence_overlap
repository_intelligence_ci
repository_intelligence_impact
repository_intelligence_cfi
repository_intelligence_eia
```

This allows GPT/Codex or another controller to acquire repository evidence and request deterministic RI decisions interactively.

Dev MCP exposure does not make RI a worker. A model using RI through Dev MCP is a consumer of evidence; any subsequent worker dispatch must happen through a separate governed dispatch path.

## Semantic reviewer vs diagnosis agent vs coding agent

These roles must remain distinct.

| Role | Primary question | May use an LLM? | May mutate code? | Current status |
|---|---|---:|---:|---|
| Repository Intelligence | What does the exact repository evidence say? | No | No | Implemented |
| Semantic reviewer | Is the proposed change semantically sound given bounded evidence? | Yes | No | Implemented through OpenCLI/ChatGPT |
| Diagnosis agent | Why did a bounded failure occur and what repair is supported? | Yes | No by default | Not yet a formal RI automation consumer |
| Coding/repair agent | Can a bounded repair Candidate be produced? | Yes | Yes, in an authorized workspace | Not yet dispatched by RI/EIA |
| Acceptance/verifier | Is the exact Candidate acceptable under its contract? | Possibly | No | Separate governance workflow |
| Merge/release authority | May this accepted change be integrated or released? | Not material | Yes | Explicitly outside RI |

## Current automation boundary

Today, the following is implemented:

```text
PR / CI evidence
      |
      v
Repository Intelligence
      |
      +--> deterministic advisory results
      |
      +--> GitHub Action artifact
      |
      +--> Dev MCP consumer
      |
      +--> retained OpenCLI semantic-review workflow
```

The following is **not yet implemented as a formal automatic RI pipeline**:

```text
CFI unexpected failure
      |
      v
EIA READY
      |
      v
automatic diagnosis-agent dispatch
      |
      v
automatic repair-agent dispatch
```

A future automation controller may consume EIA and semantic-review evidence, but it must preserve exact-head binding, replay/idempotency safety, provider/worker identity, write-scope fencing, verification, and separate merge authority.

## Intended direction

The intended next architectural step is to make the existing OpenCLI/ChatGPT reviewer a formal **Semantic Review Consumer** of canonical RI evidence, then add a separate **Agent Automation Controller** that decides when evidence warrants:

- no model call;
- semantic review only;
- read-only diagnosis;
- a bounded repair Candidate;
- or human/owner escalation.

That controller must remain outside the RI Core. RI should continue to produce deterministic evidence rather than gaining worker-dispatch or mutation authority.

The governing principle is:

> **Intelligence describes evidence. Semantic review interprets it. Agents act under separate authority. Acceptance and merge remain separate again.**
