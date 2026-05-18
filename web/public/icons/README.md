# PWA icons

This directory holds icons referenced by `web/public/manifest.webmanifest` and
`web/app/layout.tsx`.

## What's here today (v0 placeholder)

- `icon.svg` — single-file placeholder used as a maskable / any-purpose icon at
  192×192 and 512×512 via `manifest.webmanifest`. Identifiable at small sizes
  (basketball + "M" in NBA red on cream).

SVG icons are valid per the Web App Manifest spec and most modern PWA installers
respect them (Chrome on Android, Edge, desktop Chrome). iOS Safari, however,
historically prefers a raster `apple-touch-icon.png` — without one, iOS will
fall back to a screenshot of the page when "Add to Home Screen" is used.

## What's missing — drop these in before public launch

To unlock first-class install UX everywhere, replace this directory with:

| File                      | Size        | Purpose                                       |
| ------------------------- | ----------- | --------------------------------------------- |
| `icon-192.png`            | 192×192     | Android/Chrome install icon                   |
| `icon-512.png`            | 512×512     | Android/Chrome splash + maskable icon         |
| `apple-touch-icon.png`    | 180×180     | iOS home-screen icon (Safari)                 |
| `icon-maskable-512.png`   | 512×512     | Adaptive icon on Android (safe zone padded)   |

Suggested generation paths:

- Hand-design in Figma/Sketch from `icon.svg` and export PNGs.
- Or pass `icon.svg` through <https://realfavicongenerator.net/> for the full
  raster bundle, then commit the resulting files here.

After dropping in raster icons, update `manifest.webmanifest` to reference the
PNGs (and add a `purpose: "maskable"` variant for Android adaptive icons), and
update the `<link rel="apple-touch-icon">` declaration in `web/app/layout.tsx`
(currently pointed at `icon.svg`).

## Why we ship without raster icons in v0

Per the v0 plan (U13), real branding is post-v0 polish. The PWA still works as
a regular web app today; the only loss is a slightly worse install affordance
on iOS until the raster set lands.
