import { DocFooter } from "./doc-footer";
import { DocHeader } from "./doc-header";
import { Toc } from "./toc";

/**
 * Wraps every MDX page (Nextra hands it `toc` and `metadata`). Search only
 * indexes the body, not the breadcrumbs or pager.
 */
export function DocWrapper({ children, toc, metadata }) {
  return (
    <div className="doc-grid">
      <article className="doc">
        <DocHeader />
        <div className="doc-body" data-pagefind-body>
          {children}
        </div>
        <DocFooter filePath={metadata?.filePath} />
      </article>
      <Toc toc={toc} />
    </div>
  );
}
