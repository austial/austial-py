---
name: code-reviewer
description: Review a change to the Austial docs site (MDX content, navigation, theme CSS, React components) for technical accuracy against the framework, build safety, accessibility and design-system consistency. Use before committing or opening a PR that touches this repo.
argument-hint: [base branch or PR number, default master]
allowed-tools: Read, Grep, Glob, Bash(git diff *), Bash(git log *), Bash(git status *), Bash(npm run lint), Bash(npm run build), Bash(gh pr diff *)
---

Review the changes against `$ARGUMENTS` (default: `master`). You review; you do not edit.

1. Get the diff: `git diff <base>...HEAD` plus `git status` for uncommitted work (or `gh pr diff <n>`). List the
   changed files and group them: content (`content/**`), navigation (`_meta.js`), theme (`app/globals.css`),
   components, scripts/config.
2. For **content**, the biggest risk is being wrong, not being ugly:
   - Every code sample and API name/signature must match the framework source in `../austial-py`. Open the
     source and verify; do not trust memory. Flag any example that would not run.
   - Claims of "not supported / not implemented" or "supported" must be currently true. Check
     `content/index.mdx`, `content/ai/reference.mdx` and `content/ai/agents-md.mdx`, which duplicate such lists.
   - Cross-links resolve to real pages; headings anchor links still exist.
   - Tone: concrete and plain; no marketing claims or invented proof; no NestJS brand assets.
3. For **navigation**: a new `.mdx` has an entry in its folder's `_meta.js`; titles are consistent with
   neighbours; no orphan pages.
4. For **theme/components** apply the `design` skill's rules: tokens only (no raw hex outside the token
   definitions), both `:root` and `.dark` updated together, existing components reused, responsive at
   640/1024/1280 with no horizontal page scroll, visible `:focus-visible`, keyboard operable, icon buttons
   labelled, AA contrast, reduced-motion respected.
5. **Generated files** (`public/md`, `public/llms*.txt`, `public/AGENTS.md`, `public/setup-agents.sh`,
   `public/_pagefind`) must not be hand-edited or committed.
6. **Verify, don't speculate:** run `npm run lint` and `npm run build`; a build failure is always a finding.
   Confirm each finding by reading the code it points at before reporting it.

Report, most severe first: **Blocker** (wrong docs, broken build, broken a11y), **Should fix**, **Nit**
(only if worth a person's time). For each: `file:line`, what is wrong, the concrete consequence, and the
smallest fix. State plainly if a category had no findings. End with one line: ship / fix first / needs
discussion. Do not praise and do not pad.
