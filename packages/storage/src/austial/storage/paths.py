"""Object-key safety helpers.

Rejects keys that could break out of the storage root -- ``..`` segments,
absolute paths, drive letters, backslashes on POSIX, null bytes and any
control character. Encapsulated here so the local driver, the S3 driver and
the ``StorageService`` all apply the exact same rule.
"""

from __future__ import annotations

from austial.storage.errors import PathTraversalError

_ALLOWED_CONTROL_CODEPOINTS = {0x09}  # tab; nothing else in ASCII controls


def assert_safe_key(key: str) -> None:
    """Raise :class:`PathTraversalError` if ``key`` is unsafe."""

    if not isinstance(key, str) or not key:
        raise PathTraversalError(key)
    if "\x00" in key:
        raise PathTraversalError(key)
    if key.startswith("/") or key.startswith("\\"):
        raise PathTraversalError(key)
    if len(key) >= 2 and key[1] == ":":  # drive letter, e.g. C:\ or C:/
        raise PathTraversalError(key)
    for ch in key:
        code = ord(ch)
        if code < 0x20 and code not in _ALLOWED_CONTROL_CODEPOINTS:
            raise PathTraversalError(key)
        if code == 0x7F:
            raise PathTraversalError(key)
    normalized = key.replace("\\", "/")
    for part in normalized.split("/"):
        if part in ("", ".", ".."):
            # empty part covers a leading slash and a trailing slash and "//" runs.
            # a trailing slash is fine (means "directory prefix") only when we're listing;
            # for a *stored* key we reject it. That's what this function is for.
            raise PathTraversalError(key)


def assert_safe_prefix(prefix: str) -> None:
    """Slightly looser than :func:`assert_safe_key`: empty is fine, and a trailing
    slash is fine. But we still reject ``..``, absolute paths and null bytes."""

    if not isinstance(prefix, str):
        raise PathTraversalError(str(prefix))
    if prefix == "":
        return
    if "\x00" in prefix:
        raise PathTraversalError(prefix)
    if prefix.startswith("/") or prefix.startswith("\\"):
        raise PathTraversalError(prefix)
    if len(prefix) >= 2 and prefix[1] == ":":
        raise PathTraversalError(prefix)
    for ch in prefix:
        code = ord(ch)
        if code < 0x20 and code not in _ALLOWED_CONTROL_CODEPOINTS:
            raise PathTraversalError(prefix)
        if code == 0x7F:
            raise PathTraversalError(prefix)
    normalized = prefix.replace("\\", "/").rstrip("/")
    for part in normalized.split("/"):
        if part in (".", ".."):
            raise PathTraversalError(prefix)
