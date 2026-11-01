"""``austial.i18n`` exceptions.

``MissingTranslationError`` is a *server* error (500): a missing key means the
locale file the deploy shipped is incomplete. Product code catches it only in
strict mode; the default (non-strict) mode returns the key as a placeholder
instead of raising, so a missing translation degrades to a visible-but-usable
label rather than a hard 500.
"""

from __future__ import annotations

from austial.common.exceptions import InternalServerErrorException


class MissingTranslationError(InternalServerErrorException):
    """Raised in strict mode when ``t(key)`` cannot be resolved."""

    def __init__(self, key: str, locale: str):
        super().__init__(f"Missing translation for {key!r} in locale {locale!r}")
        self.key = key
        self.locale = locale
