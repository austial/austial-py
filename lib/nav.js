/**
 * Documentation sections. Each becomes a tab in the navbar and owns its own
 * sidebar, so readers see one short list instead of the whole tree.
 *
 * `roots` are top-level pages (by file name) pulled in ahead of the folder's
 * own pages; `folders` are content/ directories whose pages follow.
 */
export const SECTIONS = [
  { id: "overview", label: "Overview", roots: ["index", "first-steps"], folders: ["overview"] },
  { id: "fundamentals", label: "Fundamentals", roots: [], folders: ["fundamentals"] },
  { id: "techniques", label: "Techniques", roots: [], folders: ["techniques"] },
  { id: "ai", label: "AI Agents", roots: [], folders: ["ai"] },
  { id: "cli", label: "CLI", roots: [], folders: ["cli"] },
];

const slim = (d) => ({
  title: typeof d.title === "string" ? d.title : String(d.name),
  route: d.route,
  children: d.children?.length ? d.children.map(slim) : undefined,
});

/** Turn Nextra's normalised docs tree into [{ id, label, href, items }] per section. */
export function buildSections(docsDirectories) {
  const byName = new Map(docsDirectories.map((d) => [d.name, d]));
  return SECTIONS.map((section) => {
    const items = [];
    for (const name of section.roots) {
      const page = byName.get(name);
      if (page) items.push(slim(page));
    }
    for (const name of section.folders) {
      const folder = byName.get(name);
      if (folder?.children) items.push(...folder.children.map(slim));
    }
    return { id: section.id, label: section.label, items, href: items[0]?.route ?? "/" };
  }).filter((section) => section.items.length > 0);
}

function containsRoute(items, pathname) {
  return items.some((item) => item.route === pathname || (item.children && containsRoute(item.children, pathname)));
}

/** The section whose pages include `pathname` (falls back to the first). */
export function findSection(sections, pathname) {
  return sections.find((section) => containsRoute(section.items, pathname)) ?? sections[0];
}
