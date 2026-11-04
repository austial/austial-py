"use client";

import Image from "next/image";
import Link from "next/link";
import { Menu, PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { GithubIcon } from "./icons";
import { toggleSidebar, useSidebarCollapsed } from "@/lib/sidebar-state";
import { ThemeToggle } from "./theme-toggle";

export function Navbar({ onMenu, onSearch }) {
  const collapsed = useSidebarCollapsed();

  return (
    <header className="navbar-wrap">
      <nav className="navbar" aria-label="Primary">
        <button type="button" className="icon-btn menu-btn" aria-label="Open navigation" onClick={onMenu}>
          <Menu size={19} />
        </button>

        <button
          type="button"
          className="icon-btn rail-toggle"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          aria-controls="docs-rail"
          aria-keyshortcuts="["
          title={collapsed ? "Expand sidebar  [" : "Collapse sidebar  ["}
          onClick={toggleSidebar}
        >
          {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
        </button>

        <Link href="/" className="brand">
          <Image src="/icon.svg" alt="" width={26} height={26} priority />
          <span>Austial</span>
          <em>docs</em>
        </Link>

        <button type="button" className="search-btn" onClick={onSearch}>
          <Search size={16} aria-hidden />
          <span className="search-btn-label">Search</span>
          <kbd aria-hidden>⌘K</kbd>
          <span className="sr-only"> the documentation</span>
        </button>

        <div className="nav-actions">
          <a className="nav-link" href="https://austial.com">
            austial.com
          </a>
          <a className="icon-btn" href="https://github.com/austial/austial-py" aria-label="Austial on GitHub">
            <GithubIcon size={18} />
          </a>
          <ThemeToggle />
        </div>
      </nav>
    </header>
  );
}
