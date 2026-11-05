/**
 * The sidebar tree, read straight from Nextra's normalised page map (so titles and order come from
 * each `_meta.js`): top-level pages are plain links, and every top-level folder becomes an accordion
 * group. Add a folder under content/ and it shows up as a new group with no code change.
 */
const slim = (d) => ({
  title: typeof d.title === "string" ? d.title : String(d.name),
  route: d.route,
  children: d.children?.length ? d.children.map(slim) : undefined,
});

/**
 * Pages that sit at the top level of content/ but read better inside a group, as on docs.nestjs.com
 * where "First steps" opens the Overview group. Only the sidebar placement changes; URLs do not.
 */
const FILE_INTO_GROUP = { "first-steps": "overview" };

export function buildTree(docsDirectories) {
  const roots = [];
  const groups = [];
  const loose = [];
  for (const entry of docsDirectories) {
    if (entry.children?.length) {
      groups.push({
        id: entry.name,
        label: typeof entry.title === "string" ? entry.title : String(entry.name),
        items: entry.children.map(slim),
      });
    } else {
      loose.push(entry);
    }
  }
  for (const entry of loose) {
    const home = groups.find((g) => g.id === FILE_INTO_GROUP[entry.name]);
    if (home) home.items.unshift(slim(entry));
    else roots.push(slim(entry));
  }
  for (const group of groups) group.href = group.items[0].route;
  return { roots, groups };
}

export function containsRoute(items, pathname) {
  return items.some((item) => item.route === pathname || (item.children && containsRoute(item.children, pathname)));
}

/** The group whose pages include `pathname`, or undefined for a top-level page. */
export function findGroup(groups, pathname) {
  return groups.find((group) => containsRoute(group.items, pathname));
}
