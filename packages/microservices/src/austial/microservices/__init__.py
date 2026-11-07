"""``austial.microservices`` -- message-driven services, mirrors ``@nestjs/microservices``.

from austial.microservices import (
    MessagePattern, EventPattern, Payload, Ctx, ClientsModule, ClientProxy, ClientOptions,
    MicroserviceOptions, Transport, create_microservice,
)
"""

from austial.microservices.client import ClientProxy, ClientsModule
from austial.microservices.decorators import Ctx, EventPattern, MessagePattern, Payload
from austial.microservices.factory import build_client_transport, build_server_transport
from austial.microservices.microservice import (
    MicroserviceApplication,
    attach_microservice,
    create_microservice,
)
from austial.microservices.server import HandlerRegistry, MicroserviceServer, RpcContext, RpcExecutionContext
from austial.microservices.transport import (
    ClientOptions,
    ClientTransport,
    LocalClient,
    LocalServer,
    MicroserviceOptions,
    RpcError,
    RpcException,
    ServerTransport,
    TcpClient,
    TcpServer,
    Transport,
    pattern_key,
)

__all__ = [
    "ClientOptions",
    "ClientProxy",
    "ClientTransport",
    "ClientsModule",
    "Ctx",
    "EventPattern",
    "HandlerRegistry",
    "LocalClient",
    "LocalServer",
    "MessagePattern",
    "MicroserviceApplication",
    "MicroserviceOptions",
    "MicroserviceServer",
    "Payload",
    "RpcContext",
    "RpcError",
    "RpcException",
    "RpcExecutionContext",
    "ServerTransport",
    "TcpClient",
    "TcpServer",
    "Transport",
    "attach_microservice",
    "build_client_transport",
    "build_server_transport",
    "create_microservice",
    "pattern_key",
]
