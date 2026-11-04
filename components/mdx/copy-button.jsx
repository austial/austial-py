"use client";

import { useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

/** Copies the text of the sibling <pre>. */
export function CopyButton() {
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);

  async function copy(e) {
    const pre = e.currentTarget.parentElement?.querySelector("pre");
    if (!pre) return;
    try {
      await navigator.clipboard.writeText(pre.innerText.replace(/\n$/, ""));
    } catch {
      return; // clipboard blocked; the text is still selectable
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1600);
  }

  return (
    <button type="button" className="copy-btn" onClick={copy} aria-label={copied ? "Copied" : "Copy code"}>
      {copied ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}
