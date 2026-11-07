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
from austial.mongo.odm import Document, Index, InjectModel, Model, ModelRegistry, Schema, model_token, schema_of

__all__ = [
    "Document",
    "Index",
    "InjectModel",
    "Model",
    "ModelRegistry",
    "Schema",
    "model_token",
    "schema_of",
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
