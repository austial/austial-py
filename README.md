<p align="center">
  <img src="assets/icon.svg" alt="Austial icon" width="56">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo.svg">
    <img src="assets/logo.svg" alt="Austial" width="380">
  </picture>
</p>

<p align="center">
  <b>A NestJS-style, batteries-included web framework for Python, built on top of FastAPI.</b>
</p>

<p align="center">
  <a href="https://pypi.org/project/austial/"><img src="https://img.shields.io/pypi/v/austial?label=pypi" alt="PyPI version"></a>
  <a href="https://github.com/austial/austial-py/tags"><img src="https://img.shields.io/github/v/tag/austial/austial-py?label=tag&sort=semver" alt="Latest tag"></a>
  <a href="https://github.com/austial/austial-py/commits/main"><img src="https://img.shields.io/github/last-commit/austial/austial-py" alt="Last commit"></a>
  <a href="https://github.com/austial/austial-py/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/built%20with-FastAPI-009688?logo=fastapi&logoColor=white" alt="Built with FastAPI"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/managed%20with-uv-DE5FE9" alt="Managed with uv"></a>
</p>

# Austial

Austial gives Python the exact developer experience of [NestJS](https://nestjs.com/):
decorator-driven modules/controllers/providers, real constructor-based
dependency injection, the full request lifecycle (guards, pipes,
interceptors, exception filters, middleware), a config layer, a database
layer, Terminus-style health checks, a testing module -- and a CLI so you can
scaffold new projects and artifacts the same way `nest new`/`nest generate` do.

This repository (`austial-py`) is the **framework itself** -- an installable
library, no bundled sample app. To see it in action, scaffold a new project
with the CLI (see [Quickstart](#quickstart) below); that generated project is
the "hello world" app, kept separate from the framework's own source tree.

## Why

FastAPI is a fantastic ASGI toolkit, but it doesn't prescribe an application
architecture. Austial is opinionated on top of FastAPI the way Nest is
opinionated on top of Express/Fastify: modules own controllers and providers,
providers get dependency-injected by type, and the request pipeline
(guard → pipe → interceptor → handler → filter) is a first-class concept
instead of something you hand-roll with dependencies everywhere.

## Architecture at a glance

| NestJS | Austial |
|---|---|
| `@Module()` | `@Module(imports=, controllers=, providers=, exports=)` |
| `@Controller()` / `@Get()` etc. | `@Controller(prefix)` / `@Get/@Post/@Put/@Patch/@Delete/@Options/@Head` |
| `@Injectable()` | `@Injectable(scope=Scope.DEFAULT \| Scope.TRANSIENT)` |
| Constructor DI | Container resolves `__init__` type hints recursively, singleton by default |
| `NestFactory.create(AppModule)` | `AustialFactory.create(AppModule)` -> `AustialApplication` |
| `app.listen(3000)` | `await app.listen(8000)` |
| `CanActivate` / `@UseGuards` | `CanActivate` ABC + `ExecutionContext`, `@UseGuards(...)` |
| `NestInterceptor` / `@UseInterceptors` | `NestInterceptor` ABC (`intercept(context, call_next)`) + `@UseInterceptors(...)` |
| `PipeTransform` / `ValidationPipe` | `PipeTransform` ABC + `ValidationPipe` |
| `ExceptionFilter` / `@Catch` | `ExceptionFilter` ABC + `@Catch(...)`, default `AllExceptionsFilter` |
| `NestMiddleware`, `MiddlewareConsumer` | `NestMiddleware` ABC, `configure(consumer)` on modules |
| `ConfigModule.forRoot()` | `ConfigModule.for_root(env_file=".env")` / `ConfigService` |
| `TypeOrmModule.forRootAsync` | `DatabaseModule.for_root_async(use_factory=, inject=)` (SQLAlchemy async) |
| `@nestjs/terminus` | `austial.terminus.HealthCheckService` + `MemoryHealthIndicator`, `DatabaseHealthIndicator` |
| `@nestjs/testing` | `austial.testing.Test.create_testing_module(...).compile()` |
| `nest new` / `nest generate` | `austial new <name>` / `austial generate\|g module\|controller\|service\|resource <name>` |

### A note on file names

Nest names files with dots (`health.controller.ts`) because Node resolves
modules by explicit relative path strings. Python's `import a.b` instead
resolves `a` as a package and `b` as a submodule -- a literal file
`health.controller.py` isn't importable via a normal `import` statement. So
Austial uses underscore suffixes instead: `health_controller.py`,
`health_service.py`, `health_module.py`, `health_dto.py`. The directory
layout still mirrors Nest 1:1 -- one folder per feature under
`src/modules/`.

## Quickstart

Austial is published on PyPI -- install the CLI and scaffold a new project:

```bash
uv tool install austial                 # or: pipx install austial / pip install austial
austial new my-app                      # scaffold a new project
cd my-app
uv sync
cp .env.example .env
uv run austial serve                    # http://localhost:8000, auto-reload
```

`austial new` scaffolds a small health-check "hello world" app --
`GET /`, `GET /health`, `GET /health/protected`, `/docs` (Swagger UI) -- see
[Using the CLI](#using-the-cli) below for the full generator reference.

## Developing Austial itself

```bash
git clone https://github.com/austial/austial-py
cd austial-py
uv sync --all-extras
uv run pytest
```

## Linting, type-checking & pre-commit hooks

```bash
uv run ruff check .           # lint
uv run ruff format .          # format
uv run mypy austial tests     # type-check

uv run pre-commit install --hook-type pre-commit --hook-type pre-push
uv run pre-commit run --all-files   # run every hook once, on demand
```

Once installed, `git commit` runs formatting/linting/type-checks automatically,
and `git push` also runs the test suite -- mirroring a typical Nest project's
husky + lint-staged setup. Projects scaffolded with `austial new` get the same
`.pre-commit-config.yaml` out of the box.

## Using the CLI

`austial new` scaffolds a brand-new project exactly like `nest new`:

```bash
uv run austial new my-app
cd my-app
uv sync
cp .env.example .env
uv run austial serve
```

> New projects depend on the published `austial` package from PyPI by
> default. If you're developing the framework itself, point new projects at
> your local checkout instead with `--link`:
> `austial new my-app --link /path/to/austial-py` -- this adds an editable
> `[tool.uv.sources]` entry so `uv sync` resolves `austial` from your local
> checkout rather than PyPI.

`austial generate` (alias `austial g`) adds artifacts to an existing project,
patching `src/app_module.py`'s imports/`imports=[...]` array automatically --
just like `nest g`:

```bash
uv run austial generate module cats        # src/modules/cats/cats_module.py
uv run austial generate controller cats    # src/modules/cats/cats_controller.py
uv run austial generate service cats       # src/modules/cats/cats_service.py
uv run austial generate resource cats      # module + full CRUD controller/service/dto/entity
uv run austial g resource cats             # same as above, short alias
```

## Repository layout

```
austial-py/
├── pyproject.toml          # package "austial", console-script entry point
├── LICENSE                  # MIT
├── assets/                   # logo.svg (+ logo-dark.svg for dark mode) / icon.svg / apple-icon.png
├── austial/                 # the framework (installable library) -- this *is* the package
│   ├── common/               # decorators, guards, interceptors, pipes, filters,
│   │                         # middleware, exceptions, logger
│   ├── core/                  # metadata/reflector, DI container, router builder,
│   │                         # AustialFactory / AustialApplication
│   ├── config/                 # ConfigModule / ConfigService
│   ├── database/                # DatabaseModule (SQLAlchemy async)
│   ├── terminus/                 # HealthCheckService + health indicators
│   ├── testing/                   # Test.create_testing_module(...)
│   └── cli/                        # `austial new` / `generate` / `serve` + templates
└── tests/                    # tests for the framework itself -- no sample app needed;
    ├── unit/                   # test modules/controllers are defined inline per test file
    └── e2e/
```

There's deliberately no `src/` here -- that's what `austial new` generates for
*your* project, kept out of the framework's own repo. Test files use Nest's
`*.spec.ts` naming convention (`*_spec.py` here); `pyproject.toml`'s
`[tool.pytest.ini_options]` is configured to discover them.

## Request lifecycle

Every route runs through the same pipeline Nest uses:

```
guards -> pipes -> interceptors (wrapping) -> handler -> exception filters
```

```python
from austial import Controller, Get, UseGuards, UseInterceptors
from austial.common.interceptors import TransformInterceptor

from .api_key_guard import ApiKeyGuard


@Controller("cats")
class CatsController:
    @Get(":id")
    @UseGuards(ApiKeyGuard)
    @UseInterceptors(TransformInterceptor())
    async def find_one(self, id: int):
        ...
```

Note path params use Nest's `:id` syntax (translated to FastAPI's `{id}`
under the hood), so route strings read exactly like their Nest counterparts.

## License

[MIT](./LICENSE)
