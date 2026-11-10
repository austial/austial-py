# austial-microservices

Message-driven apps: `@MessagePattern` / `@EventPattern` over TCP, Redis, NATS, Kafka, MQTT, RabbitMQ and gRPC, plus `ClientProxy` and hybrid apps.

This is one of the six distributions of [Austial](https://github.com/austial/austial-py), a NestJS-style,
production-ready web framework for Python built on FastAPI. Most people want the umbrella package, which
installs everything and provides the `austial` CLI:

```bash
pip install austial        # or: uv tool install austial
```

Install on its own with `pip install 'austial-microservices[redis]'` (pick the broker extras you need).

- Documentation: <https://docs.austial.com>
- Source and issues: <https://github.com/austial/austial-py>
- License: MIT
