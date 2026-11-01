"""``SignedUrlService`` -- short-lived HMAC-signed URL fragments.

The framework does not know the product's public base URL, so this service
issues a *URL fragment* (``?exp=...&sig=...``) that the product joins onto
its own ``StorageController``'s route (e.g. ``/files/{key}?exp=...&sig=...``).
``verify`` accepts either a full URL or just the fragment; the product
controller passes the request URL through and this service validates it.

The signature is HMAC-SHA256 over ``method\\nkey\\nexp``, truncated to 24
bytes and URL-safe-base64 encoded. That gives:

- authenticity (only holders of the secret can mint URLs);
- expiry (exp is signed, not a client claim);
- method binding (a ``GET`` URL cannot be replayed as ``PUT``);
- key binding (a URL for ``a.pdf`` cannot fetch ``b.pdf``).

Verification uses :func:`hmac.compare_digest` for constant-time equality.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlparse

from austial.common.decorators.injectable import Injectable
from austial.storage.errors import InvalidSignedUrlError

_EXP_PARAM = "exp"
_SIG_PARAM = "sig"
_METHOD_PARAM = "m"


@Injectable()
class SignedUrlService:
    """HMAC-signed URL issuer/verifier."""

    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError("SignedUrlService secret must be at least 32 characters")
        self._secret = secret.encode("utf-8")

    # ------------------------------------------------------------------ mint

    def issue(self, key: str, *, ttl: timedelta, method: str = "GET") -> str:
        """Return a URL fragment ``?exp=<unix>&m=<method>&sig=<b64>``.

        The caller (typically a ``StorageController``) prepends the base URL
        and the key-derived path.
        """

        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if ttl.total_seconds() <= 0:
            raise ValueError("ttl must be positive")
        method_up = method.upper()
        exp = int((datetime.now(tz=UTC) + ttl).timestamp())
        sig = self._sign(method_up, key, exp)
        return f"?{_EXP_PARAM}={exp}&{_METHOD_PARAM}={method_up}&{_SIG_PARAM}={sig}"

    # ------------------------------------------------------------------ verify

    def verify(self, url_or_fragment: str, expected_key: str, method: str) -> None:
        """Raise :class:`InvalidSignedUrlError` if the URL is not authentic,
        is expired, or was issued for a different key/method."""

        try:
            params = _parse_query(url_or_fragment)
            exp = int(params[_EXP_PARAM])
            sig = params[_SIG_PARAM]
            signed_method = params.get(_METHOD_PARAM, "GET")
        except (KeyError, ValueError) as exc:
            raise InvalidSignedUrlError("malformed signed URL") from exc

        if signed_method.upper() != method.upper():
            raise InvalidSignedUrlError("signed URL method mismatch")

        expected = self._sign(signed_method.upper(), expected_key, exp)
        if not hmac.compare_digest(sig, expected):
            raise InvalidSignedUrlError("signed URL signature mismatch")

        if exp <= int(datetime.now(tz=UTC).timestamp()):
            raise InvalidSignedUrlError("signed URL expired")

    # ------------------------------------------------------------------ internal

    def _sign(self, method: str, key: str, exp: int) -> str:
        message = f"{method}\n{key}\n{exp}".encode()
        digest = hmac.new(self._secret, message, hashlib.sha256).digest()[:24]
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _parse_query(url_or_fragment: str) -> dict[str, str]:
    """Accept either a full URL or a bare ``?exp=...&sig=...`` fragment."""

    query = url_or_fragment[1:] if url_or_fragment.startswith("?") else urlparse(url_or_fragment).query
    return dict(parse_qsl(query, keep_blank_values=False))
