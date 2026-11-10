# Security policy

## Supported versions

Security fixes go into the latest released version of every `austial*` distribution.

## Reporting a vulnerability

Please do **not** open a public issue for security problems.

Report privately through GitHub: **Security → Report a vulnerability** on
<https://github.com/austial/austial-py/security/advisories/new>.

Include the affected package and version, a description of the impact, and a minimal reproduction. You can expect
an acknowledgement within a few days and a fix or mitigation plan as soon as the report is confirmed. Reporters are
credited in the advisory unless they prefer otherwise.

In scope: the framework code in `packages/` (authentication, authorization, security helpers, request handling,
the CLI and its templates). Out of scope: vulnerabilities in third-party dependencies that are not triggered by
Austial's use of them (report those upstream).
