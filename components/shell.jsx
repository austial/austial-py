"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";
import { Navbar } from "./navbar";
import { NavProvider, useNav } from "./nav-context";
import { SearchModal } from "./search";
import { SidebarNav } from "./sidebar";

function Drawer({ open, onClose }) {
  const { sections, active } = useNav();

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
          <span className="side-label">Sections</span>
          <button type="button" className="icon-btn" aria-label="Close navigation" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <ul className="drawer-tabs">
          {sections.map((s) => (
            <li key={s.id}>
              <Link href={s.href} onClick={onClose} className={cn("section-tab", s.id === active.id && "active")}>
                {s.label}
              </Link>
            </li>
          ))}
        </ul>
        <SidebarNav onNavigate={onClose} />
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
        <aside className="rail" aria-label="Documentation">
          <SidebarNav />
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
