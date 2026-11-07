"""gRPC transport (generic unary RPC, JSON payloads). Needs ``grpcio`` (``pip install 'austial-microservices[grpc]'``).

No ``.proto`` files or generated code: the service ``austial.Microservice`` has two unary methods, ``Request`` and
``Emit``, carrying UTF-8 JSON ``{"pattern": ..., "data": ...}`` and answering ``{"response": ...}`` or
``{"err": {...}}``. Use it between Austial services; to expose a real protobuf API to other languages, write your own
gRPC service and call your providers from it. Pass ``server_credentials`` / ``channel_credentials``
(``grpc.ssl_*_credentials``) for TLS.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from austial.microservices.transport import ClientTransport, RpcError, RpcException, ServerHandler, ServerTransport

SERVICE = "austial.Microservice"


def _grpc() -> Any:
    try:
        import grpc
        import grpc.aio  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("The gRPC transport needs grpcio: pip install 'austial-microservices[grpc]'") from exc
    return grpc


class GrpcServer(ServerTransport):
    def __init__(self, host: str = "127.0.0.1", port: int = 50051, *, server_credentials: Any = None):
        self.host, self.port, self.credentials = host, port, server_credentials
        self._server: Any = None

    async def listen(self, handler: ServerHandler) -> None:
        grpc = _grpc()

        async def request(payload: bytes, context: Any) -> bytes:
            message = json.loads(payload)
            try:
                reply: dict[str, Any] = {"response": await handler("request", message["pattern"], message.get("data"))}
            except RpcException as exc:
                reply = {"err": exc.payload}
            except Exception as exc:  # noqa: BLE001
                reply = {"err": {"status": "error", "message": f"{type(exc).__name__}: {exc}"}}
            return json.dumps(reply, default=str).encode()

        async def emit(payload: bytes, context: Any) -> bytes:
            message = json.loads(payload)
            # The handler registry logs failures; the sender isn't waiting for an answer.
            with contextlib.suppress(Exception):
                await handler("event", message["pattern"], message.get("data"))
            return b"{}"

        self._server = grpc.aio.server()
        self._server.add_generic_rpc_handlers(
            (
                grpc.method_handlers_generic_handler(
                    SERVICE,
                    {
                        "Request": grpc.unary_unary_rpc_method_handler(request),
                        "Emit": grpc.unary_unary_rpc_method_handler(emit),
                    },
                ),
            )
        )
        address = f"{self.host}:{self.port}"
        if self.credentials is not None:
            self.port = self._server.add_secure_port(address, self.credentials)
        else:
            self.port = self._server.add_insecure_port(address)
        await self._server.start()

    async def close(self) -> None:
        if self._server is not None:
            await self._server.stop(grace=0.5)
            self._server = None


class GrpcClient(ClientTransport):
    def __init__(
        self, host: str = "127.0.0.1", port: int = 50051, *, channel_credentials: Any = None, timeout: float = 5.0
    ):
        self.target, self.credentials, self.timeout = f"{host}:{port}", channel_credentials, timeout
        self._channel: Any = None

    async def connect(self) -> None:
        if self._channel is None:
            grpc = _grpc()
            self._channel = (
                grpc.aio.secure_channel(self.target, self.credentials)
                if self.credentials is not None
                else grpc.aio.insecure_channel(self.target)
            )

    async def _call(self, method: str, pattern: str, data: Any) -> dict[str, Any]:
        await self.connect()
        call = self._channel.unary_unary(f"/{SERVICE}/{method}")
        body = json.dumps({"pattern": pattern, "data": data}, default=str).encode()
        return json.loads(await call(body, timeout=self.timeout))

    async def request(self, pattern: str, data: Any) -> Any:
        reply = await self._call("Request", pattern, data)
        if "err" in reply:
            raise RpcError(reply["err"])
        return reply.get("response")

    async def emit(self, pattern: str, data: Any) -> None:
        await self._call("Emit", pattern, data)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
