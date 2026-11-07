---
name: design
description: Design and implement UI changes to the Austial docs site (theme, layout, components, sidebar, navbar, search, callouts, code blocks) in the established visual language. Use for any change to app/globals.css, components/, or how pages look and behave.
argument-hint: [what to design or change]
---

Design task: $ARGUMENTS

## The visual language (do not drift from it)

Same identity as austial.com, with a docs-first layout modelled on docs.nestjs.com:

- **Accent is ember orange**, never crimson/red and never a new hue. Light `--accent: #d63d17`, dark
  `--accent: #f2542d`. It marks the active state, links, focus and primary actions, and nothing else.
  Neutrals are warm (near-black `#080606` dark, warm off-white `#faf8f6` light), not cool grey or blue.
- **Dark-first**, with a deliberate warm light theme. Themes are toggled by `next-themes` via the `.dark`
  class on `<html>`; every change must be checked in **both**.
- **Type:** Manrope for text (`--font-sans`), Geist Mono for code (`--font-mono`). No other fonts. Headings
  are bold and `--heading` coloured; body copy `--text`; secondary `--text-dim`.
- **Shape:** rounded (`--radius: 14px`, smaller radii on small controls), hairline borders
  (`--line`, `--line-strong`), soft layered `--shadow`, subtle accent glows (`--glow-a/b`) for emphasis only.
- **Navigation:** floating pill navbar; accordion sidebar with bold uppercase group headings and a
  chevron (accent and pointing up while open), the selected page an accent-tinted pill
  (`--accent-soft`, `--active-ink`); a right-hand "On this page" rail with scroll-spy. The sidebar collapses
  with a navbar button or `[`, and the choice is remembered.

## Rules

1. **Tokens, never raw values.** Colours, borders, shadows and radii come from the CSS variables at the top of
   `app/globals.css`. If you need a new tone, add a token to **both** `:root` and `.dark`. No hard-coded
   hex/rgb in components or rules (the token definitions themselves are the only place).
2. **Plain CSS in `app/globals.css`**, matching the existing sectioned layout; no CSS framework, no CSS-in-JS,
   no inline `style` except for genuinely dynamic values.
3. **Reuse before inventing.** `Callout` (`info`, `warning`, `important`, `error`), `Tabs` (shared remembered
   choice for identical options), `Cards`, code blocks with copy button, headings with anchors all live in
   `components/mdx/`. Extend those instead of adding a parallel component.
4. **Responsive by default.** Mobile first; the existing breakpoints are 640, 1024 and 1280px. The sidebar
   becomes a drawer on small screens; nothing may cause horizontal page scroll (code blocks scroll inside
   themselves).
5. **Accessible.** Keep `:focus-visible` outlines; every interactive element is reachable and operable by
   keyboard; icon-only buttons have `aria-label`; text contrast meets WCAG AA in both themes (check
   `--text-dim` on `--surface-2` and accent text on `--accent-soft`); respect `prefers-reduced-motion`
   (a global reduced-motion block exists, so new animations must be covered by it); don't rely on colour alone.
6. **Content honesty.** No invented social proof (customer logos, testimonials, sponsors, fake stats). Never
   copy NestJS's logo, mascot, imagery or brand assets: take the *layout ideas*, keep our identity.
7. **No new dependencies** for visual polish without a clear reason. Prefer CSS over JS for effects.
8. **Performance.** No layout shift (reserve space for images/fonts), no render-blocking additions; search is
   Pagefind and stays client-side.

## Workflow

1. Read the existing CSS section and component you are changing, and any sibling that solves a similar
   problem. State in one or two sentences the design intent before editing.
2. Make the change with tokens and existing components.
3. Look at it: `npm run dev`, open the affected page in the browser pane, and check **light, dark, and a ~375px
   mobile width**, plus keyboard navigation (Tab, Enter/Escape for modals, `[` for the sidebar, Cmd/Ctrl+K for
   search). Take screenshots to confirm; don't judge visual work from the code alone.
4. `npm run build` and `npm run lint` must pass.
5. Report what changed, which themes/widths you verified, and anything you could not verify. If the change
   alters the shell for every page, say so explicitly.

Never hand-edit generated files (`public/md`, `public/llms*.txt`, `public/AGENTS.md`, `public/_pagefind`).
