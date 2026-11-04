import Link from "next/link";
import { CopyButton } from "./copy-button";

/* Element overrides for MDX: headings with anchors, links, code blocks, tables. */

function heading(Tag) {
  return function Heading({ id, children, ...props }) {
    return (
      <Tag id={id} {...props}>
        {children}
        {id && (
          <a href={`#${id}`} className="anchor" aria-label="Link to this section">
            #
          </a>
        )}
      </Tag>
    );
  };
}

export const h1 = heading("h1");
export const h2 = heading("h2");
export const h3 = heading("h3");
export const h4 = heading("h4");

export function a({ href = "", children, ...props }) {
  if (href.startsWith("/") || href.startsWith("#")) {
    return (
      <Link href={href} {...props}>
        {children}
      </Link>
    );
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" {...props}>
      {children}
    </a>
  );
}

export function pre({
  children,
  "data-filename": filename,
  "data-language": language,
  "data-copy": _copy,
  "data-word-wrap": _wrap,
  ...props
}) {
  return (
    <div className="codeblock" data-language={language} data-pagefind-ignore="all">
      {filename && <div className="code-title">{filename}</div>}
      <pre {...props} tabIndex={0}>
        {children}
      </pre>
      <CopyButton />
    </div>
  );
}

export function table(props) {
  return (
    <div className="table-wrap">
      <table {...props} />
    </div>
  );
}
