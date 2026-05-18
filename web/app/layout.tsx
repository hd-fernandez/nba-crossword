import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { SwRegister } from "@/components/SwRegister";

/**
 * Site metadata + PWA hooks.
 *
 * Next 16 surfaces the manifest, icon, and apple-touch-icon links from this
 * object so we don't have to render `<link>` tags by hand. `themeColor` lives
 * on the separate `viewport` export per the App Router contract — putting it
 * on `metadata` is silently ignored.
 *
 * `manifest` is a same-origin path, served as a static asset out of
 * `public/manifest.webmanifest`.
 *
 * Icons today point at the SVG placeholder (see `public/icons/README.md` for
 * the raster set we should drop in before public launch).
 */
export const metadata: Metadata = {
  title: "The NBA Mini",
  description: "A daily 5×5 NBA mini crossword.",
  applicationName: "The NBA Mini",
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icons/icon.svg", type: "image/svg+xml" },
    ],
    apple: [
      // iOS Safari prefers a raster apple-touch-icon. Pointing at the SVG is
      // a best-effort placeholder; see public/icons/README.md.
      { url: "/icons/icon.svg", type: "image/svg+xml" },
    ],
  },
  appleWebApp: {
    capable: true,
    title: "NBA Mini",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#c8102e",
  // Disable user scaling on the puzzle grid: a double-tap to zoom in the
  // middle of solving is far more annoying than helpful. The grid sizes
  // itself in CSS to be readable on small screens.
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        {/* Registers /sw.js once on mount. Renders nothing. */}
        <SwRegister />
      </body>
    </html>
  );
}
