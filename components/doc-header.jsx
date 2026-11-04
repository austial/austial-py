"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { useNav } from "./nav-context";
import { PageActions } from "./page-actions";

/** Breadcrumb trail on the left, page actions on the right. */
export function DocHeader() {
  const { active, current, pathname } = useNav();
  return (
    <div className="doc-header">
      <nav aria-label="Breadcrumb" className="crumbs">
        <Link href={active.href}>{active.label}</Link>
        {current && (
          <>
            <ChevronRight size={14} aria-hidden />
            <span aria-current="page">{current.title}</span>
          </>
        )}
      </nav>
      <PageActions pathname={pathname} />
    </div>
  );
}
