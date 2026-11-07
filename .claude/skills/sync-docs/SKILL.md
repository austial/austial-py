---
name: sync-docs
description: Check that every public symbol exported by austial is mentioned in the docs site, and find stale "not supported" claims. Use after changing the public API or before a release.
allowed-tools: Bash(uv run python scripts/*), Bash(grep *), Read, Grep, Glob
---

1. Run `uv run python scripts/check_docs_sync.py ../austial-py-doc/content`.
2. For each undocumented symbol it lists, decide where it belongs (usually an existing page; a new
   page only for a new concept), add a short accurate section with a real example, and re-run until
   it prints `N/N public symbols`.
3. Search the docs for stale claims about things that now exist:
   `grep -rniE "not (yet )?(implemented|supported)|no (request )?scope|doesn't support|isn't supported" ../austial-py-doc/content`
   and fix any that are no longer true. Pay attention to `content/index.mdx` ("What's not implemented"),
   `content/ai/reference.mdx` ("Known limits") and `content/ai/agents-md.mdx`.
4. Build the docs to catch MDX errors: `cd ../austial-py-doc && npm run build` (needs `npm ci` once).

Documentation examples must be runnable against the current API: check names and signatures in the
source rather than from memory.
