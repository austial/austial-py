"""``austial.mongo`` -- MongoDB (PyMongo async client) with lifecycle-managed connections.

from austial.mongo import MongoModule, InjectCollection, InjectDatabase, InjectClient
"""

from austial.mongo.mongo_module import (
    MONGO_CLIENT,
    MONGO_DATABASE,
    MONGO_OPTIONS,
    InjectClient,
    InjectCollection,
    InjectDatabase,
    MongoConnection,
    MongoModule,
    MongoOptions,
    collection_token,
)

__all__ = [
    "MONGO_CLIENT",
    "MONGO_DATABASE",
    "MONGO_OPTIONS",
    "InjectClient",
    "InjectCollection",
    "InjectDatabase",
    "MongoConnection",
    "MongoModule",
    "MongoOptions",
    "collection_token",
]
