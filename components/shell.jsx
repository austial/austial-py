"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Navbar } from "./navbar";
import { NavProvider } from "./nav-context";
import { SearchModal } from "./search";
import { toggleSidebar } from "@/lib/sidebar-state";
import { SidebarNav } from "./sidebar";

function Drawer({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className={cn("drawer", open && "open")} inert={!open}>
      <div className="drawer-backdrop" onClick={onClose} />
      <div className="drawer-panel" role="dialog" aria-modal="true" aria-label="Navigation">
        <div className="drawer-head">
          <span className="side-label">Documentation</span>
          <button type="button" className="icon-btn" aria-label="Close navigation" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <SidebarNav onNavigate={onClose} showHead={false} />
      </div>
    </div>
  );
}

function ShellInner({ children, footer }) {
  const [menu, setMenu] = useState(false);
  const [search, setSearch] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      const typing = /^(input|textarea|select)$/i.test(e.target?.tagName ?? "") || e.target?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearch((v) => !v);
      } else if (e.key === "/" && !typing) {
        e.preventDefault();
        setSearch(true);
      } else if (e.key === "[" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        toggleSidebar();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <a href="#content" className="skip-link">
        Skip to content
      </a>
      <div className="ambient" aria-hidden />
      <Navbar onMenu={() => setMenu(true)} onSearch={() => setSearch(true)} />
      <div className="shell">
        <aside className="rail" id="docs-rail" aria-label="Documentation">
          <SidebarNav collapsible />
        </aside>
        <div className="content-col">
          <main id="content">{children}</main>
          {footer}
        </div>
      </div>
      <Drawer open={menu} onClose={() => setMenu(false)} />
      <SearchModal open={search} onClose={() => setSearch(false)} />
    </>
  );
}

export function Shell({ pageMap, children, footer }) {
  return (
    <NavProvider pageMap={pageMap}>
      <ShellInner footer={footer}>{children}</ShellInner>
    </NavProvider>
  );
}
