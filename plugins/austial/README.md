# Austial plugin for Claude Code

Lets anyone build an application on the [Austial](https://docs.austial.com) framework (NestJS-style Python on FastAPI) with Claude Code.

## Install

```text
/plugin marketplace add austial/austial-py
/plugin install austial@austial
```

## What you get

| Piece | Use |
|---|---|
| `austial:build-app` | `/austial:build-app <idea>`: requirements, scaffold, generate, wire database and auth, tests, verify, run it |
| `austial:add-feature` | `/austial:add-feature <capability>`: auth, tenancy, jobs, schedule, WebSockets, GraphQL, microservices, CQRS, cache, Mongo, ... |
| `austial:review-app` | `/austial:review-app`: the production checklist applied to your diff, with evidence |
| `austial-framework` (automatic) | The rules, import map and pitfalls, loaded whenever a project imports `austial` |
| `austial-builder` agent | A sub-agent that knows the framework and verifies before it says "done" |

The framework skill bundles `AGENTS.md` from the docs; for anything newer the skills fetch https://docs.austial.com/llms-full.txt.

## Keeping it current

`skills/austial-framework/AGENTS.md` is a copy of https://docs.austial.com/AGENTS.md. Refresh it with `python scripts/sync_plugin.py`.
