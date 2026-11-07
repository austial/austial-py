"""gRPC with real Protocol Buffers: serve and call services defined in a ``.proto`` file, interoperable with clients
and servers in any language (the ``@GrpcMethod`` workflow of ``@nestjs/microservices``).

Needs ``pip install 'austial-microservices[grpc-proto]'`` (``grpcio``, ``grpcio-tools``). The ``.proto`` is compiled at
startup (no generated code to commit); messages cross the boundary as plain dicts.

::

    # hero.proto
    #   service HeroService {
    #     rpc FindOne (HeroById) returns (Hero);
    #     rpc FindMany (Query) returns (stream Hero);
    #     rpc Sum (stream Number) returns (Number);
    #     rpc Chat (stream Line) returns (stream Line);
    #   }

    @Controller()
    class HeroController:
        @GrpcMethod("HeroService")                      # method defaults to the PascalCase function name: FindOne
        def find_one(self, data: dict = Payload()):
            return {"id": data["id"], "name": "Ada"}

        @GrpcMethod("HeroService", "FindMany")          # server streaming: yield (or return an iterable of) dicts
        async def find_many(self, data: dict = Payload()):
            for n in range(3):
                yield {"id": n}

        @GrpcMethod("HeroService")                      # client streaming: the payload is an async iterator of dicts
        async def sum(self, numbers=Payload()):
            return {"value": sum([n["value"] async for n in numbers])}

    app.connect_microservice(MicroserviceOptions(Transport.GRPC, port=50051, extra={"proto_path": "hero.proto"}))

    # a client
    heroes = ClientProxy(ClientOptions("HEROES", Transport.GRPC, port=50051, extra={"proto_path": "hero.proto"}))
    await heroes.connect()
    service = heroes.get_service("HeroService")
    hero = await service.find_one({"id": 1})            # unary
    async for hero in service.find_many({}): ...        # server streaming
    total = await service.sum([{"value": 1}, {"value": 2}])   # client streaming: any (async) iterable

``extra`` keys: ``proto_path`` (required), ``include`` (extra import directories), ``services`` (server: short names to
serve; default every service in the file), ``server_credentials`` / ``channel_credentials``
(``grpc.ssl_*_credentials``). Without ``proto_path`` the transport falls back to the schema-less JSON mode
(:mod:`austial.microservices.transports.grpc`).

Errors: an ``RpcException`` becomes a gRPC status (``{"code": <grpc code number>}`` in its payload picks it; "Forbidden
resource" is ``PERMISSION_DENIED``; an unmapped handler is ``UNIMPLEMENTED``; anything else is ``UNKNOWN``);
on the client a failed call raises ``RpcError`` with ``{"status", "message", "code"}``.
"""

from __future__ import annotations

import importlib.resources
import re
import tempfile
from collections.abc import AsyncIterator, Callable, Iterable
from pathlib import Path
from typing import Any

from austial.core.metadata import set_metadata
from austial.microservices.decorators import MESSAGE_PATTERN_METADATA
from austial.microservices.transport import ClientTransport, RpcError, RpcException, ServerHandler, ServerTransport


def _deps() -> Any:
    try:
        import grpc
        import grpc.aio  # noqa: F401
        from google.protobuf import descriptor_pb2, descriptor_pool, json_format, message_factory
        from grpc_tools import protoc
    except ImportError as exc:
        raise RuntimeError(
            "Protobuf gRPC needs grpcio, grpcio-tools and protobuf: pip install 'austial-microservices[grpc-proto]'"
        ) from exc
    return grpc, descriptor_pb2, descriptor_pool, json_format, message_factory, protoc


