"use client";

import Image from "next/image";
import Link from "next/link";
import { Menu, Search } from "lucide-react";
import { cn } from "@/lib/cn";
import { GithubIcon } from "./icons";
import { useNav } from "./nav-context";
import { ThemeToggle } from "./theme-toggle";

export function Navbar({ onMenu, onSearch }) {
  const { sections, active } = useNav();

  return (
    <header className="navbar-wrap">
      <nav className="navbar" aria-label="Primary">
        <button type="button" className="icon-btn menu-btn" aria-label="Open navigation" onClick={onMenu}>
          <Menu size={19} />
        </button>

        <Link href="/" className="brand">
          <Image src="/icon.svg" alt="" width={26} height={26} priority />
          <span>Austial</span>
          <em>docs</em>
        </Link>

        <ul className="section-tabs">
          {sections.map((s) => (
            <li key={s.id}>
              <Link href={s.href} className={cn("section-tab", s.id === active.id && "active")} aria-current={s.id === active.id ? "true" : undefined}>
                {s.label}
              </Link>
            </li>
          ))}
        </ul>

        <div className="nav-actions">
          <button type="button" className="search-btn" onClick={onSearch} aria-label="Search the documentation">
            <Search size={16} aria-hidden />
            <span className="search-btn-label">Search</span>
            <kbd>⌘K</kbd>
          </button>
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
