"""``I18nContext`` -- request-scoped current locale.

Backed by ``contextvars.ContextVar`` so the value is isolated per request even
across ``await`` points and threadpool executors. Set by ``LocaleMiddleware``
at the perimeter; read by ``I18nService.t()`` when no explicit ``locale=`` is
passed, and by any product code that needs to know "what language did this
request come in on".

The class-level API (``I18nContext.get()`` / ``set()`` / ``reset()``) mirrors
``TenantContext`` in ``austial.tenancy`` so the two feel consistent.
"""

from __future__ import annotations

import contextvars

from austial.common.decorators.injectable import Injectable

_current_locale: contextvars.ContextVar[str | None] = contextvars.ContextVar("austial.i18n.locale", default=None)


@Injectable()
class I18nContext:
    """Injectable facade over the locale contextvar."""

    @classmethod
    def get(cls) -> str | None:
        """Return the current locale tag, or ``None`` if unset."""
        return _current_locale.get()

    @classmethod
    def require(cls) -> str:
        """Return the current locale tag, or raise ``LookupError`` when unset.

        Product code that must know the locale (e.g. formatting a currency
        amount before responding) should call this; the perimeter middleware
        guarantees a value is present when a request is in flight.
        """
        value = _current_locale.get()
        if value is None:
            raise LookupError("I18nContext is not set for the current request")
        return value

    @classmethod
    def set(cls, locale: str | None) -> contextvars.Token:
        """Set the current locale; returns a reset token."""
        return _current_locale.set(locale)

    @classmethod
    def reset(cls, token: contextvars.Token) -> None:
        _current_locale.reset(token)

    # ------------------------------------------------------------------
    # Instance helpers -- convenient when the class has been injected.

    def current(self) -> str | None:
        return _current_locale.get()

    def current_locale(self) -> str:
        return self.__class__.require()
