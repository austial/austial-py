"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CornerDownLeft, FileText, Search } from "lucide-react";
import { cn } from "@/lib/cn";

let pagefind;
/** Pagefind's index is built after `next build`; in dev it does not exist and search says so. */
function loadPagefind() {
  pagefind ??= (async () => {
    try {
      const pf = await import(/* webpackIgnore: true */ /* turbopackIgnore: true */ "/_pagefind/pagefind.js");
      await pf.options({ baseUrl: "/" });
      return pf;
    } catch {
      return null;
    }
  })();
  return pagefind;
}

const clean = (url) => url.replace(/\.html(?=#|$)/, "").replace(/\/index(?=#|$)/, "/") || "/";

/** Mounted only while open, so every opening starts from a clean state. */
function SearchPanel({ onClose }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState({ q: "", items: [], unavailable: false });
  const [cursor, setCursor] = useState(0);

  const q = query.trim();
  const settled = found.q === q; // results on screen belong to what is typed now
  const items = settled ? found.items : [];

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  useEffect(() => {
    if (!q) return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      const pf = await loadPagefind();
      if (cancelled) return;
      if (!pf) {
        setFound({ q, items: [], unavailable: true });
        return;
      }
      const search = await pf.search(q);
      const top = await Promise.all(search.results.slice(0, 8).map((r) => r.data()));
      if (cancelled) return;
      setFound({
        q,
        unavailable: false,
        items: top.map((d) => ({
          url: clean(d.sub_results?.[0]?.url ?? d.url),
          title: d.meta?.title ?? d.url,
          excerpt: d.sub_results?.[0]?.excerpt ?? d.excerpt,
        })),
      });
      setCursor(0);
    }, 120);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [q]);

  const go = (item) => {
    onClose();
    router.push(item.url);
  };

  const onKeyDown = (e) => {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter" && items[cursor]) {
      e.preventDefault();
      go(items[cursor]);
    }
  };

  return (
    <div className="search-backdrop" onMouseDown={onClose} role="presentation">
      <div
        className="search-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Search the documentation"
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="search-field">
          <Search size={18} aria-hidden />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the docs"
            aria-label="Search"
            spellCheck={false}
            autoComplete="off"
          />
          <kbd>Esc</kbd>
        </div>

        <div className="search-results" role="listbox">
          {!q && <p className="search-empty">Type to search every page.</p>}
          {q && settled && found.unavailable && (
            <p className="search-empty">Search runs on the production build. Run `npm run build` first.</p>
          )}
          {q && settled && !found.unavailable && items.length === 0 && (
            <p className="search-empty">No results for &ldquo;{q}&rdquo;.</p>
          )}
          {items.map((r, i) => (
            <button
              key={r.url + i}
              type="button"
              role="option"
              aria-selected={i === cursor}
              className={cn("search-hit", i === cursor && "active")}
              onMouseEnter={() => setCursor(i)}
              onClick={() => go(r)}
            >
              <FileText size={16} aria-hidden />
              <span className="search-hit-text">
                <strong>{r.title}</strong>
                <span dangerouslySetInnerHTML={{ __html: r.excerpt }} />
              </span>
              {i === cursor && <CornerDownLeft size={14} aria-hidden />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function SearchModal({ open, onClose }) {
  return open ? <SearchPanel onClose={onClose} /> : null;
}
