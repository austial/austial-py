"""Naming helpers shared by every generator -- turns whatever the user typed
(``cats``, ``cat-breed``, ``CatBreed``, ``cat_breed``) into the forms needed
for file names, class names and route prefixes, mirroring how ``nest g``
normalizes its ``<name>`` argument."""

from __future__ import annotations

import re

_BOUNDARY_RE = re.compile(r"[-_\s]+|(?<=[a-z0-9])(?=[A-Z])")


def _words(name: str) -> list[str]:
    return [w for w in _BOUNDARY_RE.split(name.strip()) if w]


def to_snake_case(name: str) -> str:
    return "_".join(w.lower() for w in _words(name))


def to_kebab_case(name: str) -> str:
    return "-".join(w.lower() for w in _words(name))


def to_pascal_case(name: str) -> str:
    return "".join(w.capitalize() for w in _words(name))


def to_camel_case(name: str) -> str:
    words = _words(name)
    if not words:
        return name
    return words[0].lower() + "".join(w.capitalize() for w in words[1:])
