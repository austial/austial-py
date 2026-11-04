// Generates the machine-readable files AI tools consume, straight from content/:
//
//   public/llms.txt        page index (https://llmstxt.org format)
//   public/llms-full.txt   every page concatenated as plain text
//   public/md/<route>.md   each page on its own as clean markdown (powers the
//                          "Copy page" and "Open in AI" actions on the site)
//   public/<file>          any fenced block preceded by {/* publish: <file> */}
//                          (AGENTS.md, setup-agents.sh), so the page and the
//                          download can never drift apart
//
// Runs before `next dev` and `next build`. Output is git-ignored.

import { mkdirSync, readFileSync, readdirSync, writeFileSync, chmodSync, existsSync, rmSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const contentDir = join(root, "content");
const publicDir = join(root, "public");
const SITE = "https://docs.austial.com";

const SUMMARY =
  "Austial is a batteries-included, NestJS-style web framework for Python built on FastAPI: " +
  "modules, controllers, dependency injection, guards, pipes, interceptors, an ORM, auth, " +
  "multi-tenancy, security, jobs, storage and a CLI.";

/** Ordered [key, title] pairs from a `_meta.js` (flat string maps only). */
function readMeta(dir) {
  const file = join(dir, "_meta.js");
  if (!existsSync(file)) return [];
  const entries = [];
  for (const line of readFileSync(file, "utf8").split("\n")) {
    const m = line.match(/^\s*"?([\w-]+)"?\s*:\s*"([^"]+)"\s*,?\s*$/);
    if (m) entries.push([m[1], m[2]]);
  }
  return entries;
}

function splitFrontmatter(src) {
  const m = src.match(/^---\n([\s\S]*?)\n---\n?/);
  return m ? { front: m[1], body: src.slice(m[0].length) } : { front: "", body: src };
}

