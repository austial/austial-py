---
name: austial-framework
description: Ground rules and API map for the Austial framework (a NestJS-style Python framework on FastAPI, imported as `austial`). Use whenever a project imports `austial`, has `src/app/app_module.py` (or the older `src/app_module.py`), or the user mentions Austial, `austial g`, `@Module`/`@Controller`/`@Injectable` in Python, or asks to build a Python backend with it. Load before writing any Austial code: Austial is not FastAPI, Django or NestJS, and code guessed from them does not run.
---

# Austial: how to work in an Austial project

Austial looks like NestJS and FastAPI but behaves like neither. **Read [AGENTS.md](AGENTS.md) in this folder before writing code.** It holds the
mental model, the do/don't list, the full import map (which symbol comes from which `austial.*` module), and what is not production-safe by default.

When something is not in that import map, or you are unsure of a signature, do not guess. Fetch the docs:

- Page index: https://docs.austial.com/llms.txt
- Everything in one file: https://docs.austial.com/llms-full.txt
- Production checklist: https://docs.austial.com/ai/production

## The five rules that prevent most mistakes

1. **Register everything.** Controller in a module's `controllers=[...]`, provider in `providers=[...]`, module reachable from `AppModule.imports`.
   A missing registration shows up as a missing route or a DI error, not an import error.
2. **Inject through `__init__` type hints**; never call `Service()` yourself. Repositories: `repo: Repository[Cat] = InjectRepository(Cat)` with
   `OrmModule.for_feature([Cat])` in the module and one `OrmModule.for_root(...)` at the root (it connects and closes the database itself).
3. **Request data uses marker defaults** (`Body()`, `Param()`, `Query()`, `Headers()`); route paths use `:id`, not `{id}`; DTOs are pydantic models.
4. **Raise Austial exceptions** (`NotFoundException`, ...), never `HTTPException` or hand-built error bodies.
5. **Guards are the security boundary.** Every non-public route needs `AuthGuard` (plus `RolesGuard`/`TenantGuard` where relevant); open routes are
   marked `@Public()`.

## Packages and extras

`pip install austial` installs everything below; import paths are always `austial.<module>`. Optional libraries are extras:
`austial[redis|nats|kafka|mqtt|rabbitmq|grpc|grpc-proto]` (microservices), `austial[socketio]`, `austial[strawberry]` (GraphQL), `austial[pymongo]`,
`austial[lambda]`. `austial add <extra>` runs the right `uv add`.

## Definition of done

`ruff check`, `ruff format --check`, `mypy src tests` and `pytest -q` all pass, and you ran them and read the output. Never report work as finished without that.

## Workflows

- Building a whole app from an idea: the `build-app` skill.
- Adding one capability (auth, tenancy, jobs, WebSockets, GraphQL, microservices, schedule, CQRS, cache, Mongo, ...): the `add-feature` skill.
- Checking a change before merge or release: the `review-app` skill.
