<p align="center">
  <img src="https://raw.githubusercontent.com/austial/austial-py/main/assets/icon.svg" alt="Austial icon" width="56">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/austial/austial-py/main/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/austial/austial-py/main/assets/logo.svg">
    <img src="https://raw.githubusercontent.com/austial/austial-py/main/assets/logo.svg" alt="Austial" width="380">
  </picture>
</p>

<p align="center">
  <b>A NestJS-style, batteries-included web framework for Python, built on top of FastAPI.</b>
</p>

<p align="center">
  <a href="https://github.com/austial/austial-py/actions/workflows/ci.yml"><img src="https://github.com/austial/austial-py/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <a href="https://pypi.org/project/austial/"><img src="https://img.shields.io/pypi/v/austial?label=pypi" alt="PyPI version"></a>
  <a href="https://pypi.org/project/austial/"><img src="https://img.shields.io/pypi/dm/austial?label=downloads" alt="PyPI downloads"></a>
  <a href="https://github.com/austial/austial-py/tags"><img src="https://img.shields.io/github/v/tag/austial/austial-py?label=tag&sort=semver" alt="Latest tag"></a>
  <a href="https://github.com/austial/austial-py/commits/main"><img src="https://img.shields.io/github/last-commit/austial/austial-py" alt="Last commit"></a>
  <a href="https://github.com/austial/austial-py/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/built%20with-FastAPI-009688?logo=fastapi&logoColor=white" alt="Built with FastAPI"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/managed%20with-uv-DE5FE9" alt="Managed with uv"></a>
</p>

<p align="center">
  <a href="https://docs.austial.com"><b>Documentation</b></a> &middot;
  <a href="#austial-in-one-file">Example</a> &middot;
  <a href="https://github.com/austial/austial-py/discussions">Discussions</a> &middot;
  <a href="https://github.com/austial/austial-py/blob/main/CONTRIBUTING.md">Contributing</a>
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
with the CLI (see [Install](#install) below); that generated project is
the "hello world" app, kept separate from the framework's own source tree.

> **If you know NestJS, you already know Austial.** Modules, controllers, providers and constructor-based
> dependency injection, with the whole request lifecycle, on FastAPI and Pydantic. If it saves you from
> hand-rolling architecture, a star helps other Python developers find it.

## Austial in one file

```python
# main.py
from austial import AustialFactory, Body, Controller, Injectable, Module, Post
from pydantic import BaseModel


class CreateCatDto(BaseModel):
    name: str
    age: int


@Injectable()
class CatsService:
    def __init__(self) -> None:
        self.cats: list[dict] = []

    def create(self, dto: CreateCatDto) -> dict:
        self.cats.append({"id": len(self.cats) + 1, **dto.model_dump()})
        return self.cats[-1]


@Controller("cats")
class CatsController:
    def __init__(self, cats: CatsService) -> None:  # injected by type hint
        self.cats = cats

    @Post()
    async def create(self, dto: CreateCatDto = Body()) -> dict:
        return self.cats.create(dto)


@Module(controllers=[CatsController], providers=[CatsService])
class AppModule:
    pass


app = AustialFactory.create(AppModule, title="Cats")
```

```bash
pip install austial
uvicorn main:app --reload      # Swagger UI at http://localhost:8000/docs
```

A fuller version with a guard, validation and error handling is in
[`examples/hello-world`](https://github.com/austial/austial-py/blob/main/examples/hello-world/main.py).

## What you get

- **Architecture, not just routing:** `@Module`, `@Controller`, `@Injectable`, a DI container with singleton and
  transient scopes, and `Test.create_testing_module(...)` to override providers in tests.
- **The full request lifecycle:** guards, pipes, interceptors, exception filters and middleware, bindable per
  route or globally with `APP_GUARD` and friends.
- **Batteries included:** config, a TypeORM-shaped ORM with Alembic migrations, MongoDB, caching, scheduling,
  CQRS, events, WebSockets, GraphQL, OpenAPI, health checks, i18n, file storage and background jobs.
- **Microservices:** `@MessagePattern` / `@EventPattern` over TCP, Redis, NATS, Kafka, MQTT, RabbitMQ and gRPC,
  plus hybrid HTTP + broker apps.
- **Auth and security:** Argon2, JWT, TOTP, OAuth2 / OIDC, roles and permissions, security headers, rate
  limiting and CSRF.
- **A CLI like `nest`:** `austial new` and `austial generate resource|module|controller|guard|...` patch your
  app module for you.
- **Still FastAPI underneath:** your Pydantic models, ASGI middleware and deployment setup keep working.

## Install

```bash
pip install austial                  # the CLI and everything else
pip install 'austial[redis,kafka]'   # plus optional integrations
austial new my-app && cd my-app      # or scaffold a project like `nest new`
```

Full documentation: <https://docs.austial.com> &middot; Source: <https://github.com/austial/austial-py>
