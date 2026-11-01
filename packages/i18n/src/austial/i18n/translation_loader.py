"""``TranslationLoader`` -- reads ``<locales_dir>/<locale>/<module>.json``
into a merged ``{module: {key: value}}`` structure.

Directory layout matches the frontend convention documented in the workspace
``CLAUDE.md``: **one JSON file per module per locale**. So::

    locales/
        en/
            health.json      # {"check": {"database_label": "Database"}}
            app.json         # {"welcome": "Hello, {name}!"}
        fr/
            health.json
            app.json

is merged into::

    {
        "en": {
            "health": {"check": {"database_label": "Database"}},
            "app": {"welcome": "Hello, {name}!"},
        },
        "fr": {...},
    }

Locales are auto-discovered from the top-level directory names. Malformed
JSON files are logged and skipped -- never silently dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from austial.common.logger import Logger

_logger = Logger("I18n")


class TranslationLoader:
    """Walks ``locales_dir`` and produces the merged translation dict.

    A single load pass; product code that needs hot-reload can call
    ``load()`` again and swap the result in.
    """

    def __init__(self, locales_dir: Path):
        self.locales_dir = Path(locales_dir)

    def load(self) -> dict[str, dict[str, Any]]:
        """Scan the locales directory and return ``{locale: {module: tree}}``.

        Missing directory is not an error -- returns ``{}`` and lets the
        caller decide whether that is a fatal misconfiguration.
        """
        result: dict[str, dict[str, Any]] = {}
        if not self.locales_dir.exists() or not self.locales_dir.is_dir():
            _logger.warn(f"i18n locales directory {self.locales_dir!s} does not exist")
            return result

        for locale_dir in sorted(self.locales_dir.iterdir()):
            if not locale_dir.is_dir():
                continue
            locale = locale_dir.name
            merged: dict[str, Any] = {}
            for json_file in sorted(locale_dir.glob("*.json")):
                module_name = json_file.stem
                try:
                    with json_file.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except json.JSONDecodeError as exc:
                    _logger.warn(
                        f"i18n: skipping malformed JSON at {json_file!s} "
                        f"(line {exc.lineno}, col {exc.colno}): {exc.msg}"
                    )
                    continue
                except OSError as exc:  # pragma: no cover - unlikely once glob has matched
                    _logger.warn(f"i18n: cannot read {json_file!s}: {exc}")
                    continue

                if not isinstance(data, dict):
                    _logger.warn(f"i18n: {json_file!s} did not contain a JSON object; skipped")
                    continue
                merged[module_name] = data

            if merged:
                result[locale] = merged
        return result

    def discovered_locales(self) -> list[str]:
        """Locale codes for which at least one non-empty JSON file loaded."""
        return sorted(self.load().keys())
