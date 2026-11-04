# austial-py-doc

Documentation site for [Austial](https://github.com/austial/austial-py) --
a NestJS-style, batteries-included web framework for Python built on
FastAPI. Published at **docs.austial.com**.

Built with [Next.js](https://nextjs.org/) and [Nextra](https://nextra.site/)
core. Nextra provides the MDX pipeline, page map and search index; the shell
(navbar, accordion sidebar, "On this page" rail, search modal,
"Copy page" menu) is our own layout in `components/`, themed in plain CSS in
`app/globals.css`. Content is MDX under `content/`.

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
│   ├── layout.jsx                  # fonts, theme provider, <Shell>
│   ├── globals.css                 # the whole theme: tokens, layout, prose, code
│   └── [[...mdxPath]]/page.jsx     # catch-all route rendering content/**.mdx
├── components/
│   ├── shell.jsx, navbar.jsx       # floating navbar, mobile drawer
│   ├── sidebar.jsx, toc.jsx        # accordion sidebar, "On this page" scroll-spy
│   ├── search.jsx                  # Cmd/Ctrl+K modal on the Pagefind index
│   ├── doc-wrapper.jsx             # per-page header, body, pager, edit link
│   ├── page-actions.jsx            # "Copy page" and "Open in Claude / ChatGPT"
│   └── mdx/                        # code blocks, Tabs, Callout, Cards, headings
├── lib/nav.js                      # builds the sidebar tree and accordion groups from the page map
├── content/                        # all documentation pages (MDX)
│   ├── _meta.js                    # top-level ordering and titles
│   ├── index.mdx                   # Introduction
│   ├── first-steps.mdx
│   ├── overview/ fundamentals/ techniques/ ai/ cli/
├── scripts/
│   └── generate-agent-files.mjs    # builds llms.txt, llms-full.txt, md/, AGENTS.md, setup-agents.sh
├── mdx-components.js
├── next.config.mjs
└── package.json
```

### Theme and navigation

- Colours, fonts and spacing are CSS variables at the top of `app/globals.css`
  (`:root` is the light theme, `.dark` the dark one). The accent is `--accent`.
- The sidebar is an accordion built from the page map in `lib/nav.js`. Top-level pages
  are plain links and every top-level folder under `content/` is a group (one open at a
  time; the group holding the current page opens itself). Titles and order come from each
  `_meta.js`, so a new folder shows up as a new group with no code change.
- The selected page, and the group that contains it, are marked with an accent underline.
- The whole sidebar collapses with the panel button in the navbar (or the `[` key) and the
  choice is remembered.
- Import `Tabs`, `Callout` and `Cards` in MDX from `@/components/mdx`. Tab groups
  with the same options (for example uv / pipx / pip) share one remembered choice.

Each folder under `content/` has its own `_meta.js` controlling sidebar
title/order -- see [Nextra's `_meta` file docs](https://nextra.site/docs/file-conventions/meta-file)
for the full format.

## Agent files

`npm run dev` and `npm run build` first run `scripts/generate-agent-files.mjs`,
which writes git-ignored files into `public/`:

| File | Source |
|---|---|
| `llms.txt` | page titles and summaries, in sidebar order |
| `llms-full.txt` | every page concatenated as plain text |
| `md/<route>.md` | each page as clean markdown (powers "Copy page" and "Open in AI") |
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
