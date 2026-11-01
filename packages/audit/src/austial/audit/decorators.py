"""``@Audited(...)`` -- metadata decorator + interceptor factory.

Applied to a controller handler (or a whole controller class), it declares
"record an :class:`AuditEvent` around this call". :class:`AuditedInterceptor`
reads the metadata off the handler at request time and records success or
failure via :class:`AuditLogService`.

Kept as a decorator rather than a mandatory guard so audit coverage is a
per-route decision -- the compliance auditor's spreadsheet lists routes,
not guards, and the metadata mirrors that shape.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from austial.core.metadata import get_metadata, set_metadata

AUDITED_METADATA = "austial:audit:audited"


@dataclass(frozen=True, slots=True)
class AuditSpec:
    """The values captured by ``@Audited(...)``. Read by
    :class:`AuditedInterceptor` at request time.

    ``resource_id_from``:

    - ``None`` -- do not attempt to resolve a ``resource_id`` beyond
      whatever product code puts on ``request.state.audit_resource_id``.
    - ``"path:<name>"`` -- read from ``request.path_params[<name>]``.
    - ``"result.<key>"`` (or nested with dots) -- read from the response,
      after the handler runs, via ``response[<key>][<...>]``.
    """

    action: str
    resource_type: str
    resource_id_from: str | None = None
    capture_result: bool = False


def Audited(  # noqa: N802 - decorator naming mirrors ``@Public()`` and friends
    action: str,
    *,
    resource_type: str,
    resource_id_from: str | None = None,
    capture_result: bool = False,
) -> Callable:
    """Attach an :class:`AuditSpec` to a handler / controller.

    Usage::

        @Controller("/funds")
        class FundsController:
            @Post()
            @Audited("funds.create", resource_type="Fund", resource_id_from="result.id")
            def create(self, dto: CreateFundDto): ...
    """

    spec = AuditSpec(
        action=action,
        resource_type=resource_type,
        resource_id_from=resource_id_from,
        capture_result=capture_result,
    )

    def decorator(target):
        set_metadata(AUDITED_METADATA, spec)(target)
        return target

    return decorator


def get_audit_spec(target) -> AuditSpec | None:
    """Look up the :class:`AuditSpec` on a handler or its owning class.
    Handler-level wins over controller-level; a plain read to keep the
    interceptor's hot path cheap."""
    return get_metadata(AUDITED_METADATA, target, None)
