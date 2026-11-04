"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/cn";
import { useNav } from "./nav-context";

function containsActive(item, pathname) {
  return item.route === pathname || item.children?.some((child) => containsActive(child, pathname));
}

function Item({ item, pathname, onNavigate, depth = 0 }) {
  const hasChildren = Boolean(item.children?.length);
  const [open, setOpen] = useState(() => containsActive(item, pathname));

  if (hasChildren) {
    return (
      <li>
        <button
          type="button"
          className="side-group"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          style={{ paddingLeft: `${12 + depth * 12}px` }}
        >
          <span>{item.title}</span>
          <ChevronRight size={14} className={cn("side-chevron", open && "open")} aria-hidden />
        </button>
        {open && (
          <ul className="side-list">
            {item.children.map((child) => (
              <Item key={child.route} item={child} pathname={pathname} onNavigate={onNavigate} depth={depth + 1} />
            ))}
          </ul>
        )}
      </li>
    );
  }

  const active = item.route === pathname;
  return (
    <li>
      <Link
        href={item.route}
        onClick={onNavigate}
        className={cn("side-link", active && "active")}
        aria-current={active ? "page" : undefined}
        style={{ paddingLeft: `${12 + depth * 12}px` }}
      >
        {item.title}
      </Link>
    </li>
  );
}

/** The current section's pages. */
export function SidebarNav({ onNavigate }) {
  const { active, pathname } = useNav();
  return (
    <nav className="sidebar" aria-label={`${active.label} pages`}>
      <p className="side-label">{active.label}</p>
      <ul className="side-list">
        {active.items.map((item) => (
          <Item key={item.route} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </ul>
    </nav>
  );
}
