"""``austial.i18n`` unit tests.

Covers the behaviours the app backend depends on:

- Loader picks up ``<locale>/<module>.json`` and merges into ``<module>.<key>``.
- ``t()`` resolves nested keys per locale, interpolates variables, falls back
  through the configured chain to the default locale, then to the key itself.
- ``has()`` matches ``t()`` for present/absent keys.
- ``available_locales()`` reflects what was discovered on disk.
- Strict mode raises ``MissingTranslationError`` on unknown keys / vars.
- ``LocaleMiddleware`` picks the correct tag from ``Accept-Language`` and
  honours the language-only fallback (``en-IN`` -> ``en``).
- Malformed JSON is logged (via ``Logger.warn``) but does not crash the loader.
- ``I18nContext`` is request-scoped across async tasks.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from austial.i18n import (
    I18nConfig,
    I18nContext,
    I18nService,
    LocaleMiddleware,
    MissingTranslationError,
    TranslationLoader,
    parse_accept_language,
)

# ---------------------------------------------------------------------------
# Fixtures


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture()
def locales_dir(tmp_path: Path) -> Path:
    root = tmp_path / "locales"
    _write_json(
        root / "en" / "health.json",
        {"check": {"database_label": "Database", "queue_label": "Queue"}},
    )
    _write_json(
        root / "en" / "app.json",
        {"welcome": "Hello, {name}!", "farewell": "Goodbye"},
    )
    _write_json(
        root / "fr" / "health.json",
        {"check": {"database_label": "Base de données"}},
    )
    _write_json(
        root / "fr" / "app.json",
        {"welcome": "Bonjour, {name}!"},
    )
    return root


def _service(locales_dir: Path, **overrides: Any) -> I18nService:
    config = I18nConfig(locales_dir=locales_dir, **overrides)
    return I18nService(config)


# ---------------------------------------------------------------------------
# TranslationLoader


def test_loader_discovers_locales_and_modules(locales_dir: Path):
    loaded = TranslationLoader(locales_dir).load()
    assert set(loaded.keys()) == {"en", "fr"}
    assert loaded["en"]["health"]["check"]["database_label"] == "Database"
    assert loaded["fr"]["app"]["welcome"] == "Bonjour, {name}!"


def test_loader_skips_malformed_json_without_crashing(tmp_path: Path):
    root = tmp_path / "locales"
    _write_json(root / "en" / "health.json", {"check": {"database_label": "Database"}})
    (root / "en" / "broken.json").parent.mkdir(parents=True, exist_ok=True)
    (root / "en" / "broken.json").write_text("{not valid json,,", encoding="utf-8")

    with patch("austial.i18n.translation_loader._logger") as fake_logger:
        loaded = TranslationLoader(root).load()

    assert loaded["en"] == {"health": {"check": {"database_label": "Database"}}}
    assert fake_logger.warn.called
    warned = " ".join(call.args[0] for call in fake_logger.warn.call_args_list)
    assert "broken.json" in warned


# ---------------------------------------------------------------------------
# I18nService.t / has / available_locales


def test_t_looks_up_nested_key_per_locale(locales_dir: Path):
    svc = _service(locales_dir)
    assert svc.t("health.check.database_label", locale="en") == "Database"
    assert svc.t("health.check.database_label", locale="fr") == "Base de données"


def test_t_interpolates_variables(locales_dir: Path):
    svc = _service(locales_dir)
    assert svc.t("app.welcome", locale="en", name="Alice") == "Hello, Alice!"
    assert svc.t("app.welcome", locale="fr", name="Alice") == "Bonjour, Alice!"


def test_t_falls_back_to_default_locale_when_key_missing(locales_dir: Path):
    svc = _service(locales_dir)
    # "farewell" exists in en/app.json but not fr/app.json.
    assert svc.t("app.farewell", locale="fr") == "Goodbye"


def test_t_returns_key_when_missing_everywhere(locales_dir: Path):
    svc = _service(locales_dir)
    assert svc.t("app.unknown.key", locale="fr") == "app.unknown.key"


def test_has_reports_key_presence(locales_dir: Path):
    svc = _service(locales_dir)
    assert svc.has("health.check.database_label", locale="en") is True
    assert svc.has("health.check.queue_label", locale="fr") is True  # via en fallback
    assert svc.has("nope.nada", locale="en") is False


def test_available_locales_matches_disk(locales_dir: Path):
    svc = _service(locales_dir)
    assert svc.available_locales() == ["en", "fr"]


def test_strict_mode_raises_on_missing_key(locales_dir: Path):
    svc = _service(locales_dir, strict=True)
    with pytest.raises(MissingTranslationError):
        svc.t("app.does_not_exist", locale="en")


def test_double_brace_interpolation_supported(locales_dir: Path):
    # Rewrite en/app.json to use {{name}} instead of {name}.
    (locales_dir / "en" / "app.json").write_text(json.dumps({"welcome": "Hi, {{name}}!"}), encoding="utf-8")
    svc = _service(locales_dir, interpolation="double_brace")
    assert svc.t("app.welcome", locale="en", name="Bob") == "Hi, Bob!"


def test_fallback_chain_is_honoured(tmp_path: Path):
    root = tmp_path / "locales"
    _write_json(root / "en" / "app.json", {"greeting": "Hello"})
    _write_json(root / "fr" / "app.json", {"greeting": "Bonjour"})
    _write_json(root / "fr-ca" / "app.json", {})  # empty, but "fr-ca" is present
    # fr-ca is discovered but has no keys; chain: fr-ca -> fr -> en (default).
    config = I18nConfig(locales_dir=root, default_locale="en", fallback_chain={"fr-ca": ["fr"]})
    svc = I18nService(config)
    # fr-ca discovery requires at least one non-empty file; drop it and use fresh:
    # Instead, call with explicit locale and verify the chain resolves to fr.
    assert svc.t("app.greeting", locale="fr-ca") == "Bonjour"


def test_add_locale_updates_translations_in_memory(locales_dir: Path):
    svc = _service(locales_dir)
    svc.add_locale("de", {"app": {"welcome": "Hallo, {name}!"}})
    assert "de" in svc.available_locales()
    assert svc.t("app.welcome", locale="de", name="Otto") == "Hallo, Otto!"


# ---------------------------------------------------------------------------
# I18nContext


def test_context_get_returns_none_when_unset():
    # Ensure any leftover state is cleared for this test.
    token = I18nContext.set(None)
    try:
        assert I18nContext.get() is None
    finally:
        I18nContext.reset(token)


@pytest.mark.asyncio
async def test_context_is_isolated_across_tasks():
    async def task(locale: str) -> str:
        token = I18nContext.set(locale)
        try:
            await asyncio.sleep(0)
            return I18nContext.require()
        finally:
            I18nContext.reset(token)

    seen = await asyncio.gather(task("en"), task("fr"), task("de"))
    assert sorted(seen) == ["de", "en", "fr"]


def test_t_uses_context_locale_when_none_passed(locales_dir: Path):
    svc = _service(locales_dir)
    token = I18nContext.set("fr")
    try:
        assert svc.t("health.check.database_label") == "Base de données"
    finally:
        I18nContext.reset(token)


# ---------------------------------------------------------------------------
# Accept-Language parsing + LocaleMiddleware


def test_parse_accept_language_sorts_by_q():
    tags = parse_accept_language("en-IN,en;q=0.9,fr;q=0.5")
    assert tags == ["en-IN", "en", "fr"]


def test_parse_accept_language_drops_zero_q():
    tags = parse_accept_language("en;q=0, fr;q=0.7, de;q=0.9")
    assert tags == ["de", "fr"]


@pytest.mark.asyncio
async def test_middleware_picks_language_subtag_when_full_tag_missing(locales_dir: Path):
    svc = _service(locales_dir)
    config = I18nConfig(locales_dir=locales_dir)
    middleware = LocaleMiddleware(svc, config)

    request = SimpleNamespace(
        headers={"Accept-Language": "en-IN,en;q=0.9,fr;q=0.5"},
    )

    captured: dict[str, str | None] = {}

    async def call_next() -> Any:
        captured["locale"] = I18nContext.get()
        return SimpleNamespace(status_code=200)

    response = await middleware.use(request, call_next)  # type: ignore[arg-type]
    assert response.status_code == 200
    # en-IN is not loaded, so the middleware falls back to en (its language subtag).
    assert captured["locale"] == "en"
    # And the context is torn down after the request.
    assert I18nContext.get() is None


@pytest.mark.asyncio
async def test_middleware_honours_override_header(locales_dir: Path):
    svc = _service(locales_dir)
    config = I18nConfig(locales_dir=locales_dir)
    middleware = LocaleMiddleware(svc, config)

    request = SimpleNamespace(
        headers={"X-Locale": "fr", "Accept-Language": "en"},
    )

    captured: dict[str, str | None] = {}

    async def call_next() -> Any:
        captured["locale"] = I18nContext.get()
        return SimpleNamespace(status_code=200)

    await middleware.use(request, call_next)  # type: ignore[arg-type]
    assert captured["locale"] == "fr"


@pytest.mark.asyncio
async def test_middleware_falls_back_to_default_when_nothing_matches(locales_dir: Path):
    svc = _service(locales_dir)
    config = I18nConfig(locales_dir=locales_dir, default_locale="en")
    middleware = LocaleMiddleware(svc, config)

    request = SimpleNamespace(headers={"Accept-Language": "ja,ko;q=0.5"})

    captured: dict[str, str | None] = {}

    async def call_next() -> Any:
        captured["locale"] = I18nContext.get()
        return SimpleNamespace(status_code=200)

    await middleware.use(request, call_next)  # type: ignore[arg-type]
    assert captured["locale"] == "en"
