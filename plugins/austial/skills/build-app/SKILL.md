---
name: build-app
description: Build a complete application on the Austial framework from an idea, end to end: pin down the requirements, scaffold the project, generate the feature modules, wire the database, auth and other capabilities, write tests, and verify. Use when the user wants a new backend, API, service or app built with Austial, or says "build me an app/API/service" in an Austial context.
argument-hint: <what the app should do>
---

Build this with Austial: $ARGUMENTS

Load the `austial-framework` skill first (rules, import map, pitfalls). Work in this order and do not skip the verification at the end.

## 1. Pin down the requirements (ask only what you cannot decide)

Settle these, proposing a default for each instead of asking open questions. Ask the user at most once, and only about real forks.

| Decision | Default |
|---|---|
| Entities and their fields, relations | derive from the idea |
| Database | SQLite for local, PostgreSQL for deployment (`OrmModule.for_root(type_=...)`) |
| Auth | JWT via `austial.auth` if any route is private; otherwise none |
| Roles / permissions | `austial.authz` only if two or more roles exist |
| Multi-tenant | no, unless the idea says so (`austial.tenancy`) |
| Real-time, background work, events, external calls | only what the idea needs (see `add-feature`) |

Write the decisions as a short list and keep going; they also fill the **Project facts** block of `AGENTS.md`.

## 2. Scaffold

```bash
uv tool install austial            # or: pipx install austial / pip install austial
austial new <app-name>             # creates the project, installs dependencies, writes AGENTS.md
cd <app-name>
cp .env.example .env
```

Use the project's own `AGENTS.md` from here on (it is the same rule set as the framework skill). Fill in its **Project facts**.

## 3. Generate the features

One command per entity, never hand-write the boilerplate:

```bash
uv run austial g resource <name>   # module + controller + service + entity + DTOs, registered in app_module.py
```

Other schematics: `controller`, `service`, `guard`, `pipe`, `interceptor`, `filter`, `middleware`, `decorator`, `gateway` (WebSockets), `resolver`
(GraphQL), `command` (CLI), `listener` (events), `library`, `app`. Use `--dry-run` to preview.

Then, by hand, replace the generated placeholder `name` column and DTO fields with the real ones.

## 4. Wire the database

In `src/app_module.py`, once, import `OrmModule.for_root(...)` with every entity:

```python
OrmModule.for_root(type_="sqlite", url="sqlite+aiosqlite:///./app.db", entities=[Cat, Owner], synchronize=True)  # dev
```

It connects on startup and closes on shutdown; there is no manual `initialize()`. `synchronize=True` is for local development and tests only: for anything deployed,
generate an Alembic migration (`austial-migrate revision -m "..." --autogenerate`), read it, and apply it.

## 5. Add the capabilities the idea needs

Use the `add-feature` skill for each: auth and roles, tenancy, background jobs, scheduling, WebSockets, GraphQL, microservices, caching, events,
CQRS, OpenAPI docs, health checks, MongoDB, outbound HTTP. Add them one at a time and run the tests after each.

## 6. Tests (a test per route, including the denied cases)

```python
import pytest
from httpx import ASGITransport, AsyncClient
from austial.testing import Test


@pytest.mark.asyncio
async def test_create_and_list():
    module = await Test.create_testing_module(imports=[CatsModule]).compile()
    app = module.create_austial_application()
    await app.init()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/cats", json={"name": "Tom"})).status_code == 201
        assert [c["name"] for c in (await client.get("/cats")).json()] == ["Tom"]
```

Assert error bodies (404, 401, 403, 422), not only 200s. Files are named `*_spec.py` under `tests/`.

## 7. Verify, then run it for real

```bash
uv run ruff check . --fix && uv run ruff format .
uv run mypy src tests
uv run pytest -q
uv run austial start --port 8000        # then curl a few routes; /docs is FastAPI's UI
```

Do not report the app as done until all four checks pass and you have exercised at least one route against the running server. Finish with: what was
built, how to run it, the routes, and anything from the "not production-safe by default" table that still applies. Then offer the `review-app` skill.
