"""Refresh-token store contract + in-memory reference implementation.

Refresh tokens are opaque, rotating, and revocable. The framework defines the
contract; the product supplies a persistent implementation (typically an
append-only table via ``austial.orm``) so tokens can be revoked on password
change, MFA re-enrolment, or explicit sign-out. The in-memory implementation is
useful in tests and in local dev without a database.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from austial.common.decorators.injectable import Injectable


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    """One row in a refresh-token store."""

    token_id: str
    subject: str
    expires_at: datetime
    revoked_at: datetime | None = None
    session_id: str | None = None


@runtime_checkable
class RefreshTokenStore(Protocol):
    """Inject this interface; supply an implementation from the product's persistence layer."""

    async def issue(
        self, subject: str, *, ttl: timedelta, session_id: str | None = None
    ) -> tuple[str, RefreshTokenRecord]:
        """Return ``(opaque_token, record)``. The opaque token is what the client keeps."""
        ...

    async def rotate(self, opaque_token: str, *, ttl: timedelta) -> tuple[str, RefreshTokenRecord]:
        """Revoke the presented token and issue a replacement in one atomic step.
        Raises ``LookupError`` if the token is unknown, expired, or already revoked."""
        ...

    async def revoke(self, opaque_token: str) -> None:
        """Idempotent: revoking an unknown or already-revoked token is a no-op."""
        ...

    async def revoke_all_for_subject(self, subject: str) -> int:
        """Revoke every active refresh token for ``subject``; return the count revoked."""
        ...


@Injectable()
class InMemoryRefreshTokenStore:
    """Reference implementation for tests and local dev.

    Tokens are hashed before storage (SHA-256) so a memory dump does not surrender them
    verbatim; the raw opaque token is only ever held by the caller. Not for production."""

    def __init__(self) -> None:
        self._records: dict[str, RefreshTokenRecord] = {}

    def _hash(self, opaque: str) -> str:
        import hashlib

        return hashlib.sha256(opaque.encode()).hexdigest()

    async def issue(
        self, subject: str, *, ttl: timedelta, session_id: str | None = None
    ) -> tuple[str, RefreshTokenRecord]:
        opaque = secrets.token_urlsafe(48)
        token_id = self._hash(opaque)
        record = RefreshTokenRecord(
            token_id=token_id,
            subject=subject,
            expires_at=datetime.now(UTC) + ttl,
            session_id=session_id,
        )
        self._records[token_id] = record
        return opaque, record

    async def rotate(self, opaque_token: str, *, ttl: timedelta) -> tuple[str, RefreshTokenRecord]:
        token_id = self._hash(opaque_token)
        existing = self._records.get(token_id)
        if existing is None:
            raise LookupError("unknown refresh token")
        if existing.revoked_at is not None:
            raise LookupError("refresh token already revoked")
        if existing.expires_at < datetime.now(UTC):
            raise LookupError("refresh token expired")

        self._records[token_id] = RefreshTokenRecord(
            token_id=existing.token_id,
            subject=existing.subject,
            expires_at=existing.expires_at,
            revoked_at=datetime.now(UTC),
            session_id=existing.session_id,
        )
        return await self.issue(existing.subject, ttl=ttl, session_id=existing.session_id)

    async def revoke(self, opaque_token: str) -> None:
        token_id = self._hash(opaque_token)
        existing = self._records.get(token_id)
        if existing is None or existing.revoked_at is not None:
            return
        self._records[token_id] = RefreshTokenRecord(
            token_id=existing.token_id,
            subject=existing.subject,
            expires_at=existing.expires_at,
            revoked_at=datetime.now(UTC),
            session_id=existing.session_id,
        )

    async def revoke_all_for_subject(self, subject: str) -> int:
        revoked = 0
        now = datetime.now(UTC)
        for token_id, record in list(self._records.items()):
            if record.subject == subject and record.revoked_at is None:
                self._records[token_id] = RefreshTokenRecord(
                    token_id=record.token_id,
                    subject=record.subject,
                    expires_at=record.expires_at,
                    revoked_at=now,
                    session_id=record.session_id,
                )
                revoked += 1
        return revoked
