---
name: release
description: Cut a release of the austial packages to PyPI by tagging. Only when the user explicitly asks to release.
disable-model-invocation: true
argument-hint: [version, e.g. 0.2.0]
---

Release $ARGUMENTS. Publishing is irreversible (PyPI versions cannot be reused), so confirm with the user
before the push in step 6.

1. Preconditions: on `main`, working tree clean, up to date with `origin/main`, and the latest CI run
   on `main` is green (`gh run list --branch main --limit 1`).
2. Run `/verify` and `/sync-docs`; both must be clean.
3. Check `$ARGUMENTS` is valid semver, greater than the latest tag (`git tag --sort=-v:refname | head -3`),
   and that a breaking change bumps major (or minor while `0.x`).
4. Summarise what is in the release: `git log <last-tag>..HEAD --oneline`, grouped as features, fixes,
   breaking changes. Show it to the user.
5. Versions come from git tags via hatch-vcs: there is no version to edit in any `pyproject.toml`.
6. After explicit confirmation: `git tag -a v$ARGUMENTS -m "v$ARGUMENTS - <summary>"` then
   `git push origin v$ARGUMENTS`. This triggers `.github/workflows/publish.yml`.
7. Watch it: `gh run watch`. If a publish job fails for one package, report which; do not re-tag.
   Afterwards confirm the new version on PyPI for `austial` and `austial-core`.