def pascal(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def GrpcMethod(service: str, method: str | None = None) -> Callable:  # noqa: N802
    """Marks a handler as the implementation of ``service``'s ``method`` (default: the PascalCase function name).
    Streaming kinds follow from the ``.proto`` signature: a server-streaming handler yields dicts, a
    client-streaming one receives an async iterator of dicts as its payload."""

    def decorate(fn: Callable) -> Callable:
        return set_metadata(MESSAGE_PATTERN_METADATA, f"grpc:{service}/{method or pascal(fn.__name__)}")(fn)

    return decorate


class ProtoSchema:
    """A compiled ``.proto``: services, their methods and message classes."""

    def __init__(self, proto_path: str | Path, include: Iterable[str | Path] = ()):
        grpc, descriptor_pb2, descriptor_pool, json_format, message_factory, protoc = _deps()
        self.grpc, self._json, self._factory = grpc, json_format, message_factory
        path = Path(proto_path).resolve()
        well_known = str(importlib.resources.files("grpc_tools") / "_proto")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "schema.pb"
            args = ["protoc", f"-I{path.parent}", *[f"-I{Path(i).resolve()}" for i in include], f"-I{well_known}"]
            args += [f"--descriptor_set_out={out}", "--include_imports", path.name]
            if protoc.main(args) != 0:
                raise ValueError(f"protoc could not compile {path} (see its output above)")
            files = descriptor_pb2.FileDescriptorSet.FromString(out.read_bytes()).file
        self.pool = descriptor_pool.DescriptorPool()
        for file in files:
            self.pool.AddSerializedFile(file.SerializeToString())
        self.main_file = files[-1]  # protoc lists dependencies first, the requested file last

    def service_names(self) -> list[tuple[str, str]]:
        """(short name, full name) of every service declared in the main file."""
        package = self.main_file.package
        return [(s.name, f"{package}.{s.name}" if package else s.name) for s in self.main_file.service]

    def service(self, name: str) -> Any:
        for short, full in self.service_names():
            if name in (short, full):
                return self.pool.FindServiceByName(full)
        raise LookupError(f"The .proto declares no service '{name}' (it has {[s for s, _ in self.service_names()]})")

    def message_class(self, descriptor: Any) -> Any:
        return self._factory.GetMessageClass(descriptor)

    def to_dict(self, message: Any) -> dict[str, Any]:
        return self._json.MessageToDict(
            message, preserving_proto_field_name=True, always_print_fields_with_no_presence=True
        )

    def to_message(self, value: Any, cls: Any) -> Any:
        if isinstance(value, cls):
            return value
        return self._json.ParseDict(value or {}, cls())


def _status_for(grpc: Any, exc: RpcException) -> tuple[Any, str]:
    payload = exc.payload if isinstance(exc.payload, dict) else {}
    message = str(payload.get("message", exc))
    code = payload.get("code")
    if isinstance(code, int):
        for status in grpc.StatusCode:
            if status.value[0] == code:
                return status, message
    if message == "Forbidden resource":
        return grpc.StatusCode.PERMISSION_DENIED, message
    if message.startswith("There is no matching message handler"):
        return grpc.StatusCode.UNIMPLEMENTED, message
    return grpc.StatusCode.UNKNOWN, message


class GrpcProtoServer(ServerTransport):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        *,
        proto_path: str | Path,
        include: Iterable[str | Path] = (),
        services: Iterable[str] | None = None,
        server_credentials: Any = None,
    ):
        self.host, self.port, self.credentials = host, port, server_credentials
        self.schema = ProtoSchema(proto_path, include)
        self.services = list(services) if services is not None else None
        self._server: Any = None

    async def listen(self, handler: ServerHandler) -> None:
        grpc = self.schema.grpc
        schema = self.schema
        self._server = grpc.aio.server()
        wanted = [s for s, _ in schema.service_names() if self.services is None or s in self.services]
        for short in wanted:
            descriptor = schema.service(short)
            methods = {m.name: self._rpc(grpc, schema, handler, short, m) for m in descriptor.methods}
            self._server.add_generic_rpc_handlers(
                (grpc.method_handlers_generic_handler(descriptor.full_name, methods),)
            )
        address = f"{self.host}:{self.port}"
        if self.credentials is not None:
            self.port = self._server.add_secure_port(address, self.credentials)
        else:
            self.port = self._server.add_insecure_port(address)
        await self._server.start()

    @staticmethod
    def _rpc(grpc: Any, schema: ProtoSchema, handler: ServerHandler, service: str, method: Any) -> Any:
        request_cls, response_cls = schema.message_class(method.input_type), schema.message_class(method.output_type)
        key = f"grpc:{service}/{method.name}"

        async def invoke(data: Any, context: Any) -> Any:
            try:
                return await handler("request", key, data)
            except RpcException as exc:
                status, message = _status_for(grpc, exc)
                await context.abort(status, message)
            except Exception as exc:  # noqa: BLE001
                await context.abort(grpc.StatusCode.UNKNOWN, f"{type(exc).__name__}: {exc}")

        async def requests(iterator: AsyncIterator[Any]) -> AsyncIterator[dict[str, Any]]:
            async for message in iterator:
                yield schema.to_dict(message)

        async def emit_stream(result: Any) -> AsyncIterator[Any]:
            if hasattr(result, "__aiter__"):
                async for item in result:
                    yield schema.to_message(item, response_cls)
            else:
                for item in result or ():
                    yield schema.to_message(item, response_cls)

        serializer = response_cls.SerializeToString
        common = {"request_deserializer": request_cls.FromString, "response_serializer": serializer}

        if not method.client_streaming and not method.server_streaming:

            async def unary(request: Any, context: Any) -> Any:
                return schema.to_message(await invoke(schema.to_dict(request), context), response_cls)

            return grpc.unary_unary_rpc_method_handler(unary, **common)
        if not method.client_streaming:

            async def server_stream(request: Any, context: Any) -> AsyncIterator[Any]:
                async for item in emit_stream(await invoke(schema.to_dict(request), context)):
                    yield item

            return grpc.unary_stream_rpc_method_handler(server_stream, **common)
        if not method.server_streaming:

            async def client_stream(request_iterator: Any, context: Any) -> Any:
                return schema.to_message(await invoke(requests(request_iterator), context), response_cls)

            return grpc.stream_unary_rpc_method_handler(client_stream, **common)

        async def bidi(request_iterator: Any, context: Any) -> AsyncIterator[Any]:
            async for item in emit_stream(await invoke(requests(request_iterator), context)):
                yield item

        return grpc.stream_stream_rpc_method_handler(bidi, **common)

    async def close(self) -> None:
        if self._server is not None:
            await self._server.stop(grace=0.5)
            self._server = None


