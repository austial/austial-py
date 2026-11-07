# Austial (framework repo)

A NestJS-style, batteries-included web framework for Python on FastAPI. This repo is the **framework**
(a uv workspace of 19 independently published packages under `packages/`). It has no sample app: the
generated project from `austial new` plays that role. The documentation site is a **separate repo**,
`../austial-py-doc` (Next.js + Nextra, MDX under `content/`).

## Commands

```bash
uv sync --all-packages --group dev        # install everything
uv run pytest -q                          # all tests (packages/*/test + integration)
uv run pytest packages/core/test -q -k lifecycle
uv run pytest --cov --cov-report=term-missing   # coverage (fail_under in pyproject.toml)
uv run ruff check . && uv run ruff format --check .
uv run mypy packages integration          # must be clean
uv run python scripts/check_docs_sync.py ../austial-py-doc/content   # public API vs docs
```

Run `/verify` (the project skill) before saying work is done: it runs lint, format, mypy and the tests.
Run `/code-reviewer` on your own diff before committing or opening a PR.

## Layout and where things go

| Package | Owns |
|---|---|
| `packages/core` | DI `Container`, module scanner, `RouterBuilder`, `AustialApplication`, lifecycle, request context, `ModuleRef` |
| `packages/common` | Decorators, pipes, guards, interceptors, filters, exceptions, `StreamableFile`, serializer, mapped types |
| `packages/austial` | The umbrella `austial` package: re-exports the everyday symbols and owns the CLI entry point |
| `packages/{orm,config,terminus,testing,cli,auth,authz,tenancy,security,audit,jobs,storage,i18n,migrations,cache,events}` | One feature each; `austial.<name>` via a pkgutil namespace shim |

- A new **public** symbol is exported from its package `__init__.py` **and** from
  `packages/austial/src/austial/__init__.py` (+ `__all__`) when it is an everyday import.
- Tests live in the package's own `test/` dir and are named `*_spec.py` (mirrors Nest's `*.spec.ts`);
  cross-package end-to-end tests go in `integration/`.
- Files use underscore suffixes (`cats_controller.py`), never dots.

## Architecture notes that cause bugs if you forget them

- **One application-wide container.** Module `exports` are not enforced as visibility.
- **Routes build lazily**, on the first non-lifespan ASGI scope (or `await app.init()`), *after* the ASGI
  startup handlers. Never resolve providers eagerly at import/`create()` time: a repository over a
  not-yet-initialised `DataSource` would crash.
- **Request pipeline:** guards -> pipes -> interceptors (wrapping) -> handler -> exception filters. The
  default `AllExceptionsFilter` always closes the filter chain.
- **Scope bubbles up:** anything depending on a `Scope.REQUEST` provider (or the `REQUEST` token) is
  itself resolved per request, including controllers and guards. Check with `Container.is_request_bound`.
- **Lifecycle hooks are found by method name**, run from the ASGI lifespan and from `init()`/`close()`.
  Only providers that define a hook are built eagerly.
- Constructor params *with defaults* are injected only when their type is provided (`retries: int = 3`
  keeps `3`). Annotations are read with `typing.get_type_hints`; classes defined inside a function with
  `from __future__ import annotations` can't be resolved, so define DI test fixtures at module level.
- **Async factory providers** are awaited by `Container.init_async_providers()` (called from `init()`, the ASGI
  lifespan, `create_application_context()` and `compile()`); sync `resolve()` of one that hasn't run raises.
- **`APP_GUARD`/`APP_PIPE`/`APP_INTERCEPTOR`/`APP_FILTER`** providers are filed under unique tokens by
  `Container.register` and picked up by `RouterBuilder`; the filter chain always ends in `AllExceptionsFilter`.
- Builtin types are never auto-built by the container, and `X | None` hints are unwrapped.
- Param helpers (`Param`, `Query`, ...) are **default values**, not decorators. Values that must be read
  after guards ran are `DeferredParam`s.

## Conventions

- Python >= 3.11, ruff line length 120, `ruff format`. Public API is fully typed; mypy must pass.
- Mirror NestJS naming and semantics unless Python makes it impossible; say so in the docstring when it
  differs.
- Every behavior change gets a test first (red), then the fix. Bugs get a regression test.
- Prefer extending an existing module over adding a new package.

## Definition of done

1. Tests added/updated and green; `/verify` passes; coverage did not drop; `/code-reviewer` has no Blockers.
2. Public API change -> docs updated in `../austial-py-doc` (same change, linked PR) and
   `scripts/check_docs_sync.py` is clean.
3. Conventional, imperative commit messages. Never commit or push without being asked; never push to
   `main`, never force-push, never create release tags (that is `/release`, user-invoked).
4. Do not hand-edit `uv.lock` or `dist/`.
