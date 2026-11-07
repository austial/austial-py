"""Prints the next release tag (``vX.Y.Z``) from the latest ``v*`` tag and the commits since it, or nothing.

Bump rules (conventional commits): a ``type!:`` subject or a ``BREAKING CHANGE`` footer bumps major (minor while
the major is 0); ``feat`` bumps minor; anything else bumps patch. Commits containing ``[skip release]`` are
ignored; if every commit since the tag is skipped, no tag is printed.
"""

from __future__ import annotations

import re
import subprocess
import sys

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
BREAKING = re.compile(r"^\w+(\([^)]*\))?!:")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def latest_tag() -> tuple[str, tuple[int, int, int]] | None:
    for tag in git("tag", "--list", "v*", "--sort=-v:refname").split():
        match = TAG.match(tag)
        if match:
            return tag, (int(match[1]), int(match[2]), int(match[3]))
    return None


def bump(current: tuple[int, int, int], messages: list[str]) -> tuple[int, int, int] | None:
    messages = [m for m in messages if "[skip release]" not in m]
    if not messages:
        return None
    major, minor, patch = current
    if any(BREAKING.match(m.splitlines()[0]) or "BREAKING CHANGE" in m for m in messages):
        return (major, minor + 1, 0) if major == 0 else (major + 1, 0, 0)
    if any(m.startswith("feat") for m in messages):
        return major, minor + 1, 0
    return major, minor, patch + 1


def main() -> int:
    found = latest_tag()
    base, current = found if found else (None, (0, 0, 0))
    rng = f"{base}..HEAD" if base else "HEAD"
    messages = [m.strip() for m in git("log", "--format=%B%x00", rng).split("\x00") if m.strip()]
    new = bump(current, messages)
    if new is not None:
        print("v{}.{}.{}".format(*new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
