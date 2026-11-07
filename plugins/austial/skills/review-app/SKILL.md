---
name: review-app
description: Review an Austial app or a change to one against the framework's production checklist and its common mistakes, with evidence. Use before merging or releasing, or when the user asks to audit, harden or review an Austial project.
argument-hint: [path or branch, default: the current diff]
---

Review this Austial change or project: $ARGUMENTS (default: `git diff` against the main branch).

Load the `austial-framework` skill, then fetch https://docs.austial.com/ai/production and walk its sections in order. For each section report:
**applies / does not apply**, whether it is **satisfied** (cite `file:line`), and what is **missing**. Never mark something satisfied without evidence from the code.

## Always check

1. **Registration:** every new controller, provider and module is registered and reachable from `AppModule`.
2. **Guards:** every non-public route is covered by `AuthGuard` (and `RolesGuard` / `TenantGuard` where relevant); `@Public()` appears only where intended.
3. **Errors:** Austial exceptions only (no `HTTPException`, no hand-built error bodies, no broad `except Exception` that swallows failures).
4. **Data:** repositories only (no raw SQLAlchemy, no f-string SQL); `IsNull()`/`NotNull()` instead of `None` filters; tenant-scoped entities filtered by `tenant_id`
   on every read, update and delete; `insert()` for application-assigned keys.
5. **Schema:** changes come with an Alembic revision that was read and reversed; no `synchronize=True` outside local/test.
6. **Secrets and PII:** nothing hardcoded; `jwt_secret` and `signed_url_secret` are 32+ characters from the environment; PII goes through `PIIRedactor` before logs and audit.
7. **In-memory defaults:** list every component from the "not production-safe by default" table that this app still uses.
8. **Health and startup:** `OrmModule.for_root` imported once; health endpoint returns 503 when a dependency is down; global `ValidationPipe` and `AllExceptionsFilter` registered.
9. **Tests:** a test per new route, including 401/403/404/422 cases; no skipped tests hiding failures.

## Then run it

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src tests && uv run pytest -q
```

Report the real output. Findings go first, ordered by severity (blocker, should-fix, nit), each with the file, the problem, and the fix. Do not change code unless the user asks;
offer to fix the blockers.
