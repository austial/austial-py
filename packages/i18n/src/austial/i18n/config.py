"""``I18nConfig`` -- configuration passed to ``I18nModule.for_root(...)``.

Kept in its own module so ``I18nService`` and ``TranslationLoader`` can import
it without pulling in the module registration (which itself depends on the
service).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class I18nConfig:
    """Configuration for ``I18nModule.for_root(config)``.

    - ``locales_dir`` -- root directory containing ``<locale>/<module>.json``.
    - ``default_locale`` -- used when the request has no locale, and as the
      final entry of every fallback chain.
    - ``fallback_chain`` -- explicit fallback ordering per locale (e.g.
      ``{"fr-CA": ["fr"]}``). The default locale is always tried last and
      does not need to be listed.
    - ``strict`` -- when true, ``t()`` raises ``MissingTranslationError`` on
      lookups that resolve to nothing (after chain + default); otherwise the
      key itself is returned. Interpolation follows the same rule.
    - ``interpolation`` -- ``"brace"`` for ``{name}`` (the default), or
      ``"double_brace"`` for ``{{name}}`` (mirrors i18next).
    """

    locales_dir: Path
    default_locale: str = "en"
    fallback_chain: dict[str, list[str]] = field(default_factory=dict)
    strict: bool = False
    interpolation: Literal["brace", "double_brace"] = "brace"
