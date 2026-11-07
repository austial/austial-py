"""Stateful features, live: real server + real Mongo/Redis (docker-compose.brokers.yml), real timers, real sockets.

Needs the AUSTIAL_TEST_* variables of ``integration/env.sh`` (skipped otherwise)."""

import asyncio
import os
import uuid
from dataclasses import dataclass

import httpx
import pytest
from pydantic import BaseModel

from austial import AustialFactory, Controller, Get, Injectable, Module, Post, Scope
from austial.cache import CacheModule, CacheService
from austial.config import ConfigModule, ConfigService
from austial.cqrs import CommandBus, CommandHandler, CqrsModule, EventBus, EventsHandler, QueryBus, QueryHandler
from austial.events import EventEmitter, EventEmitterModule, OnEvent
from austial.http import HttpModule, HttpService
from austial.microservices import ClientOptions, ClientProxy, MessagePattern, MicroserviceOptions, Payload, Transport
from austial.mongo import Document, InjectClient, InjectModel, Model, MongoModule, Schema
from austial.schedule import Interval, ScheduleModule
from austial.terminus import (
    DiskHealthIndicator,
    HealthCheckService,
    HttpHealthIndicator,
    MongoHealthIndicator,
    TcpHealthIndicator,
)
from integration.live import free_port, serve, wait_until


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set (see integration/env.sh)")
    return value


# -- Mongo models + health checks + config, through HTTP ---------------------------------------


async def test_mongo_models_health_checks_and_config_through_http(tmp_path) -> None:
    mongo_url, redis_url = env("AUSTIAL_TEST_MONGO_URL"), env("AUSTIAL_TEST_REDIS_URL")
    redis_port = int(redis_url.rsplit(":", 1)[1])
    collection = f"live_{uuid.uuid4().hex[:8]}"
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=live-test\nPORT=8123\n")

    class Settings(BaseModel):
        APP_NAME: str
        PORT: int

    @Schema(collection=collection)
    class Pet(Document):
        name: str

    @Controller("pets")
    class Pets:
        def __init__(self, pets: Model[Pet] = InjectModel(Pet), config: ConfigService = None):  # type: ignore[assignment]
            self.pets, self.config = pets, config

        @Post()
        async def add(self, body: dict):
            return (await self.pets.create(body)).model_dump()

        @Get()
        async def all(self):
            return [p.model_dump() for p in await self.pets.find()]

        @Get("config")
        def cfg(self):
            return {"name": self.config.get("APP_NAME"), "port": self.config.get("PORT")}

    @Controller("health")
    class Health:
        def __init__(
            self,
            checks: HealthCheckService,
            mongo_check: MongoHealthIndicator,
            tcp: TcpHealthIndicator,
            disk: DiskHealthIndicator,
            http: HttpHealthIndicator,
            client=InjectClient(),
        ):
            self.checks, self.mongo, self.tcp, self.disk, self.http, self.client = (
                checks,
                mongo_check,
                tcp,
                disk,
                http,
                client,
            )

        @Get()
        async def check(self):
            return await self.checks.check(
                [
                    lambda: self.mongo.ping_check("mongo", self.client),
                    lambda: self.tcp.ping_check("redis", "127.0.0.1", redis_port),
                    lambda: self.disk.check_storage("disk", path="/", threshold_percent=0.999),
                ]
            )

        @Get("down")
        async def down(self):
            return await self.checks.check(
                [lambda: self.tcp.ping_check("nothing", "127.0.0.1", free_port(), timeout=0.3)]
            )

    @Module(
        imports=[
            ConfigModule.for_root(str(env_file), validation_schema=Settings),
            MongoModule.for_root(uri=mongo_url, database="austial_live"),
            MongoModule.for_feature([Pet]),
        ],
        controllers=[Pets, Health],
        providers=[
            HealthCheckService,
            MongoHealthIndicator,
            TcpHealthIndicator,
            DiskHealthIndicator,
            HttpHealthIndicator,
        ],
    )
    class App:
        pass

    async with serve(AustialFactory.create(App)) as base, httpx.AsyncClient(base_url=base) as c:
        created = await c.post("/pets", json={"name": "rex"})
        assert created.json()["name"] == "rex" and created.json()["id"]
        assert [p["name"] for p in (await c.get("/pets")).json()] == ["rex"]
        assert (await c.get("/pets/config")).json() == {"name": "live-test", "port": 8123}
        health = (await c.get("/health")).json()
        assert health["status"] == "ok" and {"mongo", "redis", "disk"} <= set(health["info"])
        down = await c.get("/health/down")
        assert down.status_code == 503 and down.json()["status"] == "error"  # a dead port really fails the check


# -- scheduling, CQRS, events, cache, HttpModule, request scope --------------------------------


@dataclass
class Adopt:
    name: str


@dataclass
class Count:
    pass


