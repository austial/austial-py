# Austial docs site

Documentation for the Austial framework (`../austial-py`), published at docs.austial.com. Next.js +
Nextra; content is MDX under `content/`. See `README.md` for the layout and theming.

## Commands

```bash
npm ci
npm run dev       # http://localhost:3000 (regenerates the agent files first)
npm run build     # next build + pagefind; MUST pass before you say a docs change is done
npm run lint
```

## Rules

- **Docs follow the framework.** Every example must match the current API in `../austial-py`: check
  names and signatures in the source, not from memory. After a public API change run, in the framework
  repo, `uv run python scripts/check_docs_sync.py ../austial-py-doc/content`.
- New page = new `.mdx` file **and** an entry in that folder's `_meta.js` (that is what builds the sidebar).
- Import `Callout`, `Tabs`, `Cards` from `@/components/mdx`. Callout types: `info`, `warning`.
- Code samples are Python unless marked `bash`. Page titles go in the front matter; the first heading
  repeats it.
- Never hand-edit generated files (`public/md`, `public/llms*.txt`, `public/AGENTS.md`,
  `public/setup-agents.sh`, `public/_pagefind`): change the MDX that generates them.
- Keep "what's not implemented" lists honest: remove an item when the framework closes the gap, add one
  when you find a real gap.
- Never commit or push unless asked.
