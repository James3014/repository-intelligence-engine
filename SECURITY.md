# Security Policy

Repository Intelligence Engine is designed to consume repository and CI evidence without granting approval, merge, release, deployment, or worker-dispatch authority.

## Supported versions

Security fixes are supported on the latest released `0.1.x` version and on the current `main` branch while the project remains in the `0.x` series.

## Reporting a vulnerability

Please do not publish exploit details, credentials, tokens, private repository data, or other sensitive material in a public GitHub Issue.

If GitHub private vulnerability reporting is available in the repository Security tab, use that channel. Otherwise, open a minimal public Issue requesting a private security contact channel and include no exploit details. The maintainer will move the discussion to a private channel before requesting reproduction material.

A useful private report includes:

- affected version, tag, or commit;
- the exact component or adapter involved;
- reproduction steps or a minimal proof of concept;
- the expected security or authority boundary;
- the observed behavior and impact;
- whether credentials, repository writes, code execution, or evidence substitution are involved.

## Security boundary

The GitHub Action is intended to be read-only and advisory. It acquires repository metadata, changed-file names, and CI status evidence without checking out or executing pull-request source.

Security-sensitive regressions include, among other things:

- executing untrusted pull-request source;
- requesting broader GitHub permissions than required;
- treating stale, incomplete, or substituted evidence as current;
- accepting tampered hash-bound reports;
- silently crossing the documented advisory claim ceiling;
- adding approval, merge, release, deployment, or worker-dispatch authority to the engine or its read-only adapters.

Security reports do not automatically prove a vulnerability or authorize a fix, release, or disclosure. Each report is reproduced and bounded to an exact affected revision before a public claim is made.
