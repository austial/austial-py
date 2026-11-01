"""Auth-specific exceptions.

These extend Austial's ``UnauthorizedException`` so the framework's exception dispatch
maps them to ``401`` without a translation layer, but each carries a distinct type so a
product-level filter can render a different response body if it wants to.
"""

from __future__ import annotations

from austial.common.exceptions import UnauthorizedException


class AuthenticationError(UnauthorizedException):
    """Base for authentication failures."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class InvalidTokenError(AuthenticationError):
    """The token is malformed, has a bad signature, or fails claims validation."""

    def __init__(self, message: str = "Invalid token"):
        super().__init__(message)


class TokenExpiredError(AuthenticationError):
    """The token's ``exp`` claim is in the past."""

    def __init__(self, message: str = "Token expired"):
        super().__init__(message)


class MfaRequiredError(AuthenticationError):
    """A valid password was supplied but MFA verification is still pending."""

    def __init__(self, message: str = "MFA required"):
        super().__init__(message)
