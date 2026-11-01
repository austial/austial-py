"""``Argon2Hasher`` -- OWASP ASVS L2 password hashing.

Argon2id with defaults calibrated to OWASP's 2024 recommendations for interactive
authentication (>=19 MiB memory, >=2 iterations, 1 lane). The hasher is stateless and
injectable; callers use ``hash()`` at registration/password-change and ``verify()`` at
login, and check ``needs_rehash()`` to opportunistically upgrade older hashes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from austial.common.decorators.injectable import Injectable


class PasswordVerificationError(Exception):
    """Raised when the supplied password does not match the stored hash."""


@runtime_checkable
class PasswordHasher(Protocol):
    """Injectable interface: any hasher that implements these three methods
    is a drop-in replacement for ``Argon2Hasher`` (useful in tests)."""

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded: str) -> None: ...

    def needs_rehash(self, encoded: str) -> bool: ...


@Injectable()
class Argon2Hasher:
    """Argon2id password hasher. Defaults tuned to OWASP's 2024 interactive-login profile."""

    def __init__(
        self,
        *,
        time_cost: int = 2,
        memory_cost: int = 19 * 1024,  # 19 MiB, per OWASP 2024 minimum
        parallelism: int = 1,
        hash_len: int = 32,
        salt_len: int = 16,
    ) -> None:
        self._hasher = _Argon2(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
        )

    def hash(self, password: str) -> str:
        """Return a PHC-string-encoded Argon2id hash of ``password``."""
        return self._hasher.hash(password)

    def verify(self, password: str, encoded: str) -> None:
        """Verify ``password`` against ``encoded``; raise ``PasswordVerificationError``
        on any mismatch or malformed hash. Callers should treat all failures identically
        to avoid leaking why authentication failed."""
        try:
            self._hasher.verify(encoded, password)
        except (VerifyMismatchError, InvalidHashError) as exc:
            raise PasswordVerificationError("password verification failed") from exc

    def needs_rehash(self, encoded: str) -> bool:
        """True if ``encoded`` was produced with older parameters and should be rehashed
        with the current profile on next successful login. Callers should silently
        rehash + persist to keep pace with parameter upgrades."""
        return self._hasher.check_needs_rehash(encoded)
