"""Broker transports. Each module imports its client library lazily, so none of them is a hard dependency."""

from austial.microservices.transports.grpc import GrpcClient, GrpcServer
from austial.microservices.transports.kafka import KafkaBackend
from austial.microservices.transports.mqtt import MqttBackend
from austial.microservices.transports.nats import NatsBackend
from austial.microservices.transports.pubsub import (
    PubSubBackend,
    PubSubClient,
    PubSubServer,
    topic_for,
)
from austial.microservices.transports.rabbitmq import RabbitMqBackend
from austial.microservices.transports.redis import RedisBackend

__all__ = [
    "GrpcClient",
    "GrpcServer",
    "KafkaBackend",
    "MqttBackend",
    "NatsBackend",
    "PubSubBackend",
    "PubSubClient",
    "PubSubServer",
    "RabbitMqBackend",
    "RedisBackend",
    "topic_for",
]