class GrpcServiceClient:
    """``await service.find_one({...})`` -- one callable per ``.proto`` method (exact name or snake_case)."""

    def __init__(self, channel: Any, schema: ProtoSchema, name: str, timeout: float):
        grpc = schema.grpc
        descriptor = schema.service(name)
        self._calls: dict[str, Callable[..., Any]] = {}
        for method in descriptor.methods:
            request_cls, response_cls = (
                schema.message_class(method.input_type),
                schema.message_class(method.output_type),
            )
            path = f"/{descriptor.full_name}/{method.name}"
            kind = (
                ("stream" if method.client_streaming else "unary")
                + "_"
                + ("stream" if method.server_streaming else "unary")
            )
            stub = getattr(channel, kind)(
                path, request_serializer=request_cls.SerializeToString, response_deserializer=response_cls.FromString
            )
            call = self._make(grpc, schema, stub, request_cls, method, timeout)
            self._calls[method.name] = self._calls[snake(method.name)] = call

    @staticmethod
    def _make(
        grpc: Any, schema: ProtoSchema, stub: Any, request_cls: Any, method: Any, timeout: float
    ) -> Callable[..., Any]:
        def failure(exc: Any) -> RpcError:
            return RpcError({"status": "error", "message": exc.details(), "code": exc.code().value[0]})

        async def outgoing(source: Any) -> AsyncIterator[Any]:
            if hasattr(source, "__aiter__"):
                async for item in source:
                    yield schema.to_message(item, request_cls)
            else:
                for item in source:
                    yield schema.to_message(item, request_cls)

        if not method.server_streaming:

            async def unary_response(data: Any = None, *, timeout: float = timeout, metadata: Any = None) -> Any:
                payload = outgoing(data) if method.client_streaming else schema.to_message(data, request_cls)
                try:
                    return schema.to_dict(await stub(payload, timeout=timeout, metadata=metadata))
                except grpc.aio.AioRpcError as exc:
                    raise failure(exc) from exc

            return unary_response

        async def streaming_response(data: Any = None, *, timeout: float = timeout, metadata: Any = None) -> Any:
            payload = outgoing(data) if method.client_streaming else schema.to_message(data, request_cls)
            try:
                async for item in stub(payload, timeout=timeout, metadata=metadata):
                    yield schema.to_dict(item)
            except grpc.aio.AioRpcError as exc:
                raise failure(exc) from exc

        return streaming_response

    def __getattr__(self, name: str) -> Callable[..., Any]:
        try:
            return self._calls[name]
        except KeyError:
            raise AttributeError(f"The service has no method '{name}' (it has {sorted(set(self._calls))})") from None


class GrpcProtoClient(ClientTransport):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        *,
        proto_path: str | Path,
        include: Iterable[str | Path] = (),
        channel_credentials: Any = None,
        timeout: float = 5.0,
    ):
        self.target, self.credentials, self.timeout = f"{host}:{port}", channel_credentials, timeout
        self.schema = ProtoSchema(proto_path, include)
        self._channel: Any = None

    async def connect(self) -> None:
        if self._channel is None:
            grpc = self.schema.grpc
            self._channel = (
                grpc.aio.secure_channel(self.target, self.credentials)
                if self.credentials is not None
                else grpc.aio.insecure_channel(self.target)
            )

    def get_service(self, name: str) -> GrpcServiceClient:
        if self._channel is None:
            raise RuntimeError("Call connect() before get_service()")
        return GrpcServiceClient(self._channel, self.schema, name, self.timeout)

    async def request(self, pattern: str, data: Any) -> Any:
        """``client.send("HeroService/FindOne", {...})``: a unary call by ``Service/Method``."""
        service, _, method = pattern.partition("/")
        return await getattr(self.get_service(service), method)(data)

    async def emit(self, pattern: str, data: Any) -> None:
        raise NotImplementedError("gRPC has no fire-and-forget events: call a method with get_service()")

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
