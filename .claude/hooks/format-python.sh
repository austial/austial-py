#!/usr/bin/env bash
# PostToolUse hook for Edit|Write: format and lint the Python file Claude just touched.
# Formatting is applied silently. Lint errors that ruff cannot auto-fix are reported to Claude on
# stderr with exit code 2 (PostToolUse cannot undo the edit, but Claude sees the message and fixes it).
set -uo pipefail

file="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)"

case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# Generated scaffolding templates are Jinja, not Python.
case "$file" in
  */cli/templates/*) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
uv run --quiet ruff format "$file" >/dev/null 2>&1
uv run --quiet ruff check --fix --quiet "$file" >/dev/null 2>&1
if ! output="$(uv run --quiet ruff check "$file" 2>&1)"; then
  printf 'ruff found problems in %s:\n%s\n' "$file" "$output" >&2
  exit 2
fi
exit 0
