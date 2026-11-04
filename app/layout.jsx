import { Geist_Mono, Manrope } from "next/font/google";
import { getPageMap } from "nextra/page-map";
import { ThemeProvider } from "next-themes";
import { Shell } from "@/components/shell";
import { SiteFooter } from "@/components/site-footer";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono", display: "swap" });

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

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#080606" },
    { media: "(prefers-color-scheme: light)", color: "#faf8f6" },
  ],
};

export default async function RootLayout({ children }) {
  const pageMap = await getPageMap();
  return (
    <html lang="en" dir="ltr" suppressHydrationWarning className={`${manrope.variable} ${geistMono.variable}`}>
      <body>
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <Shell pageMap={pageMap} footer={<SiteFooter />}>
            {children}
          </Shell>
        </ThemeProvider>
      </body>
    </html>
  );
}
