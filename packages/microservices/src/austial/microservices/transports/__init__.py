"""Broker transports. Each module imports its client library lazily, so none of them is a hard dependency."""

from austial.microservices.transports.grpc import GrpcClient, GrpcServer
from austial.microservices.transports.grpc_proto import GrpcMethod, GrpcProtoClient, GrpcProtoServer
from austial.microservices.transports.kafka import KafkaBackend
from austial.microservices.transports.mqtt import MqttBackend
from austial.microservices.transports.nats import NatsBackend
from austial.microservices.transports.pubsub import (
    JsonCodec,
    PubSubBackend,
    PubSubClient,
    PubSubServer,
    topic_for,
)
from austial.microservices.transports.rabbitmq import RabbitMqBackend
from austial.microservices.transports.redis import RedisBackend
from austial.microservices.transports.redis_streams import RedisStreamsBackend

__all__ = [
    "GrpcClient",
    "GrpcMethod",
    "GrpcProtoClient",
    "GrpcProtoServer",
    "GrpcServer",
    "KafkaBackend",
    "MqttBackend",
    "NatsBackend",
    "PubSubBackend",
    "PubSubClient",
    "JsonCodec",
    "PubSubServer",
    "RabbitMqBackend",
    "RedisBackend",
    "RedisStreamsBackend",
    "topic_for",
]
