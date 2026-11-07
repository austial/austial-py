---
name: code-reviewer
description: Review a change to the Austial framework for correctness, DI/scope/lifecycle invariants, public-API consistency, test quality and docs drift. Use before committing or opening a PR, or when asked to review a branch or pull request.
argument-hint: [base branch or PR number, default main]
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(git log *), Bash(git status *), Bash(gh pr diff *), Bash(uv run pytest *), Bash(uv run ruff *), Bash(uv run mypy *), Bash(uv run python scripts/*)
---

Review the changes against `$ARGUMENTS` (default: `main`). You review; you do not edit. Read `CLAUDE.md` first:
its "Architecture notes" and "Definition of done" are the standard.

## Procedure

1. **Get the diff.** `git diff <base>...HEAD` plus `git status` for uncommitted work (or `gh pr diff <n>`).
   List changed files by package. For a large diff, review package by package.
2. **Understand intent before judging.** Read the commit messages and the tests; state in one sentence what
   the change is meant to do. If the intent is unclear, say so as a finding.
3. **Read the surrounding code**, not just the hunks: callers, the code the change interacts with, and the
   existing tests for the area. Most real bugs live at the seam.
4. **Check, in order of importance:**
   1. *Correctness*: does the code do what the tests claim? Precedence/ordering (global -> controller ->
      route), off-by-one, falsy-but-valid values, swallowed exceptions, missing `await`, mutation of shared
      state, error paths that leave things half-done.
   2. *Framework invariants*: routes still build lazily after ASGI startup and nothing resolves providers at
      import/`create()` time; request scope bubbles (anything depending on a request-scoped provider or the
      `REQUEST` token is resolved per request, controllers and guards included); lifecycle hooks run once and
      in the right order, only hook-bearing providers built eagerly; the filter chain still ends in
      `AllExceptionsFilter`; constructor defaults keep their value unless the type is provided.
   3. *Public API*: new symbols exported from the package `__init__` and `austial/__init__.py` (+ `__all__`);
      names/semantics mirror NestJS unless the docstring says why not; breaking changes are explicit.
   4. *Tests*: every new branch and error path covered; bug fixes have a regression test that fails without
      the fix; assertions check behaviour not mocks; DI fixtures are module-level; no flaky timing.
   5. *Security*: user input reaching file paths, headers, regexes or SQL; secrets in logs/errors; unsafe
      defaults (e.g. trusting `X-Forwarded-For`, trusting declared `Content-Type`); new dependencies.
   6. *Docs*: a public change has a matching update in `../austial-py-doc/content`; run
      `uv run python scripts/check_docs_sync.py ../austial-py-doc/content`.
   7. *Typing/style*: public API fully typed; no bare `type: ignore`. Skip anything `ruff` already enforces.
5. **Verify before reporting.** For each suspected bug, read the exact code path and, when cheap, prove it with
   a throwaway failing test or a short `uv run python` snippet. Drop findings you cannot substantiate. Run
   `uv run ruff check .`, `uv run mypy packages integration` and `uv run pytest -q`; any failure is a finding.

## Output

Findings ordered by severity: **Blocker** (wrong behaviour, broken invariant, security, failing gate),
**Should fix**, **Nit** (only if worth a human's time). For each give `file:line`, what is wrong, a concrete
failing scenario (input -> actual vs expected), and the smallest fix. Say explicitly when a category had no
findings. Finish with one line: **ship**, **fix first**, or **needs discussion**. No praise, no padding.

For deeper multi-agent review use the built-in `/code-review`; this skill is the fast, project-specific pass.
