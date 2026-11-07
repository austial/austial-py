# Working on Austial with Claude Code

How this repo is set up for Claude Code, how to turn on the GitHub automation, and which open-source
plugins and skills are worth adding. The recommendations were checked against each project's own
repository on 2026-11-07; things I could not verify are marked **(unverified)**.

## What is already in the repo

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Commands, layout, the architecture rules that cause bugs when forgotten, and the definition of done. Loaded every session. |
| `.claude/settings.json` | Shared permissions (allow the dev loop; ask before `git push`/`tag`/`commit`; deny force-push, `rm -rf`, `.env`, `uv.lock`) and a **PostToolUse hook** that formats and lints every Python file Claude edits. |
| `.claude/hooks/format-python.sh` | The hook: `ruff format` + `ruff check --fix`; unfixable errors go back to Claude (exit 2). |
| `.claude/skills/verify` | `/verify`: the CI gate (ruff, format check, mypy, pytest + coverage) with honest reporting. |
| `.claude/skills/add-feature` | `/add-feature <desc>`: scope, failing tests first, minimal change, exports, docs, verify. Manual only. |
| `.claude/skills/sync-docs` | `/sync-docs`: public API vs docs, stale "not supported" claims, docs build. |
| `.claude/skills/release` | `/release <version>`: preconditions, notes, annotated tag. Manual only; confirms before pushing the tag. |
| `.claude/skills/code-reviewer` | `/code-reviewer [base]`: fast project-specific review of a diff (correctness, DI/scope/lifecycle invariants, API, tests, security, docs drift); verifies each finding before reporting. |
| `.claude/agents/framework-reviewer` | Read-only reviewer that knows the framework invariants. |
| `.claude/agents/test-author` | Writes edge-case tests from the coverage report; reports bugs instead of bending tests. |
| `scripts/check_docs_sync.py` | Fails if an exported symbol is not mentioned in `austial-py-doc`. |
| `.github/workflows/ci.yml` | lint, format, mypy, tests on Python 3.11-3.14 with a coverage floor, build of all 6 packages, advisory docs-sync. |
| `.github/workflows/claude.yml` | `@claude` in issues/PRs. |
| `.github/workflows/claude-review.yml` | Automatic review of non-draft, same-repo PRs. Advisory: CI is the merge gate. |
| `.github/dependabot.yml`, PR/issue templates | Weekly dependency + Actions updates; a checklist that matches the definition of done. |

Releases stay as they were: push a `vX.Y.Z` tag and `publish.yml` does the rest (versions come from git tags).

## One-time setup for the GitHub automation

1. Install the Claude GitHub App on the repo: run `/install-github-app` in Claude Code, or follow the action's setup guide (`docs/setup.md` in `anthropics/claude-code-action`).
2. Add the repository secret `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`, then change the input name in both Claude workflows).
3. Branch protection on `main`: require the `CI` checks (`Lint & format`, `Type-check`, every `Test`, `Build all distributions`), require a PR, and do **not** make the Claude review a required check.
4. Check that `austial/austial-py-doc` is the right repository for the `docs-sync` job in `ci.yml`.
5. Pin third-party actions to commit SHAs once you are happy with them; Dependabot will keep the pins current.

The review workflow skips fork PRs on purpose: they have no secrets, and running an LLM over untrusted
diffs with a write-scoped token is a prompt-injection risk.

## Recommended plugins and skills

Plugins run code and prompts with your permissions. **Read a plugin before installing it** and pin or
review updates; Anthropic's own directory says it cannot verify what third-party plugins contain.

### Adopt now (official, low risk)

