"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowUp } from "lucide-react";
import { cn } from "@/lib/cn";

/** "On this page" rail with a scroll-spy that follows the heading in view. */
export function Toc({ toc }) {
  const items = useMemo(() => (toc ?? []).filter((h) => h.depth >= 2 && h.depth <= 3), [toc]);
  const [active, setActive] = useState(items[0]?.id);

  useEffect(() => {
    if (!items.length) return;
    const visible = new Map();
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) visible.set(e.target.id, e.isIntersecting);
        const first = items.find((h) => visible.get(h.id));
        if (first) setActive(first.id);
      },
      // a heading counts as "current" while it sits in the upper part of the screen
      { rootMargin: "-96px 0px -65% 0px" },
    );
    for (const h of items) {
      const el = document.getElementById(h.id);
      if (el) io.observe(el);
    }
    return () => io.disconnect();
  }, [items]);

  if (!items.length) return <aside className="toc" aria-hidden />;

  return (
    <aside className="toc" aria-label="On this page">
      <p className="side-label">On this page</p>
      <ul>
        {items.map((h) => (
          <li key={h.id}>
            <a href={`#${h.id}`} className={cn("toc-link", h.depth === 3 && "sub", h.id === active && "active")}>
              {h.value}
            </a>
          </li>
        ))}
      </ul>
      <button type="button" className="to-top" onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}>
        <ArrowUp size={13} aria-hidden /> Back to top
      </button>
    </aside>
  );
}
