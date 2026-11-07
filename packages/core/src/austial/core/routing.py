"""Route matching beyond path + method: API versioning, host-based routing, global prefix.

Starlette picks the first route whose path and method match, so two routes at the same path
but different *versions* (header / media-type versioning) or *hosts* can't be told apart by
path alone. :class:`AustialRoute` extends ``matches()`` with extra predicates: a route whose
predicates reject the request reports ``Match.NONE`` and the router simply moves on to the
next candidate (ending in the usual 404 if none accept).
"""

from __future__ import annotations

import re
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any

from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

from austial.common.enums import VERSION_NEUTRAL, RequestMethod, RouteInfo, VersioningType

Scope = MutableMapping[str, Any]
Matcher = Callable[[Scope], "dict[str, Any] | None"]


@dataclass
class VersioningOptions:
    type: VersioningType = VersioningType.URI
    prefix: str | bool = "v"  # URI: "v" -> /v1/...; False -> /1/...
    header: str | None = None  # HEADER: the header carrying the version
    key: str = "v="  # MEDIA_TYPE: the Accept parameter, e.g. `application/json;v=2`
    default_version: str | Sequence[str] | None = None
    extractor: Callable[[Request], str | Sequence[str] | None] | None = None  # CUSTOM

    def default_versions(self) -> list[str]:
        if self.default_version is None:
            return []
        return (
            [str(self.default_version)]
            if isinstance(self.default_version, str)
            else [str(v) for v in self.default_version]
        )


@dataclass
class GlobalPrefix:
    prefix: str = ""
    exclude: Sequence[str | RouteInfo] = ()

    def applies_to(self, path: str, method: str) -> bool:
        if not self.prefix:
            return False
        for entry in self.exclude:
            info = entry if isinstance(entry, RouteInfo) else RouteInfo(entry)
            if _normalize(info.path) == _normalize(path) and info.method in (RequestMethod.ALL, method):
                return False
        return True


def _normalize(path: str) -> str:
    return "/" + path.strip("/") if path.strip("/") else "/"


def effective_versions(route_version: Any, options: VersioningOptions | None) -> list[str] | None:
    """The versions a route answers: ``None`` = neutral / unversioned (always matches)."""
    if options is None:
        return None
    versions = route_version if isinstance(route_version, list) else ([route_version] if route_version else [])
    if VERSION_NEUTRAL in versions:
        return None
    return versions or options.default_versions() or None


def uri_version_segment(version: str, options: VersioningOptions) -> str:
    prefix = options.prefix if isinstance(options.prefix, str) else ""
    return f"/{prefix}{version}"


# -- request-side version extraction (HEADER / MEDIA_TYPE / CUSTOM) ----------------------------
def _requested_versions(scope: Scope, options: VersioningOptions) -> list[str]:
    headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
    if options.type == VersioningType.HEADER:
        value = headers.get((options.header or "x-api-version").lower())
        return [v.strip() for v in value.split(",")] if value else []
    if options.type == VersioningType.MEDIA_TYPE:
        found = []
        for media in headers.get("accept", "").split(","):
            for param in media.split(";")[1:]:
                param = param.strip()
                if param.startswith(options.key):
                    found.append(param[len(options.key) :].strip())
        return found
    if options.type == VersioningType.CUSTOM and options.extractor is not None:
        value = options.extractor(Request(scope))
        if value is None:
            return []
        return [str(value)] if isinstance(value, str) else [str(v) for v in value]
    return []


def version_matcher(versions: list[str] | None, options: VersioningOptions) -> Matcher | None:
    if versions is None or options.type == VersioningType.URI:
        return None  # neutral routes always match; URI versions live in the path

    def match(scope: Scope) -> dict[str, Any] | None:
        requested = _requested_versions(scope, options) or options.default_versions()
        return {} if any(v in versions for v in requested) else None

    return match


# -- host-based routing --------------------------------------------------------------------
_HOST_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")


def _compile_host(pattern: str) -> re.Pattern[str]:
    regex, last = "", 0
    for m in _HOST_PARAM.finditer(pattern):
        regex += re.escape(pattern[last : m.start()]) + f"(?P<{m.group(1)}>[^.]+)"
        last = m.end()
    return re.compile("^" + regex + re.escape(pattern[last:]) + "$", re.IGNORECASE)


def host_matcher(hosts: str | Sequence[str] | None) -> Matcher | None:
    if not hosts:
        return None
    patterns = [_compile_host(h) for h in ([hosts] if isinstance(hosts, str) else hosts)]

    def match(scope: Scope) -> dict[str, Any] | None:
        raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"host"), "")
        host = raw.rsplit(":", 1)[0] if raw.count(":") == 1 else raw  # drop the port
        for pattern in patterns:
            found = pattern.match(host)
            if found:
                return {"austial.host_params": found.groupdict()}
        return None

    return match


class AustialRoute(APIRoute):
    """``APIRoute`` + extra match predicates (see module docstring). Instances come from
    :func:`route_class_for`, which bakes a route's predicates into a subclass."""

    austial_matchers: tuple[Matcher, ...] = ()
    austial_token: object | None = None  # set for routes whose handler takes `Next()`

    def matches(self, scope: MutableMapping[str, Any]) -> tuple[Match, MutableMapping[str, Any]]:
        match, child_scope = super().matches(scope)
        if match != Match.FULL:
            return match, child_scope
        if self.austial_token is not None and self.austial_token in scope.get(DECLINED_KEY, ()):
            return Match.NONE, {}  # this route already declined the request via `next()`
        extra: dict[str, Any] = {}
        for matcher in self.austial_matchers:
            result = matcher(scope)
            if result is None:
                return Match.NONE, {}
            extra.update(result)
        return match, {**child_scope, **extra}


DECLINED_KEY = "austial.declined"


class PassThrough(Response):
    """What a handler that called ``next()`` answers with: instead of a body, it re-dispatches the request through the
    application's router with the declining route marked, so the router picks the next matching route (or 404s).

    The body was already read for the declining route, so it is replayed for the next one.
    """

    def __init__(self, token: object, body: bytes):
        super().__init__()
        self.token, self.body = token, body

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        fresh = {k: v for k, v in scope.items() if k not in ("route", "endpoint", "path_params")}
        fresh[DECLINED_KEY] = frozenset(scope.get(DECLINED_KEY, ())) | {self.token}
        delivered = False

        async def replay() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": self.body, "more_body": False}
            return await receive()

        await scope["app"].router(fresh, replay, send)


def route_class_for(matchers: list[Matcher], *, token: object | None = None) -> type[APIRoute] | None:
    if not matchers and token is None:
        return None
    return type("AustialRoute", (AustialRoute,), {"austial_matchers": tuple(matchers), "austial_token": token})
