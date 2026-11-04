"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Pencil } from "lucide-react";
import { useNav } from "./nav-context";

const REPO_FILES = "https://github.com/austial/austial-py-doc/blob/master";

/** Edit link plus previous / next cards. */
export function DocFooter({ filePath }) {
  const { previous, next } = useNav();
  return (
    <footer className="doc-footer">
      {filePath && (
        <a className="edit-link" href={`${REPO_FILES}/${filePath}`} target="_blank" rel="noreferrer">
          <Pencil size={14} aria-hidden /> Edit this page on GitHub
        </a>
      )}
      <nav className="pager" aria-label="Pagination">
        {previous ? (
          <Link href={previous.route} className="pager-card prev" rel="prev">
            <span className="pager-hint">
              <ArrowLeft size={14} aria-hidden /> Previous
            </span>
            <span className="pager-title">{previous.title}</span>
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link href={next.route} className="pager-card next" rel="next">
            <span className="pager-hint">
              Next <ArrowRight size={14} aria-hidden />
            </span>
            <span className="pager-title">{next.title}</span>
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </footer>
  );
}
