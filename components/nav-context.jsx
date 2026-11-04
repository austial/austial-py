"use client";

import { createContext, useContext, useMemo } from "react";
import { usePathname } from "next/navigation";
import { normalizePages } from "nextra/normalize-pages";
import { buildSections, findSection } from "@/lib/nav";

const NavContext = createContext(null);

/** Navigation state derived from Nextra's page map and the current route. */
export function NavProvider({ pageMap, children }) {
  const pathname = usePathname() || "/";

  const value = useMemo(() => {
    const normalized = normalizePages({ list: pageMap, route: pathname });
    const sections = buildSections(normalized.docsDirectories);
    const flat = normalized.flatDocsDirectories;
    return {
      pathname,
      sections,
      active: findSection(sections, pathname),
      flat,
      index: normalized.activeIndex,
      current: flat[normalized.activeIndex],
      previous: flat[normalized.activeIndex - 1],
      next: flat[normalized.activeIndex + 1],
    };
  }, [pageMap, pathname]);

  return <NavContext.Provider value={value}>{children}</NavContext.Provider>;
}

export function useNav() {
  const value = useContext(NavContext);
  if (!value) throw new Error("useNav must be used inside <NavProvider>");
  return value;
}
