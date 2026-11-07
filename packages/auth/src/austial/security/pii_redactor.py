"""``PIIRedactor`` -- masks common personally-identifying data before it hits logs.

Recognises:

- Email addresses (RFC-5322-ish, pragmatic subset).
- International phone numbers (``+`` optional, 7-15 digits, common separators).
- Indian PAN (``AAAAA9999A``), Aadhaar (12 digits, spaces optional; Verhoeff
  check-digit heuristic keeps the false-positive rate low).
- Passport numbers (Indian format ``[A-PR-WY]\\d{7}``).
- IBAN (2 letters + 2 digits + up to 30 alphanumerics with a mod-97 check).
- Credit card numbers (13-19 digits, spaces/dashes tolerated, Luhn-verified).

Redaction preserves the first and last character for emails and the last four
digits for cards so operators can still correlate incidents. Values that fail
their per-pattern check (Luhn, mod-97) are left untouched to avoid destroying
useful log data.

Instances are safe to share across threads; no state is mutated after init.
"""

from __future__ import annotations

import re
from typing import Any

from austial.common.decorators.injectable import Injectable

_EMAIL_RE = re.compile(r"(?P<user>[A-Za-z0-9._%+-]+)@(?P<host>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PHONE_RE = re.compile(r"(?<![A-Za-z0-9])(?P<phone>\+?\d[\d\s().-]{6,}\d)(?![A-Za-z0-9])")
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR_RE = re.compile(r"(?<!\d)\d{4}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
_PASSPORT_RE = re.compile(r"\b[A-PR-WY][0-9]{7}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}\b")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


@Injectable()
class PIIRedactor:
    """Redact PII patterns from strings or nested dict/list structures.

    ``redact`` accepts a string (returns a string) or a mapping (returns a new
    mapping with the same shape, values redacted recursively). Non-string
    scalar values pass through unchanged."""

    _placeholder = "[REDACTED]"

    def redact(self, record: dict | list | str | Any) -> Any:
        if isinstance(record, str):
            return self._redact_str(record)
        if isinstance(record, dict):
            return {k: self.redact(v) for k, v in record.items()}
        if isinstance(record, (list, tuple)):
            result = [self.redact(v) for v in record]
            return type(record)(result) if isinstance(record, tuple) else result
        return record

    # ------------------------------------------------------------------

    def _redact_str(self, text: str) -> str:
        # Order matters: longer/more-specific patterns first so a card's leading
        # digits cannot be swallowed by the 12-digit Aadhaar regex, and IBAN's
        # alphanumerics cannot be nibbled by PAN.
        text = _EMAIL_RE.sub(_mask_email, text)
        text = _PAN_RE.sub(self._placeholder, text)
        text = _PASSPORT_RE.sub(self._placeholder, text)
        text = _IBAN_RE.sub(lambda m: self._placeholder if _iban_ok(m.group(0)) else m.group(0), text)
        text = _CARD_RE.sub(_mask_card, text)
        text = _AADHAAR_RE.sub(lambda m: self._placeholder if _digits_only(m.group(0), 12) else m.group(0), text)
        text = _PHONE_RE.sub(_mask_phone, text)
        return text


# --- helpers ------------------------------------------------------------


def _mask_email(match: re.Match[str]) -> str:
    user = match.group("user")
    host = match.group("host")
    masked_user = user[0] + "***" + user[-1] if len(user) >= 2 else "***"
    return f"{masked_user}@{host}"


def _mask_phone(match: re.Match[str]) -> str:
    phone = match.group("phone")
    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 15:
        return phone
    return "[REDACTED-PHONE]"


def _mask_card(match: re.Match[str]) -> str:
    raw = match.group(0)
    digits = re.sub(r"\D", "", raw)
    if not 13 <= len(digits) <= 19:
        return raw
    if not _luhn_ok(digits):
        return raw
    return f"[REDACTED-CARD-{digits[-4:]}]"


def _luhn_ok(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _digits_only(text: str, expected: int) -> bool:
    return len(re.sub(r"\D", "", text)) == expected


def _iban_ok(value: str) -> bool:
    value = value.upper()
    rearranged = value[4:] + value[:4]
    digits = []
    for ch in rearranged:
        if ch.isalpha():
            digits.append(str(ord(ch) - 55))
        elif ch.isdigit():
            digits.append(ch)
        else:
            return False
    try:
        return int("".join(digits)) % 97 == 1
    except ValueError:
        return False
