from enum import StrEnum


class Scope(StrEnum):
    """Provider scope, mirrors ``@nestjs/common``'s ``Scope``.

    Only ``DEFAULT`` (singleton, one instance per application) and
    ``TRANSIENT`` (a new instance every time it's resolved) are supported.
    Nest's ``REQUEST`` scope is intentionally not implemented in v1 -- FastAPI's
    async request model doesn't map onto it cleanly, and it's rarely needed
    outside multi-tenant setups.
    """

    DEFAULT = "DEFAULT"
    TRANSIENT = "TRANSIENT"
