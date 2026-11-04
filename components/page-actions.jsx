"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Copy, ExternalLink, FileText } from "lucide-react";
import { cn } from "@/lib/cn";

const SITE = "https://docs.austial.com";

/**
 * "Copy page" split button. Every page is also published as clean markdown
 * (public/md, written by scripts/generate-agent-files.mjs), so the AI links hand
 * a tool that URL instead of making it scrape HTML.
 */
export function PageActions({ pathname }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState("idle"); // idle | copied | failed
  const root = useRef(null);

  const route = pathname === "/" ? "" : pathname;
  const mdPath = `/md${route || "/index"}.md`;
  const prompt = `Read ${SITE}${route || ""} (markdown: ${SITE}${mdPath}) and help me with questions about it.`;
  const q = encodeURIComponent(prompt);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => !root.current?.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function copy() {
    try {
      const res = await fetch(mdPath);
      if (!res.ok) throw new Error(String(res.status));
      await navigator.clipboard.writeText(await res.text());
      setState("copied");
    } catch {
      setState("failed");
    }
    setOpen(false);
    setTimeout(() => setState("idle"), 1800);
  }

  return (
    <div className="page-actions" ref={root}>
      <div className="split-btn">
        <button type="button" onClick={copy} className="split-main">
          {state === "copied" ? <Check size={15} /> : <Copy size={15} />}
          <span>{state === "copied" ? "Copied" : state === "failed" ? "Could not copy" : "Copy page"}</span>
        </button>
        <button
          type="button"
          className="split-toggle"
          aria-label="More page actions"
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <ChevronDown size={15} className={cn(open && "flip")} />
        </button>
      </div>

      {open && (
        <div className="menu" role="menu">
          <button type="button" role="menuitem" onClick={copy}>
            <Copy size={15} />
            <span>
              Copy as Markdown<small>For pasting into any AI tool</small>
            </span>
          </button>
          <a role="menuitem" href={mdPath} target="_blank" rel="noreferrer">
            <FileText size={15} />
            <span>
              View as Markdown<small>The raw page text</small>
            </span>
            <ExternalLink size={13} className="menu-ext" />
          </a>
          <a role="menuitem" href={`https://claude.ai/new?q=${q}`} target="_blank" rel="noreferrer">
            <span className="menu-mark">C</span>
            <span>
              Open in Claude<small>Ask questions about this page</small>
            </span>
            <ExternalLink size={13} className="menu-ext" />
          </a>
          <a role="menuitem" href={`https://chatgpt.com/?q=${q}`} target="_blank" rel="noreferrer">
            <span className="menu-mark">G</span>
            <span>
              Open in ChatGPT<small>Ask questions about this page</small>
            </span>
            <ExternalLink size={13} className="menu-ext" />
          </a>
        </div>
      )}
    </div>
  );
}
