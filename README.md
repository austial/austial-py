# austial-py-doc

Documentation site for [Austial](https://github.com/austial/austial-py) --
a NestJS-style, batteries-included web framework for Python built on
FastAPI. Published at **docs.austial.com**.

Built with [Next.js](https://nextjs.org/) + [Nextra](https://nextra.site/)
(`nextra-theme-docs`), content authored in MDX under `content/`.

## Developing

```bash
npm install
npm run dev      # http://localhost:3000
```

## Building

```bash
npm run build    # next build + pagefind search index
npm run start    # serve the production build
```

## Structure

```
austial-py-doc/
├── app/
│   ├── layout.jsx                  # nextra-theme-docs Layout, navbar, footer
│   ├── globals.css
│   └── [[...mdxPath]]/page.jsx     # catch-all route rendering content/**.mdx
├── content/                         # all documentation pages (MDX)
│   ├── _meta.js                      # top-level sidebar ordering
│   ├── index.mdx                      # Introduction
│   ├── first-steps.mdx
│   ├── overview/                       # Controllers, Providers, Modules, ...
│   ├── fundamentals/                    # Custom Providers, Dynamic Modules, ...
│   ├── techniques/                       # Configuration, Database, Testing, ...
│   ├── ai/                                # AI agent setup, reference, production checklist
│   └── cli/                               # CLI reference
├── scripts/
│   └── generate-agent-files.mjs      # builds llms.txt, llms-full.txt, AGENTS.md, setup-agents.sh
├── mdx-components.js
├── next.config.mjs
└── package.json
```

Each folder under `content/` has its own `_meta.js` controlling sidebar
title/order -- see [Nextra's `_meta` file docs](https://nextra.site/docs/file-conventions/meta-file)
for the full format.

## Agent files

`npm run dev` and `npm run build` first run `scripts/generate-agent-files.mjs`,
which writes four git-ignored files into `public/`:

| File | Source |
|---|---|
| `llms.txt` | page titles and summaries, in sidebar order |
| `llms-full.txt` | every page concatenated as plain text |
| `AGENTS.md` | the fenced block after `{/* publish: AGENTS.md */}` in `content/ai/agents-md.mdx` |
| `setup-agents.sh` | the fenced block after `{/* publish: setup-agents.sh */}` in `content/ai/setup.mdx` |

Edit the MDX pages, never the generated files. Any fenced block preceded by a
`{/* publish: <filename> */}` comment is published to `public/<filename>`.

## Contributing

Documentation should stay in lockstep with
[`austial/austial-py`](https://github.com/austial/austial-py) -- when the
framework's public API changes, update the corresponding page here in the
same PR (or a follow-up linked to it)..

## License

[MIT](./LICENSE)
