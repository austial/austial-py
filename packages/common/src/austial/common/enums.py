from enum import IntEnum, StrEnum


class Scope(StrEnum):
    """Provider scope, mirrors ``@nestjs/common``'s ``Scope``.

    * ``DEFAULT`` -- singleton, one instance per application.
    * ``TRANSIENT`` -- a new instance every time it's resolved.
    * ``REQUEST`` -- one instance per request (per :class:`~austial.core.request_context.ContextId`),
      built lazily on first use and discarded with the request. Scope *bubbles up*: a provider
      (or controller, guard, interceptor...) that depends on a request-scoped provider -- or on
      the injectable ``REQUEST`` token -- is itself resolved per request.
    """

    DEFAULT = "DEFAULT"
    TRANSIENT = "TRANSIENT"
    REQUEST = "REQUEST"


class VersioningType(IntEnum):
    """How a request names the API version it wants, mirrors Nest's ``VersioningType``."""

    URI = 0  # /v1/cats
    HEADER = 1  # X-API-Version: 1
    MEDIA_TYPE = 2  # Accept: application/json;v=1
    CUSTOM = 3  # a user-supplied extractor


class RequestMethod(StrEnum):
    """HTTP verbs, mirrors Nest's ``RequestMethod`` (``ALL`` matches any verb)."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"
    ALL = "ALL"


# `@Version(VERSION_NEUTRAL)` -- the route is served whatever version the request asks for
# (or none at all), mirrors Nest's `VERSION_NEUTRAL`.
VERSION_NEUTRAL = "__austial_version_neutral__"
