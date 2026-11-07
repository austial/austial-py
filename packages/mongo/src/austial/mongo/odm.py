"""Document models -- the ``@nestjs/mongoose`` workflow: declare a schema class, register it, inject a model.

::

    from austial.mongo import Document, Index, InjectModel, Model, MongoModule, Schema

    @Schema(collection="cats", indexes=[Index("name", unique=True)])
    class Cat(Document):
        name: str
        age: int = 0

    @Module(imports=[MongoModule.for_root(database="app"), MongoModule.for_feature([Cat])])
    class CatsModule: ...

    @Injectable()
    class CatsService:
        def __init__(self, cats: Model[Cat] = InjectModel(Cat)):
            self.cats = cats

        async def adopt(self, name: str) -> Cat:
            return await self.cats.create({"name": name})

Schemas are pydantic models, so validation, defaults and ``Field`` constraints work as everywhere else in Austial.
``id`` maps to Mongo's ``_id`` (an ``ObjectId``, exposed as ``str``). Indexes declared on the schema are created
once, before a model's first operation. ``Model.collection`` is the underlying PyMongo collection for anything the
helpers don't cover.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from austial.common.decorators.injectable import Inject

try:  # bson ships with PyMongo; without it ids stay plain strings
    from bson import ObjectId
except ImportError:  # pragma: no cover
    ObjectId = None  # type: ignore[assignment,misc]


@dataclass
class Index:
    """One index: ``Index("name", unique=True)``, ``Index(("a", 1), ("b", -1))``, or a TTL
    ``Index("expires", expire_after_seconds=60)``."""

    keys: tuple[Any, ...]
    unique: bool = False
    sparse: bool = False
    expire_after_seconds: int | None = None
    name: str | None = None

    def __init__(
        self,
        *keys: Any,
        unique: bool = False,
        sparse: bool = False,
        expire_after_seconds: int | None = None,
        name: str | None = None,
    ):
        self.keys, self.unique, self.sparse = keys, unique, sparse
        self.expire_after_seconds, self.name = expire_after_seconds, name

    def spec(self) -> list[tuple[str, int]]:
        return [(k, 1) if isinstance(k, str) else (k[0], k[1]) for k in self.keys]

    def options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"unique": self.unique, "sparse": self.sparse}
        if self.expire_after_seconds is not None:
            options["expireAfterSeconds"] = self.expire_after_seconds
        if self.name:
            options["name"] = self.name
        return options


@dataclass
class SchemaSpec:
    collection: str
    indexes: list[Index] = field(default_factory=list)


class Document(BaseModel):
    """Base class of schemas. ``id`` is Mongo's ``_id``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    __schema__: ClassVar[SchemaSpec]

    id: str | None = Field(default=None, alias="_id")

    @field_validator("id", mode="before")
    @classmethod
    def _stringify_id(cls, value: Any) -> Any:
        return str(value) if value is not None else None


D = TypeVar("D", bound=Document)


def Schema(collection: str | None = None, *, indexes: Sequence[Index] = ()):  # noqa: N802
    """Binds a :class:`Document` subclass to a collection (default: class name lower-cased + ``s``)."""

    def decorate(cls: type[D]) -> type[D]:
        cls.__schema__ = SchemaSpec(collection or f"{cls.__name__.lower()}s", list(indexes))
        return cls

    return decorate


def schema_of(cls: type[Document]) -> SchemaSpec:
    spec = cls.__dict__.get("__schema__")
    if spec is None:
        raise TypeError(f"{cls.__name__} is not decorated with @Schema(...)")
    return spec


def _oid(value: Any) -> Any:
    """Strings that look like ObjectIds become ObjectIds, so ``find_by_id("65f...")`` works."""
    if ObjectId is not None and isinstance(value, str) and ObjectId.is_valid(value):
        return ObjectId(value)
    return value


def _filter(filter: dict[str, Any] | None) -> dict[str, Any]:  # noqa: A002
    if not filter:
        return {}
    return {("_id" if k == "id" else k): (_oid(v) if k in ("id", "_id") else v) for k, v in filter.items()}


