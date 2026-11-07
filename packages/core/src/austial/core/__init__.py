"""Kept intentionally lightweight (no imports of ``app``/``factory``/``router_builder``)
so that low-level modules like ``austial.core.metadata`` can be imported from
deep within ``austial.common.decorators`` without triggering a circular import.
``AustialApplication``/``AustialFactory`` are imported directly from
``austial.core.app`` / ``austial.core.factory`` by ``austial/__init__.py``,
*after* ``austial.common`` has fully loaded.
"""

from austial.core.configurable_module import ConfigurableModule, ConfigurableModuleBuilder
from austial.core.container import (
    AsyncProviderNotInitializedError,
    CircularDependencyError,
    Container,
    ProviderNotFoundError,
    RequestScopeError,
)
from austial.core.discovery import DiscoveryService, InstanceWrapper
from austial.core.dynamic_module import DynamicModule
from austial.core.forward_ref import ForwardReference, forward_ref
from austial.core.lazy_module_loader import LazyModuleLoader
from austial.core.module_ref import ModuleRef
from austial.core.reflector import Reflector
from austial.core.request_context import REQUEST, ContextId, ContextIdFactory
from austial.core.routing import RouteInfo
from austial.core.tokens import APP_FILTER, APP_GUARD, APP_INTERCEPTOR, APP_PIPE

__all__ = [
    "AsyncProviderNotInitializedError",
    "APP_FILTER",
    "APP_GUARD",
    "APP_INTERCEPTOR",
    "APP_PIPE",
    "Container",
    "ConfigurableModule",
    "ConfigurableModuleBuilder",
    "ContextId",
    "ContextIdFactory",
    "DiscoveryService",
    "ForwardReference",
    "InstanceWrapper",
    "LazyModuleLoader",
    "ModuleRef",
    "ProviderNotFoundError",
    "CircularDependencyError",
    "DynamicModule",
    "REQUEST",
    "Reflector",
    "RequestScopeError",
    "RouteInfo",
    "forward_ref",
]
