# Contributing to Austial

Thanks for helping. Austial aims for NestJS parity on Python, so most good contributions are "Nest has X, Austial
doesn't yet" or "Austial does X differently from Nest".

## Setup

```bash
git clone https://github.com/austial/austial-py
cd austial-py
uv sync --all-packages --group dev
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Before you open a PR

Run the same gate CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_package_boundaries.py
uv run mypy packages integration
uv run pytest
```

- **Tests first.** New behaviour comes with tests; bug fixes come with a regression test. Test files are named
  `*_spec.py` and live in each package's `test/` directory.
- **Coverage ratchet.** The floor in `pyproject.toml` (`fail_under`) only goes up.
- **Package boundaries.** A distribution may only import from the ones it depends on
  (`scripts/check_package_boundaries.py` enforces this).
- **Public API changes** are exported from their package and from `austial/__init__.py`, and documented in
  [`austial/austial-py-doc`](https://github.com/austial/austial-py-doc) (CI flags drift).
- **Name the Nest feature** your change mirrors, if there is one.

## Commits and releases

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
`docs:`, `chore:`, `refactor!:` for breaking changes). Versions come from git tags via hatch-vcs and releases
are cut automatically from merged commits, so never edit a version number by hand. Add `[skip release]` to
commits that should not trigger a release (docs, CI, repo config).

## Finding something to work on

Look for [`good first issue`](https://github.com/austial/austial-py/labels/good%20first%20issue) and
[`help wanted`](https://github.com/austial/austial-py/labels/help%20wanted). For anything bigger than a bug fix,
open an issue or a [discussion](https://github.com/austial/austial-py/discussions) first so we can agree on the
shape before you write it.

## Conduct

Everyone participating is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
