"""``austial.i18n`` -- server-side i18n.

Mirrors the frontend convention documented in the workspace ``CLAUDE.md``:
**one JSON file per module per locale**, merged by the loader into a
``<module>.<key>`` lookup namespace. Framework internals stay English --
this package is for app-level code (product backends, controllers, error
messages surfaced to end users).

Public API::

    from austial.i18n import (
        I18nModule,
        I18nConfig,
        I18nService,
        I18nContext,
        LocaleMiddleware,
        TranslationLoader,
        MissingTranslationError,
        parse_accept_language,
    )
"""

from austial.i18n.config import I18nConfig
from austial.i18n.errors import MissingTranslationError
from austial.i18n.i18n_context import I18nContext
from austial.i18n.i18n_module import I18nModule
from austial.i18n.i18n_service import I18nService
from austial.i18n.locale_middleware import LocaleMiddleware, parse_accept_language
from austial.i18n.translation_loader import TranslationLoader

__all__ = [
    "I18nConfig",
    "I18nContext",
    "I18nModule",
    "I18nService",
    "LocaleMiddleware",
    "MissingTranslationError",
    "TranslationLoader",
    "parse_accept_language",
]
