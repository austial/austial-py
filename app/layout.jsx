/* eslint-env node */
import { Footer, Layout, Navbar } from "nextra-theme-docs";
import { Head } from "nextra/components";
import { getPageMap } from "nextra/page-map";
import "nextra-theme-docs/style.css";
import "./globals.css";

export const metadata = {
  metadataBase: new URL("https://docs.austial.com"),
  title: {
    default: "Austial",
    template: "%s - Austial",
  },
  description:
    "Austial: a NestJS-style, batteries-included web framework for Python, built on top of FastAPI.",
  applicationName: "Austial",
  generator: "Next.js",
  appleWebApp: {
    title: "Austial",
  },
  other: {
    "msapplication-TileColor": "#0a0a0a",
  },
  icons: {
    icon: "/icon.svg",
  },
};

const logo = (
  <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
    <img src="/icon.svg" alt="" width={24} height={24} />
    <b>Austial</b>
  </span>
);

const navbar = (
  <Navbar
    logo={logo}
    projectLink="https://github.com/austial/austial-py"
  />
);

const footer = (
  <Footer>
    <span>
      MIT {new Date().getFullYear()} &copy;{" "}
      <a href="https://github.com/austial" target="_blank" rel="noreferrer">
        Austial
      </a>
      . Docs for{" "}
      <a
        href="https://github.com/austial/austial-py"
        target="_blank"
        rel="noreferrer"
      >
        austial-py
      </a>
      .
    </span>
  </Footer>
);

export default async function RootLayout({ children }) {
  const pageMap = await getPageMap();
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head />
      <body>
        <Layout
          navbar={navbar}
          pageMap={pageMap}
          docsRepositoryBase="https://github.com/austial/austial-py-doc/blob/main"
          editLink="Edit this page on GitHub"
          sidebar={{ defaultMenuCollapseLevel: 1, toggleButton: true }}
          footer={footer}
        >
          {children}
        </Layout>
      </body>
    </html>
  );
}
