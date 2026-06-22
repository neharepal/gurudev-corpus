import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "गुरुदेव संग्रह — Gurudev Sangrah",
  description:
    "A guided exploration of the Nimbal sampradaya literature — verbatim quotes, not paraphrase.",
};

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
      </head>
      <body>{children}</body>
    </html>
  );
}
