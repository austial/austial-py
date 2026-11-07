"""``MongoModule`` -- MongoDB through PyMongo's async client, mirrors ``@nestjs/mongoose``'s module shape.

::

    @Module(imports=[
        MongoModule.for_root(uri="mongodb://localhost:27017", database="app"),
        MongoModule.for_feature(["cats"]),
    ])
    class CatsModule: ...

    @Injectable()
    class CatsService:
        def __init__(self, cats=InjectCollection("cats")):
            self.cats = cats                              # a pymongo AsyncCollection

        async def find(self, name: str):
            return await self.cats.find_one({"name": name})

Needs ``pip install 'austial-mongo[pymongo]'``. The client connects when the application initialises (a ``ping``,
so a bad URI fails at startup, not on the first request) and closes when it shuts down.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from austial.common.decorators.injectable import Inject
from austial.common.decorators.modules import Module
from austial.common.logger import Logger
from austial.core.dynamic_module import DynamicModule
from austial.mongo.odm import MODEL_REGISTRY, Document, Model, ModelRegistry, model_token, schema_of

MONGO_OPTIONS = "AUSTIAL_MONGO_OPTIONS"
MONGO_CLIENT = "AUSTIAL_MONGO_CLIENT"
MONGO_DATABASE = "AUSTIAL_MONGO_DATABASE"

_logger = Logger("MongoModule")


@dataclass
class MongoOptions:
    uri: str = "mongodb://localhost:27017"
    database: str = "test"
    connect_on_init: bool = True  # ping the server during startup
    client_factory: Callable[..., Any] | None = None  # default: pymongo.AsyncMongoClient
    client_kwargs: dict[str, Any] = field(default_factory=dict)  # tls, maxPoolSize, serverSelectionTimeoutMS ...


def collection_token(name: str) -> str:
    return f"austial:mongo:collection:{name}"


def InjectCollection(name: str) -> Any:  # noqa: N802
    """Constructor default injecting the collection called ``name`` (declare it with ``MongoModule.for_feature``)."""
    return Inject(collection_token(name))


def InjectDatabase() -> Any:  # noqa: N802
    return Inject(MONGO_DATABASE)


def InjectClient() -> Any:  # noqa: N802
    return Inject(MONGO_CLIENT)


def _default_client_factory(uri: str, **kwargs: Any) -> Any:
    try:
        from pymongo import AsyncMongoClient
    except ImportError as exc:
        raise RuntimeError("MongoModule needs PyMongo 4.9+: pip install 'austial-mongo[pymongo]'") from exc
    return AsyncMongoClient(uri, **kwargs)


class MongoConnection:
    """Owns the client's life: pings on init, closes on shutdown."""

    def __init__(self, client: Any = Inject(MONGO_CLIENT), options: MongoOptions = Inject(MONGO_OPTIONS)):
        self.client, self.options = client, options

    async def on_module_init(self) -> None:
        if self.options.connect_on_init:
            await self.client.admin.command("ping")
            _logger.log(f"Connected to MongoDB database '{self.options.database}'")

    async def on_module_destroy(self) -> None:
        closed = self.client.close()
        if inspect.isawaitable(closed):  # PyMongo's async client awaits; Motor-style clients close synchronously
            await closed


@Module()
class MongoModule:
    @staticmethod
    def for_root(
        *,
        uri: str = "mongodb://localhost:27017",
        database: str = "test",
        connect_on_init: bool = True,
        client_factory: Callable[..., Any] | None = None,
        **client_kwargs: Any,
    ) -> DynamicModule:
        options = MongoOptions(uri, database, connect_on_init, client_factory, client_kwargs)
        return MongoModule._build([{"provide": MONGO_OPTIONS, "useValue": options}], [])

    @staticmethod
    def for_root_async(
        *,
        use_factory: Callable[..., MongoOptions],
        inject: Sequence[Any] = (),
        imports: Sequence[Any] = (),
    ) -> DynamicModule:
        provider = {"provide": MONGO_OPTIONS, "useFactory": use_factory, "inject": list(inject)}
        return MongoModule._build([provider], list(imports))

    @staticmethod
    def _build(options_providers: list[Any], imports: list[Any]) -> DynamicModule:
        def make_client(options: MongoOptions) -> Any:
            factory = options.client_factory or _default_client_factory
            return factory(options.uri, **options.client_kwargs)

        return DynamicModule(
            module=MongoModule,
            imports=imports,
            providers=[
                *options_providers,
                {"provide": MONGO_CLIENT, "useFactory": make_client, "inject": [MONGO_OPTIONS]},
                {
                    "provide": MONGO_DATABASE,
                    "useFactory": lambda client, options: client[options.database],
                    "inject": [MONGO_CLIENT, MONGO_OPTIONS],
                },
                {"provide": MODEL_REGISTRY, "useClass": ModelRegistry},
                MongoConnection,
            ],
            exports=[MONGO_CLIENT, MONGO_DATABASE, MONGO_OPTIONS],
        )

    @staticmethod
    def for_feature(features: Sequence[str | type[Document]]) -> DynamicModule:
        """Declares collections (``"cats"``, injectable with ``InjectCollection``) and/or ``@Schema`` classes
        (injectable as a :class:`Model` with ``InjectModel``)."""
        providers: list[Any] = []
        exports: list[Any] = []
        for feature in features:
            if isinstance(feature, str):
                providers.append(
                    {
                        "provide": collection_token(feature),
                        "useFactory": lambda db, n=feature: db[n],
                        "inject": [MONGO_DATABASE],
                    }
                )
                exports.append(collection_token(feature))
                continue

            def make_model(db: Any, registry: ModelRegistry, cls: type[Document] = feature) -> Model[Any]:
                model: Model[Any] = Model(db[schema_of(cls).collection], cls)
                registry.models.append(model)
                return model

            providers.append(
                {"provide": model_token(feature), "useFactory": make_model, "inject": [MONGO_DATABASE, MODEL_REGISTRY]}
            )
            exports.append(model_token(feature))
        return DynamicModule(module=MongoModule, providers=providers, exports=exports)
