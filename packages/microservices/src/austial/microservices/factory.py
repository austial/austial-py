"""Turns ``MicroserviceOptions`` / ``ClientOptions`` into the right transport object."""

from __future__ import annotations

from typing import Any

from austial.microservices.transport import (
    ClientOptions,
    ClientTransport,
    LocalClient,
    LocalServer,
    MicroserviceOptions,
    ServerTransport,
    TcpClient,
    TcpServer,
    Transport,
)


def _split_host_port(url: str | None, default_host: str, default_port: int) -> tuple[str, int]:
    if not url:
        return default_host, default_port
    host, _, port = url.removeprefix("mqtt://").rpartition(":")
    return (host or url, int(port)) if port.isdigit() else (url, default_port)


def _backend(transport: Transport, url: str | None, group: str, extra: dict[str, Any]) -> Any:
    from austial.microservices.transports import KafkaBackend, MqttBackend, NatsBackend, RabbitMqBackend, RedisBackend

    if transport == Transport.REDIS:
        return RedisBackend(url or "redis://localhost:6379", **extra)
    if transport == Transport.NATS:
        return NatsBackend(url or "nats://localhost:4222", **extra)
    if transport == Transport.KAFKA:
        return KafkaBackend(url or "localhost:9092", group=group, **extra)
    if transport == Transport.MQTT:
        host, port = _split_host_port(url, "localhost", 1883)
        return MqttBackend(host, port, **extra)
    if transport == Transport.RMQ:
        return RabbitMqBackend(url or "amqp://guest:guest@localhost/", **extra)
    raise ValueError(f"Not a broker transport: {transport}")


_BROKERS = {Transport.REDIS, Transport.NATS, Transport.KAFKA, Transport.MQTT, Transport.RMQ}


def build_server_transport(options: MicroserviceOptions) -> ServerTransport:
    if options.transport == Transport.TCP:
        return TcpServer(options.host, options.port)
    if options.transport == Transport.LOCAL:
        return LocalServer(options.name)
    if options.transport in _BROKERS:
        from austial.microservices.transports import PubSubServer

        # NATS and MQTT share load via the group; Kafka's group is consumed inside the backend; RabbitMQ shares by queue
        grouped = options.transport in (Transport.NATS, Transport.MQTT)
        return PubSubServer(
            _backend(options.transport, options.url, options.group, options.extra),
            prefix=options.prefix,
            group=options.group if grouped else None,
            codec=options.codec,
        )
    if options.transport == Transport.GRPC:
        from austial.microservices.transports import GrpcServer

        return GrpcServer(options.host, options.port, **options.extra)
    if options.custom_server is None:
        raise ValueError("Transport.CUSTOM needs custom_server=")
    return options.custom_server


def build_client_transport(options: ClientOptions) -> ClientTransport:
    if options.transport == Transport.TCP:
        return TcpClient(options.host, options.port, options.timeout)
    if options.transport == Transport.LOCAL:
        return LocalClient(options.broker)
    if options.transport in _BROKERS:
        from austial.microservices.transports import PubSubClient

        return PubSubClient(
            _backend(options.transport, options.url, "austial", options.extra),
            prefix=options.prefix,
            timeout=options.timeout,
            codec=options.codec,
        )
    if options.transport == Transport.GRPC:
        from austial.microservices.transports import GrpcClient

        return GrpcClient(options.host, options.port, timeout=options.timeout, **options.extra)
    if options.custom_client is None:
        raise ValueError(f"Client '{options.name}': Transport.CUSTOM needs custom_client=")
    return options.custom_client
