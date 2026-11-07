---
name: auto-release
description: How automatic PyPI releases on every push to main work, how to opt out, and how to debug a failed one. Use when changing the release pipeline, when a push to main did or did not publish, or when asked to publish on push.
---

Pushes to `main` that touch `packages/**`, `pyproject.toml` or `uv.lock` are released automatically by
`.github/workflows/auto-release.yml`:

1. `scripts/next_version.py` reads the latest `v*` tag and the commits since it: `type!:` or `BREAKING CHANGE` bumps
   major (minor while 0.x), `feat` bumps minor, anything else bumps patch. All commits `[skip release]` -> no release.
2. The workflow tags the pushed commit and runs `publish.yml` on the tag with `gh workflow run` (a tag pushed by
   `GITHUB_TOKEN` does not trigger workflows; `workflow_dispatch` does).
3. `publish.yml` runs ruff, mypy and pytest, builds every package, publishes each to PyPI through trusted publishing
   and creates the GitHub release. A failing gate means the tag exists but nothing was published.

Rules when working here:
- Write conventional commit subjects (`feat:`, `fix:`, `feat!:`); the version depends on them.
- Docs-only or CI-only changes don't touch the trigger paths. For others that shouldn't ship, put `[skip release]` in the message.
- PyPI versions are immutable. If a publish fails after some packages uploaded, do not re-tag or delete the tag: fix forward
  with a new commit (a new patch is cut). Check which jobs failed with `gh run view`.
- A new package needs its PyPI trusted publisher (owner austial, repo austial-py, workflow publish.yml, environment pypi) and a
  matrix entry in `publish.yml` BEFORE it merges, or its job fails every release.
- Check the next version locally: `python3 scripts/next_version.py`.
- Manual or major releases: use the `release` skill (it pushes a tag, which `publish.yml` still handles; `auto-release`
  skips a commit that is already tagged).
