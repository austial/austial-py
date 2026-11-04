import Link from "next/link";
import { AlertTriangle, ArrowUpRight, Info, Lightbulb, OctagonAlert } from "lucide-react";
import { cn } from "@/lib/cn";
import { TabsClient } from "./tabs-client";

/* Components the pages import: `import { Tabs, Cards, Callout } from "@/components/mdx"`. */

export function Tabs({ items, children }) {
  return <TabsClient items={items}>{children}</TabsClient>;
}
Tabs.Tab = function Tab({ children }) {
  return <div className="tab-body">{children}</div>;
};

const CALLOUTS = {
  default: { Icon: Lightbulb, label: "Tip" },
  info: { Icon: Info, label: "Note" },
  warning: { Icon: AlertTriangle, label: "Warning" },
  important: { Icon: AlertTriangle, label: "Important" },
  error: { Icon: OctagonAlert, label: "Caution" },
};

export function Callout({ type = "default", children }) {
  const { Icon, label } = CALLOUTS[type] ?? CALLOUTS.default;
  return (
    <aside className={cn("callout", `callout-${type}`)} role="note">
      <span className="callout-icon">
        <Icon size={17} aria-label={label} />
      </span>
      <div className="callout-body">{children}</div>
    </aside>
  );
}

export function Cards({ children }) {
  return <div className="cards">{children}</div>;
}
Cards.Card = function Card({ title, href, children }) {
  return (
    <Link href={href} className="card">
      <span className="card-title">
        {title}
        <ArrowUpRight size={16} aria-hidden />
      </span>
      {children && <span className="card-body">{children}</span>}
    </Link>
  );
};