@dataclass
class Adopted:
    name: str


async def test_schedule_cqrs_events_cache_http_and_request_scope_live() -> None:
    ticks: list[int] = []
    adopted: list[str] = []
    heard: list[str] = []
    store: list[str] = []
    instances: list[int] = []

    @Injectable()
    class Jobs:
        @Interval(0.1)
        def tick(self):
            ticks.append(1)

    @CommandHandler(Adopt)
    @Injectable()
    class AdoptHandler:
        def __init__(self, events: EventBus):
            self.events = events

        async def execute(self, command: Adopt) -> str:
            store.append(command.name)
            await self.events.publish(Adopted(command.name))
            return command.name

    @QueryHandler(Count)
    @Injectable()
    class CountHandler:
        async def execute(self, query: Count) -> int:
            return len(store)

    @EventsHandler(Adopted)
    @Injectable()
    class OnAdopted:
        async def handle(self, event: Adopted) -> None:
            adopted.append(event.name)

    @Injectable()
    class Listener:
        @OnEvent("pet.*")
        def on_pet(self, payload):
            heard.append(payload)

    @Injectable(scope=Scope.REQUEST)
    class PerRequest:
        def __init__(self) -> None:
            instances.append(1)
            self.id = len(instances)

    @Controller("live")
    class Live:
        def __init__(
            self,
            commands: CommandBus,
            queries: QueryBus,
            emitter: EventEmitter,
            cache: CacheService,
            http: HttpService,
            scoped: PerRequest,
        ):
            self.commands, self.queries, self.emitter, self.cache, self.http, self.scoped = (
                commands,
                queries,
                emitter,
                cache,
                http,
                scoped,
            )

        @Post("adopt/:name")
        async def adopt(self, name: str):
            await self.commands.execute(Adopt(name))
            self.emitter.emit("pet.adopted", name)
            return {"count": await self.queries.execute(Count())}

        @Get("cached")
        async def cached(self):
            hit = await self.cache.get("k")
            if hit is None:
                await self.cache.set("k", "computed", 5)
                return {"hit": False}
            return {"hit": True, "value": hit}

        @Get("remote")
        async def remote(self):
            return (await self.http.get("/live/scope")).json()

        @Get("scope")
        def scope(self):
            return {"instance": self.scoped.id}

    port = free_port()
    # HttpModule calls the live server itself: a real outbound connection over TCP

    @Module(
        imports=[
            ScheduleModule.for_root(),
            CqrsModule.for_root(),
            EventEmitterModule.for_root(),
            CacheModule.register(),
            HttpModule.register(base_url=f"http://127.0.0.1:{port}"),
        ],
        controllers=[Live],
        providers=[Jobs, AdoptHandler, CountHandler, OnAdopted, Listener, PerRequest],
    )
    class App:
        pass

    async with serve(AustialFactory.create(App), port=port) as base, httpx.AsyncClient(base_url=base) as c:
        await wait_until(lambda: len(ticks) >= 3)  # the @Interval job fires on a real timer
        assert (await c.post("/live/adopt/tom")).json() == {"count": 1}
        assert (await c.post("/live/adopt/kit")).json() == {"count": 2}
        assert adopted == ["tom", "kit"]  # the event handler ran
        assert heard == ["tom", "kit"]  # wildcard @OnEvent("pet.*")
        assert (await c.get("/live/cached")).json() == {"hit": False}
        assert (await c.get("/live/cached")).json() == {"hit": True, "value": "computed"}
        first, second = (await c.get("/live/scope")).json(), (await c.get("/live/scope")).json()
        assert first["instance"] != second["instance"]  # request scope: a new instance per request
        assert "instance" in (await c.get("/live/remote")).json()  # HttpService made a real HTTP call to the server
    after_shutdown = len(ticks)
    await asyncio.sleep(0.5)
    assert len(ticks) == after_shutdown  # shutdown stopped the scheduler: no more ticks


# -- hybrid application: HTTP and a TCP microservice in one process ------------------------------


async def test_hybrid_app_serves_http_and_tcp_microservice() -> None:
    @Controller()
    class Both:
        @MessagePattern({"cmd": "double"})
        def double(self, n: int = Payload()):
            return n * 2

        @Get("ping")
        def ping(self):
            return {"pong": True}

    @Module(controllers=[Both])
    class App:
        pass

    tcp_port = free_port()
    app = AustialFactory.create(App)
    app.connect_microservice(MicroserviceOptions(Transport.TCP, port=tcp_port))
    async with serve(app) as base, httpx.AsyncClient(base_url=base) as c:
        assert (await c.get("/ping")).json() == {"pong": True}
        client = ClientProxy(ClientOptions("X", Transport.TCP, port=tcp_port))
        await client.connect()
        try:
            assert await client.send({"cmd": "double"}, 21) == 42
        finally:
            await client.close()
