---
name: verify
description: Run the full quality gate (ruff lint, ruff format check, mypy, pytest with coverage) and report results. Use before claiming work is done, before committing, or after any change to framework code.
allowed-tools: Bash(uv run *)
---

Run the same gate CI runs, in this order, and stop at the first failure to fix it:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy packages integration`
4. `uv run pytest -q --cov --cov-report=term-missing`

Report honestly:

- Which step failed and the relevant output, if any. Do not summarise a failure as a pass.
- The total test count and the coverage percentage; flag it if coverage dropped below the
  `fail_under` in `pyproject.toml`.
- For files you changed, the uncovered lines from the coverage report, and whether they matter.

If the public API changed, also run `uv run python scripts/check_docs_sync.py ../austial-py-doc/content`.