function titleOf(front, fallback) {
  const m = front.match(/^title:\s*(.+)$/m);
  return m ? m[1].replace(/^["']|["']$/g, "").trim() : fallback;
}

/** First prose paragraph after the H1, as one short plain-text sentence. */
function describe(body) {
  const lines = body.replace(/```[\s\S]*?```/g, "").split("\n");
  let i = lines.findIndex((l) => /^#\s/.test(l));
  const para = [];
  for (i = i + 1; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l || /^(import |<|\{\/\*|#|\||[-*] )/.test(l)) {
      if (para.length) break;
      continue;
    }
    para.push(l);
  }
  const text = para
    .join(" ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const sentences = text.match(/.*?[.!?](?=\s|$)/g) ?? [text];
  let out = "";
  for (const sentence of sentences) {
    out = `${out} ${sentence.trim()}`.trim();
    if (out.length >= 70) break;
  }
  return out.length > 200 ? out.slice(0, 197).trimEnd() + "..." : out;
}

/**
 * Flatten the few JSX wrappers the pages use (Tabs, Callout) into plain markdown:
 * each tab gets a bold label and its content is dedented, so code fences stay fences.
 */
function flattenJsx(body) {
  const out = [];
  let labels = [];
  let tab = 0;
  let strip = 0;
  for (const line of body.split("\n")) {
    const tabs = line.match(/^\s*<Tabs\s+items=\{\[([^\]]*)\]\}/);
    if (tabs) {
      labels = [...tabs[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
      tab = 0;
      continue;
    }
    if (/^\s*<Tabs\.Tab/.test(line)) {
      out.push("", `**${labels[tab++] ?? "Option"}**`, "");
      strip = 4;
      continue;
    }
    if (/^\s*<\/Tabs\.Tab>/.test(line)) {
      strip = 0;
      continue;
    }
    if (/^\s*<\/Tabs>/.test(line)) continue;
    if (/^\s*<Callout/.test(line)) {
      strip = 2;
      continue;
    }
    if (/^\s*<\/Callout>/.test(line)) {
      strip = 0;
      continue;
    }
    out.push(strip ? line.replace(new RegExp(`^ {1,${strip}}`), "") : line);
  }
  return out.join("\n");
}

/** Plain-text version of an MDX body: drop imports, JSX wrappers and comments. */
function toPlainText(body) {
  return flattenJsx(
    body
      .replace(/^import .*$/gm, "")
      .replace(/\{\/\*[\s\S]*?\*\/\}/g, ""),
  )
    .replace(/^\s*<Cards\.Card\s+title="([^"]+)"\s+href="([^"]+)"\s*\/>\s*$/gm, "- [$1]($2)")
    .replace(/^\s*<\/?Cards[^>]*>\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Collect pages in sidebar order: [{ section, slug, url, title, description, body }]. */
function collectPages() {
  const pages = [];
  const topMeta = readMeta(contentDir);
  for (const [key, sectionTitle] of topMeta) {
    const asFile = join(contentDir, `${key}.mdx`);
    const asDir = join(contentDir, key);
    if (existsSync(asFile)) {
      pages.push(load(asFile, "Docs", key === "index" ? "" : key, sectionTitle));
    } else if (existsSync(asDir)) {
      const known = readMeta(asDir).map(([k]) => k);
      const onDisk = readdirSync(asDir)
        .filter((f) => f.endsWith(".mdx"))
        .map((f) => f.replace(/\.mdx$/, ""));
      const ordered = [...known.filter((k) => onDisk.includes(k)), ...onDisk.filter((k) => !known.includes(k)).sort()];
      for (const slug of ordered) {
        pages.push(load(join(asDir, `${slug}.mdx`), sectionTitle, `${key}/${slug}`, slug));
      }
    }
  }
  return pages;
}

function load(file, section, slug, fallbackTitle) {
  const { front, body } = splitFrontmatter(readFileSync(file, "utf8"));
  return {
    file,
    section,
    url: `${SITE}/${slug}`.replace(/\/$/, ""),
    title: titleOf(front, fallbackTitle),
    description: front.match(/^description:\s*(.+)$/m)?.[1].replace(/^["']|["']$/g, "").trim() || describe(body),
    body,
  };
}

function buildLlmsTxt(pages) {
  const out = [`# Austial`, "", `> ${SUMMARY}`, ""];
  out.push(
    "Austial is not FastAPI, Django or NestJS. Read the page for an API before using it.",
    `The full documentation as one file is at ${SITE}/llms-full.txt.`,
    "",
  );
  let current = null;
  for (const p of pages) {
    if (p.section !== current) {
      if (current !== null) out.push("");
      current = p.section;
      out.push(`## ${current}`, "");
    }
    out.push(`- [${p.title}](${p.url})${p.description ? `: ${p.description}` : ""}`);
  }
  return out.join("\n") + "\n";
}

function buildLlmsFull(pages) {
  const parts = [`# Austial documentation`, "", `> ${SUMMARY}`, ""];
  for (const p of pages) {
    parts.push("---", "", `Source: ${p.url}`, "", toPlainText(p.body), "");
  }
  return parts.join("\n").trimEnd() + "\n";
}

// Extract an MDX "publish: <name>" comment plus the fenced block after it into public/<name>.
function publishBlocks(pages) {
  const written = [];
  const re = /\{\/\*\s*publish:\s*([\w.\-]+)\s*\*\/\}[ \t]*\n+(`{3,})[^\n]*\n([\s\S]*?)\n\2[ \t]*(?:\n|$)/g;
  for (const p of pages) {
    for (const m of p.body.matchAll(re)) {
      const [, name, , content] = m;
      const target = join(publicDir, name);
      writeFileSync(target, content + "\n");
      if (name.endsWith(".sh")) chmodSync(target, 0o755);
      written.push(name);
    }
  }
  return written;
}

// One markdown file per page, at the same path as its URL (/overview/controllers -> md/overview/controllers.md).
function writePageMarkdown(pages) {
  const mdDir = join(publicDir, "md");
  rmSync(mdDir, { recursive: true, force: true });
  for (const p of pages) {
    const route = new URL(p.url).pathname.replace(/^\/|\/$/g, "") || "index";
    const target = join(mdDir, `${route}.md`);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, `> Source: ${p.url}\n\n${toPlainText(p.body)}\n`);
  }
  return pages.length;
}

mkdirSync(publicDir, { recursive: true });
const pages = collectPages();
writeFileSync(join(publicDir, "llms.txt"), buildLlmsTxt(pages));
writeFileSync(join(publicDir, "llms-full.txt"), buildLlmsFull(pages));
const published = publishBlocks(pages);
const markdownPages = writePageMarkdown(pages);

const rel = (f) => relative(root, join(publicDir, f));
console.log(
  `agent files: ${pages.length} pages -> ${["llms.txt", "llms-full.txt", ...published].map(rel).join(", ")}, plus ${markdownPages} page files in public/md/`,
);