class Model(Generic[D]):
    def __init__(self, collection: Any, cls: type[D]):
        self.collection, self.cls = collection, cls
        self._indexed = False

    def _wrap(self, raw: dict[str, Any] | None) -> D | None:
        return self.cls.model_validate(raw) if raw is not None else None

    def _dump(self, data: dict[str, Any] | D) -> dict[str, Any]:
        document = self.cls.model_validate(data) if isinstance(data, dict) else data
        raw = document.model_dump(by_alias=True)
        if raw.get("_id") is None:
            raw.pop("_id", None)  # let Mongo generate it
        else:
            raw["_id"] = _oid(raw["_id"])
        return raw

    async def create(self, data: dict[str, Any] | D) -> D:
        """Validates ``data``, inserts it and returns the stored document (with its generated ``id``)."""
        await self._ready()
        raw = self._dump(data)
        result = await self.collection.insert_one(raw)
        raw["_id"] = result.inserted_id
        return self.cls.model_validate(raw)

    async def create_many(self, items: Sequence[dict[str, Any] | D]) -> list[D]:
        return [await self.create(item) for item in items]

    async def find(
        self,
        filter: dict[str, Any] | None = None,  # noqa: A002
        *,
        sort: Sequence[tuple[str, int]] | None = None,
        skip: int = 0,
        limit: int = 0,
    ) -> list[D]:
        await self._ready()
        cursor = self.collection.find(_filter(filter))
        if sort:
            cursor = cursor.sort(list(sort))
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return [self.cls.model_validate(raw) for raw in await cursor.to_list(length=None)]

    async def find_one(self, filter: dict[str, Any] | None = None) -> D | None:  # noqa: A002
        await self._ready()
        return self._wrap(await self.collection.find_one(_filter(filter)))

    async def find_by_id(self, id: str) -> D | None:  # noqa: A002
        return await self.find_one({"_id": id})

    async def update_one(
        self,
        filter: dict[str, Any],  # noqa: A002
        changes: dict[str, Any],
        *,
        upsert: bool = False,
    ) -> D | None:
        """``changes`` is a field->value mapping applied with ``$set``, or an update document using ``$`` operators.
        Returns the document after the update, validated."""
        await self._ready()
        from pymongo import ReturnDocument

        update = changes if any(k.startswith("$") for k in changes) else {"$set": changes}
        raw = await self.collection.find_one_and_update(
            _filter(filter), update, upsert=upsert, return_document=ReturnDocument.AFTER
        )
        return self._wrap(raw)

    async def update_by_id(self, id: str, changes: dict[str, Any]) -> D | None:  # noqa: A002
        return await self.update_one({"_id": id}, changes)

    async def delete_one(self, filter: dict[str, Any]) -> bool:  # noqa: A002
        await self._ready()
        return bool((await self.collection.delete_one(_filter(filter))).deleted_count)

    async def delete_by_id(self, id: str) -> bool:  # noqa: A002
        return await self.delete_one({"_id": id})

    async def delete_many(self, filter: dict[str, Any] | None = None) -> int:  # noqa: A002
        await self._ready()
        return int((await self.collection.delete_many(_filter(filter))).deleted_count)

    async def count(self, filter: dict[str, Any] | None = None) -> int:  # noqa: A002
        await self._ready()
        return int(await self.collection.count_documents(_filter(filter)))

    async def exists(self, filter: dict[str, Any]) -> bool:  # noqa: A002
        return await self.count(filter) > 0

    async def aggregate(self, pipeline: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        await self._ready()
        cursor = self.collection.aggregate(list(pipeline))
        if inspect.isawaitable(cursor):  # PyMongo's async client returns an awaitable cursor, Motor a plain one
            cursor = await cursor
        return list(await cursor.to_list(length=None))

    async def _ready(self) -> None:
        if not self._indexed:
            self._indexed = True
            await self.ensure_indexes()

    async def ensure_indexes(self) -> None:
        self._indexed = True
        for index in schema_of(self.cls).indexes:
            await self.collection.create_index(index.spec(), **index.options())


class ModelRegistry:
    """Collects every model so their indexes are created once the application initialises."""

    def __init__(self) -> None:
        self.models: list[Model[Any]] = []

    async def on_module_init(self) -> None:
        for model in self.models:
            await model.ensure_indexes()


MODEL_REGISTRY = "AUSTIAL_MONGO_MODEL_REGISTRY"


def model_token(cls: type[Document]) -> str:
    return f"austial:mongo:model:{cls.__module__}.{cls.__qualname__}"


def InjectModel(cls: type[Document]) -> Any:  # noqa: N802
    """Constructor default injecting the :class:`Model` of ``cls`` (declare it with ``MongoModule.for_feature``)."""
    return Inject(model_token(cls))
