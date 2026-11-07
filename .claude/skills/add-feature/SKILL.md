---
name: add-feature
description: Add a framework feature the standard way, test-first, with exports and docs. Use when implementing a new decorator, provider type, pipe, interceptor or module behaviour (typically a NestJS parity gap).
disable-model-invocation: true
argument-hint: [feature description]
---

Implement: $ARGUMENTS

Follow this order. Do not skip steps; do not start step 3 before step 2 fails for the right reason.

1. **Scope it.** Name the NestJS equivalent (if any) and what it does. Find the existing code that
   owns the area (`packages/core` for DI/routing/lifecycle, `packages/common` for decorators, pipes,
   interceptors, filters, exceptions). Read it before designing. Prefer extending over adding a package.
   If the design has a real fork (public API shape, breaking change), ask the user once, briefly.
2. **Write failing tests first**, in the owning package's `test/` as `*_spec.py`. Cover the happy path,
   the error path, scope/ordering interactions, and one edge case per branch you add. Define DI test
   fixtures at module level (function-local classes lose their type hints under
   `from __future__ import annotations`). Run them and confirm they fail.
3. **Implement the smallest change** that passes. Match the surrounding conventions (typing, naming,
   docstring explains where Austial differs from Nest). No speculative options.
4. **Export it.** Package `__init__.py` and, if it's an everyday import, `packages/austial/src/austial/__init__.py`
   (+ `__all__`).
5. **Verify.** Run `/verify`. Fix everything it reports.
6. **Document.** Update `../austial-py-doc/content` in the same change: the relevant page, the sidebar
   `_meta.js` if you added a page, and the "what's not implemented" lists if you closed a gap. Then run
   `/sync-docs`.
7. **Summarise** what changed, what is untested or deliberately out of scope, and any behaviour change
   for existing users. Do not commit unless asked.