| Plugin | Why it fits | Install |
|---|---|---|
| `pr-review-toolkit` (MIT) | Six review agents. The useful ones here: **pr-test-analyzer** (behavioural, not line, coverage), **silent-failure-hunter** (our lifecycle/filter code swallows errors by design in places), **type-design-analyzer**, **code-reviewer** (applies `CLAUDE.md`). | `/plugin install pr-review-toolkit@claude-plugins-official` |
| `code-review` | Multi-agent PR review with confidence scoring; complements the GitHub workflow for local use. | `/plugin install code-review@claude-plugins-official` |
| `hookify` | Turn "stop doing X" into a project rule (`.claude/*.local.md`) without editing hooks JSON. | `/plugin install hookify@claude-plugins-official` |
| `context7` (Upstash, external) | Current FastAPI / Starlette / pydantic docs instead of stale training data; we build directly on their internals. Works without a key (shared anonymous limits). Queries go to Context7's hosted server; its licence was not stated on the plugin page **(unverified)**. | `/plugin install context7@claude-plugins-official` |
| `pyright-lsp` | Type intelligence in the editor loop. Needs `pipx install pyright`. Advisory only: **mypy remains the gate**. Licence not stated on the plugin page **(unverified)**. | `/plugin install pyright-lsp@claude-plugins-official` |

Also listed in the same directory, names verified but behaviour **not** reviewed by me: `feature-dev`,
`commit-commands`, `security-guidance`, `claude-md-management`, `claude-code-setup`, `code-simplifier`,
`plugin-dev`, `skill-creator`. Look at each plugin's README before adopting.

### Adopt selectively (community, high value, check the licence)

| Project | Take | Caveat |
|---|---|---|
| [trailofbits/skills](https://github.com/trailofbits/skills) | `modern-python` (uv + ruff + pytest, matches our toolchain), `property-based-testing` (Hypothesis: ideal for pipes, version matching, serializer, mapped types), `static-analysis` (Semgrep/CodeQL), `differential-review`, `supply-chain-risk-auditor` (we publish 6 PyPI packages). | **CC-BY-SA-4.0.** Install as a marketplace plugin; do not copy their text into this repo, or ShareAlike applies to it. |
| [obra/superpowers](https://github.com/obra/superpowers) (MIT) | `test-driven-development`, `systematic-debugging`, `verification-before-completion`, `writing-plans`. Very widely used. | Enforces a heavy design -> plan -> execute process and can burn tokens on small changes. Overlaps the `tdd`/`diagnosing-bugs` skills you already have from `mattpocock-skills`: use one set, not both, or triggers conflict. |
| [anthropics/claude-code-security-review](https://github.com/anthropics/claude-code-security-review) (MIT) | Security-focused PR review Action. | **Not hardened against prompt injection**: trusted, same-repo PRs only, and enable "Require approval for all external contributors". Our `claude-review.yml` already covers general review; add this only if you want a dedicated security pass. |

Already available in your sessions, no install needed: `/code-review`, `/simplify`, `/security-review`,
and from your installed skills `mattpocock-skills:tdd`, `:code-review`, `:diagnosing-bugs`,
`:domain-modeling`, and `andrej-karpathy-skills:karpathy-guidelines`.

### Not recommended for this repo

- Anything that vendors broad "100+ skills" bundles or awesome-list dumps: discovery lists are
  useful, but unreviewed bundles add prompt surface and noise. Treat lists such as
  `ComposioHQ/awesome-claude-plugins` as places to *look*, then vet each entry.
- Overlapping review plugins stacked together: pick `pr-review-toolkit` or `code-review` locally plus
  the one GitHub workflow, not five reviewers.

### Suggested rollout

1. Merge this setup; add the secret; protect `main`.
2. Install `pr-review-toolkit`, `code-review`, `context7` and run a review on the next real PR.
3. Add Trail of Bits `modern-python` + `property-based-testing`; write the first Hypothesis tests for
   `ParseIntPipe`/`format_sse`/version matching.
4. After a month, look at what the reviewers actually caught and what they only nagged about; turn the
   recurring nags into `hookify` rules or `CLAUDE.md` lines and drop reviewers that add noise.

## Sources

- Claude Code GitHub Action: https://github.com/anthropics/claude-code-action (inputs, `@v1`, secrets)
- Skills frontmatter and locations: https://code.claude.com/docs/en/skills
- Hooks schema, events and exit codes: https://code.claude.com/docs/en/hooks
- Official plugin directory: https://github.com/anthropics/claude-plugins-official
- Superpowers: https://github.com/obra/superpowers
- Trail of Bits skills: https://github.com/trailofbits/skills
- Security review Action: https://github.com/anthropics/claude-code-security-review
- Anthropic skills: https://github.com/anthropics/skills
