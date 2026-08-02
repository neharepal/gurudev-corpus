import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "गुरुदेव संग्रह — Gurudev Sangrah",
  description:
    "A guided exploration of the Nimbal sampradaya literature — verbatim quotes, not paraphrase.",
};

// Inline pre-hydration script — applies the persisted font scale to <html>
// BEFORE the first paint. Without this the reader would flash at the default
// size and then jump to the user's stored preference on hydration. Kept
// self-contained (no imports, no exceptions) so the parser never throws and
// blocks paint. Must stay in sync with `lib/fontScale.ts`.
const FONT_SCALE_HYDRATE = `
try {
  var raw = window.localStorage.getItem("gd:read:fontScale:v1");
  var scales = [0.9, 1.0, 1.15, 1.3];
  var n = raw == null ? 1 : parseInt(raw, 10);
  if (!(n >= 0 && n < scales.length)) n = 1;
  document.documentElement.style.setProperty("--app-font-scale", String(scales[n]));
} catch (e) { /* storage unavailable — leave default */ }
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* Google Fonts: Crimson Pro (Garamond lineage, optimized for screen
            legibility — much calmer italics than EB Garamond) for Latin;
            Noto Serif Devanagari for Marathi/Hindi. Swapped 2026-06-14 after
            EB Garamond italics read as too cursive at small sizes. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin=""
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500;1,600&family=Noto+Serif+Devanagari:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: FONT_SCALE_HYDRATE }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
