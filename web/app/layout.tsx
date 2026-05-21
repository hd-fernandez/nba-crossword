import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Fraunces, Inter } from "next/font/google";

import { SwRegister } from "@/components/SwRegister";

/**
 * Typography:
 * - **Fraunces** for serif headers — high-contrast, modern, friendly.
 *   Carries our editorial identity: hint of warmth, distinctly not Times.
 * - **Inter** for everything else — clean, neutral UI sans.
 *
 * Both via `next/font/google` so they're self-hosted (no FOUT, no
 * runtime DNS), variable so weight transitions don't fall off cliffs.
 */
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-serif",
  axes: ["SOFT", "opsz"],
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

export const metadata: Metadata = {
  title: "The NBA Mini",
  description:
    "A daily basketball mini crossword. Clues refresh every morning from yesterday's NBA & WNBA discourse.",
  applicationName: "The NBA Mini",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/icons/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icons/icon.svg", type: "image/svg+xml" }],
  },
  appleWebApp: {
    capable: true,
    title: "NBA Mini",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0a0c",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable}`}>
      <body
        style={{
          margin: 0,
          fontFamily: "var(--font-sans), ui-sans-serif, system-ui, sans-serif",
          background: "#0a0a0c",
        }}
      >
        {children}
        <SwRegister />
      </body>
    </html>
  );
}
