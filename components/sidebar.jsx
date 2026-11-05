"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronDown, PanelLeftClose } from "lucide-react";
import { cn } from "@/lib/cn";
import { containsRoute } from "@/lib/nav";
import { toggleSidebar } from "@/lib/sidebar-state";
import { useNav } from "./nav-context";

function PageLink({ item, pathname, onNavigate, depth = 0, root = false }) {
  const active = item.route === pathname;
  return (
    <li>
      <Link
        href={item.route}
        onClick={onNavigate}
        className={cn("side-link", root && "root", active && "active")}
        aria-current={active ? "page" : undefined}
        style={{ paddingLeft: `${12 + depth * 12}px` }}
      >
        <span className="side-text">{item.title}</span>
      </Link>
      {item.children && (
        <ul className="side-list">
          {item.children.map((child) => (
            <PageLink key={child.route} item={child} pathname={pathname} onNavigate={onNavigate} depth={depth + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

/**
 * One group open at a time. The group holding the current page starts open, and the component is
 * keyed by that group (see SidebarNav), so moving into another group opens it automatically while
 * a group you opened by hand stays as you left it.
 */
function Accordion({ groups, initialOpen, pathname, onNavigate }) {
  const [openId, setOpenId] = useState(initialOpen);

  return (
    <ul className="side-sections">
      {groups.map((group) => {
        const open = group.id === openId;
        const hasActive = containsRoute(group.items, pathname);
        return (
          <li key={group.id} className="side-section">
            <h3>
              <button
                type="button"
                className={cn("side-group", hasActive && "has-active")}
                aria-expanded={open}
                aria-controls={`side-panel-${group.id}`}
                onClick={() => setOpenId(open ? null : group.id)}
              >
                <span className="side-text">{group.label}</span>
                <ChevronDown size={16} strokeWidth={1.75} className={cn("side-chevron", open && "open")} aria-hidden />
              </button>
            </h3>
            <div className="side-panel" id={`side-panel-${group.id}`} data-open={open}>
              <div className="side-panel-inner" inert={!open}>
                <ul className="side-list">
                  {group.items.map((item) => (
                    <PageLink key={item.route} item={item} pathname={pathname} onNavigate={onNavigate} />
                  ))}
                </ul>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

/** Top-level pages, then the accordion groups. */
export function SidebarNav({ onNavigate, collapsible = false, showHead = true }) {
  const { tree, group, pathname } = useNav();
  return (
    <nav className="sidebar" aria-label="Documentation pages">
      {showHead && (
        <div className="side-head">
          <p className="side-label">Documentation</p>
          {collapsible && (
            <button
              type="button"
              className="icon-btn side-collapse"
              aria-label="Collapse sidebar"
              aria-controls="docs-rail"
              title="Collapse sidebar  ["
              onClick={toggleSidebar}
            >
              <PanelLeftClose size={16} />
            </button>
          )}
        </div>
      )}

      <ul className="side-list">
        {tree.roots.map((item) => (
          <PageLink key={item.route} item={item} pathname={pathname} onNavigate={onNavigate} root />
        ))}
      </ul>

      <Accordion
        key={group?.id ?? "none"}
        groups={tree.groups}
        initialOpen={group?.id ?? null}
        pathname={pathname}
        onNavigate={onNavigate}
      />
    </nav>
  );
}
