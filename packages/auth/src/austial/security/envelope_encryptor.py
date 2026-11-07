"""``EnvelopeEncryptor`` -- app-level column encryption with AES-256-GCM.

The wire format is a URL-safe base64 encoding of::

    b"v1:<key_version>:" || nonce (12 bytes) || ciphertext || tag (16 bytes)

The key version prefix lets a rotation swap the active KEK without a bulk
re-encrypt: old rows keep decrypting with their embedded version, new writes
use ``SecurityConfig.active_encryption_key``.

Callers pass a ``dict[str, bytes]`` of ``version -> 32-byte key``. A key that
is not exactly 32 bytes is rejected at construction (``EncryptionKeyError``).
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from austial.common.decorators.injectable import Injectable
from austial.security.errors import EncryptionKeyError

_VERSION_PREFIX = b"v1:"


@Injectable()
class EnvelopeEncryptor:
    """Symmetric app-level encryption for individual column values.

    ``encrypt`` writes with ``active_key``. ``decrypt`` reads whichever version
    the ciphertext advertises so historical rows stay readable across a key
    rotation."""

    def __init__(self, keys: dict[str, bytes], active_key: str | None) -> None:
        if not keys:
            raise EncryptionKeyError("At least one encryption key must be supplied")
        if active_key is None:
            raise EncryptionKeyError("active_encryption_key must be supplied")
        if active_key not in keys:
            raise EncryptionKeyError(f"active_encryption_key '{active_key}' is not present in keys")
        for version, material in keys.items():
            if not isinstance(material, (bytes, bytearray)) or len(material) != 32:
                raise EncryptionKeyError(f"Key '{version}' must be exactly 32 bytes (AES-256)")
        self._keys: dict[str, bytes] = {v: bytes(m) for v, m in keys.items()}
        self._active_key = active_key

    def encrypt(self, plaintext: str) -> str:
        if not isinstance(plaintext, str):
            raise TypeError("plaintext must be str")
        aesgcm = AESGCM(self._keys[self._active_key])
        nonce = os.urandom(12)
        ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        header = _VERSION_PREFIX + self._active_key.encode("ascii") + b":"
        blob = header + nonce + ciphertext_with_tag
        return base64.urlsafe_b64encode(blob).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            blob = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise EncryptionKeyError("Ciphertext is not valid base64") from exc

        if not blob.startswith(_VERSION_PREFIX):
            raise EncryptionKeyError("Ciphertext is missing the version prefix")
        remainder = blob[len(_VERSION_PREFIX) :]
        try:
            version_end = remainder.index(b":")
        except ValueError as exc:
            raise EncryptionKeyError("Ciphertext version delimiter not found") from exc

        version = remainder[:version_end].decode("ascii", errors="replace")
        payload = remainder[version_end + 1 :]
        if len(payload) < 12 + 16:  # nonce + minimum-sized tag
            raise EncryptionKeyError("Ciphertext payload is truncated")

        key = self._keys.get(version)
        if key is None:
            raise EncryptionKeyError(f"Unknown encryption key version '{version}'")

        nonce, ciphertext_bytes = payload[:12], payload[12:]
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext_bytes, None)
        except InvalidTag as exc:
            raise EncryptionKeyError("Ciphertext failed authentication") from exc
        return plaintext.decode("utf-8")

    @property
    def active_key(self) -> str:
        return self._active_key
