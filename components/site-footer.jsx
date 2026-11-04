const links = [
  ["Home", "https://austial.com"],
  ["GitHub", "https://github.com/austial/austial-py"],
  ["PyPI", "https://pypi.org/project/austial/"],
  ["llms.txt", "/llms.txt"],
  ["AGENTS.md", "/AGENTS.md"],
];

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p>
        MIT {new Date().getFullYear()} &copy; Austial. Docs for{" "}
        <a href="https://github.com/austial/austial-py" target="_blank" rel="noreferrer">
          austial-py
        </a>
        .
      </p>
      <ul>
        {links.map(([label, href]) => (
          <li key={label}>
            <a href={href} {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
              {label}
            </a>
          </li>
        ))}
      </ul>
    </footer>
  );
}
