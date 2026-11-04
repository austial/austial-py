"use client";

import { Children, isValidElement, useEffect, useId, useState } from "react";
import { cn } from "@/lib/cn";

const EVENT = "austial:tabs";

/**
 * Tab group whose choice is remembered. Every group with the same set of
 * options (e.g. uv / pipx / pip) follows the same selection, on this page and
 * on every other page you open later.
 */
export function TabsClient({ items, children }) {
  const id = useId();
  const storageKey = `austial:tabs:${items.join("|")}`;
  const panels = Children.toArray(children).filter(isValidElement);
  const [selected, setSelected] = useState(items[0]);

  useEffect(() => {
    const read = () => {
      let saved = null;
      try {
        saved = localStorage.getItem(storageKey);
      } catch {}
      if (saved && items.includes(saved)) setSelected(saved);
    };
    read();
    window.addEventListener(EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, [storageKey]); // eslint-disable-line react-hooks/exhaustive-deps

  function choose(item) {
    setSelected(item);
    try {
      localStorage.setItem(storageKey, item);
    } catch {}
    window.dispatchEvent(new Event(EVENT)); // keep the other groups on this page in sync
  }

  const index = Math.max(0, items.indexOf(selected));

  return (
    <div className="tabs">
      <div role="tablist" className="tab-list">
        {items.map((item) => (
          <button
            key={item}
            type="button"
            role="tab"
            id={`${id}-${item}`}
            aria-selected={item === selected}
            aria-controls={`${id}-panel`}
            className={cn("tab", item === selected && "active")}
            onClick={() => choose(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${items[index]}`} className="tab-panel">
        {panels[index]}
      </div>
    </div>
  );
}
