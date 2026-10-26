import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { AppLoader } from "./components/loading-spinner";
import { ThemeProvider } from "./components/theme-provider";
import "./globals.css";
import "./markdown.css";

const resolveMetadataBase = () => {
  const configuredSiteUrl = process.env.NEXT_PUBLIC_SITE_URL?.trim();
  if (!configuredSiteUrl) {
    return undefined;
  }

  try {
    return new URL(configuredSiteUrl);
  } catch {
    return undefined;
  }
};

const metadataBase = resolveMetadataBase();

// Inter for all text (owner, 2026-10-26; it was Mulish), the font upstream
// uses. Served from this site, from a pinned npm package, so
// neither a build nor a visit contacts Google. The "latin" file covers English
// and the accented letters of Spanish and Portuguese; other scripts fall back
// to system fonts.
const inter = localFont({
  src: "../node_modules/@fontsource-variable/inter/files/inter-latin-wght-normal.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--font-inter",
});

const TITLE = "Instructor Assistant";
const DESCRIPTION =
  "Instructor Assistant helps BYU-Pathway online instructors find answers about teaching, course administration, student support, and instructor policies.";

export const metadata: Metadata = {
  metadataBase,
  title: TITLE,
  description: DESCRIPTION,
  applicationName: TITLE,
  keywords: [
    "Instructor Assistant",
    "BYU-Pathway",
    "online instructors",
    "adjunct faculty",
    "Canvas",
  ],
  manifest: "/site.webmanifest",
  alternates: {
    canonical: "/",
  },
  icons: {
    icon: [{ url: "/favicon.ico", type: "image/x-icon", sizes: "16x16" }],
    shortcut: ["/favicon.ico"],
    apple: [
      { url: "/apple-touch-icon.png", type: "image/png", sizes: "180x180" },
    ],
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    type: "website",
    url: "/",
    siteName: TITLE,
    locale: "en_US",
    images: [
      {
        url: "/byu-pathway-og-image.jpg",
        width: 1193,
        height: 630,
        alt: "Instructor Assistant by BYU-Pathway",
        type: "image/jpeg",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/byu-pathway-og-image.jpg"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAF9F5" },
    { media: "(prefers-color-scheme: dark)", color: "#0A0A0A" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning className={inter.variable}>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              try {
                const theme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
                document.documentElement.classList.add(theme);
              } catch (e) {}
            `,
          }}
        />
      </head>
      <body>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <AppLoader>{children}</AppLoader>
        </ThemeProvider>
      </body>
    </html>
  );
}
