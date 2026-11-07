"""``I18nService`` -- the injectable translator.

Loads the translation tree via ``TranslationLoader`` at construction (i.e.
when the DI container instantiates the provider at app startup), then
answers ``t(key, locale=..., **vars)`` lookups against an in-memory dict.

Lookup order for ``t("<module>.<subkey>", locale="fr-CA")``:

1. ``fr-CA`` translations.
2. Each locale in ``I18nConfig.fallback_chain["fr-CA"]`` (in order).
3. The ``default_locale``.
4. Failure: raise in strict mode, otherwise return the key itself.

Missing interpolation variables are substituted as ``""`` and warned about
(or raised, in strict mode). This makes it obvious in dev without turning
into a 500 in prod.
"""

from __future__ import annotations

import re
from typing import Any

from austial.common.decorators.injectable import Injectable
from austial.common.logger import Logger
from austial.i18n.config import I18nConfig
from austial.i18n.errors import MissingTranslationError
from austial.i18n.i18n_context import I18nContext
from austial.i18n.translation_loader import TranslationLoader

_logger = Logger("I18n")

_MISSING = object()


@Injectable()
class I18nService:
    def __init__(self, config: I18nConfig):
        self._config = config
        self._translations: dict[str, dict[str, Any]] = TranslationLoader(config.locales_dir).load()
        self._pattern = (
            re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
            if config.interpolation == "double_brace"
            else re.compile(r"\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}")
        )

    # ------------------------------------------------------------------
    # Public API

    def t(self, key: str, *, locale: str | None = None, **vars: Any) -> str:
        """Translate ``key`` -- e.g. ``"health.check.database_label"``.

        The first segment names the module (JSON filename); the remainder is
        a dotted path into that file's object tree. Missing keys degrade to
        the key itself unless ``strict=True``.
        """
        effective_locale = locale or I18nContext.get() or self._config.default_locale
        value = self._lookup(key, effective_locale)
        if value is _MISSING:
            if self._config.strict:
                raise MissingTranslationError(key, effective_locale)
            return key
        if not isinstance(value, str):
            # A dotted-key resolved to a subtree, not a leaf. Treat as missing.
            if self._config.strict:
                raise MissingTranslationError(key, effective_locale)
            return key
        return self._interpolate(value, vars, key=key, locale=effective_locale)

    def has(self, key: str, *, locale: str | None = None) -> bool:
        """True if ``key`` resolves to a string in ``locale`` (or the fallback
        chain, or the default locale)."""
        effective_locale = locale or I18nContext.get() or self._config.default_locale
        value = self._lookup(key, effective_locale)
        return isinstance(value, str)

    def available_locales(self) -> list[str]:
        """Locales the loader discovered on disk, sorted."""
        return sorted(self._translations.keys())

    def add_locale(self, locale: str, translations: dict[str, dict]) -> None:
        """Register or replace a locale's translations in-memory.

        For tests, hot-reload flows and unit fixtures. Not called on the
        request hot path.
        """
        self._translations[locale] = dict(translations)

    # ------------------------------------------------------------------
    # Lookup helpers

    def _lookup(self, key: str, locale: str) -> Any:
        for candidate in self._locale_chain(locale):
            value = self._lookup_in(candidate, key)
            if value is not _MISSING:
                return value
        return _MISSING

    def _locale_chain(self, locale: str) -> list[str]:
        chain: list[str] = [locale]
        for extra in self._config.fallback_chain.get(locale, []):
            if extra not in chain:
                chain.append(extra)
        if self._config.default_locale not in chain:
            chain.append(self._config.default_locale)
        return chain

    def _lookup_in(self, locale: str, key: str) -> Any:
        tree = self._translations.get(locale)
        if tree is None:
            return _MISSING
        parts = key.split(".")
        if not parts:
            return _MISSING
        node: Any = tree
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return _MISSING
            node = node[part]
        return node

    def _interpolate(self, template: str, vars: dict[str, Any], *, key: str, locale: str) -> str:
        if not vars and "{" not in template:
            return template

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in vars:
                if self._config.strict:
                    raise MissingTranslationError(f"{key}[missing var {name!r}]", locale)
                _logger.warn(f"i18n: missing interpolation variable {name!r} for {key!r} in {locale!r}")
                return ""
            return str(vars[name])

        return self._pattern.sub(_replace, template)
