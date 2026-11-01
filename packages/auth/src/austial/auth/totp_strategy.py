"""``TotpStrategy`` -- RFC 6238 TOTP for multi-factor authentication.

Generates enrolment secrets, builds the ``otpauth://`` provisioning URI (the QR-code
payload authenticators consume), verifies 6-digit codes with a one-window drift
allowance, and produces recovery codes for the account-recovery flow.

The secret is *not* stored by this class; the product persists it against the user
record. Every method here is pure/stateless so it is trivial to unit-test.
"""

from __future__ import annotations

import secrets

import pyotp

from austial.common.decorators.injectable import Injectable


@Injectable()
class TotpStrategy:
    """RFC 6238 TOTP -- 30-second step, SHA-1 digest, 6-digit codes."""

    def __init__(self, *, issuer: str, digits: int = 6, interval_seconds: int = 30, window: int = 1) -> None:
        self._issuer = issuer
        self._digits = digits
        self._interval = interval_seconds
        # ``window`` is the number of intervals on either side of "now" we accept, to
        # absorb clock drift on the client. 1 = ±30 seconds; do not exceed 2 (per ASVS).
        self._window = min(window, 2)

    def generate_secret(self) -> str:
        """Return a fresh base32-encoded secret to persist for the user."""
        return pyotp.random_base32()

    def provisioning_uri(self, secret: str, account_name: str) -> str:
        """Return the ``otpauth://totp/...`` URI the authenticator app scans."""
        totp = pyotp.TOTP(secret, digits=self._digits, interval=self._interval)
        return totp.provisioning_uri(name=account_name, issuer_name=self._issuer)

    def verify(self, secret: str, code: str) -> bool:
        """Constant-time TOTP verification with one-window drift allowance."""
        if not code or not code.isdigit() or len(code) != self._digits:
            return False
        totp = pyotp.TOTP(secret, digits=self._digits, interval=self._interval)
        return totp.verify(code, valid_window=self._window)

    def generate_recovery_codes(self, count: int = 10, *, group_size: int = 5) -> list[str]:
        """Return ``count`` cryptographically-random single-use recovery codes.

        Codes are grouped for human readability (``ABCDE-FGHIJ``); persist them **hashed**
        (via ``Argon2Hasher``) so that a database leak does not compromise them."""
        codes: list[str] = []
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous glyphs
        for _ in range(count):
            raw = "".join(secrets.choice(alphabet) for _ in range(group_size * 2))
            codes.append(f"{raw[:group_size]}-{raw[group_size:]}")
        return codes
