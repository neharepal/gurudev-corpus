import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "bg-page": "#ECDFBC",
        "bg-surface": "#F4EAC9",
        "bg-panel": "#E5D6AC",
        "text-primary": "#2A241C",
        "text-secondary": "#6B6151",
        "text-tertiary": "#8B7F69",
        "accent-maroon": "#7A2E2A",
        "accent-gold": "#A88556",
        "border-soft": "#C9BC97",
        "border-stronger": "#A89978",
      },
      fontFamily: {
        serif: [
          "Crimson Pro",
          "EB Garamond",
          "Charter",
          "Georgia",
          "Noto Serif Devanagari",
          "serif",
        ],
        deva: [
          "Noto Serif Devanagari",
          "Crimson Pro",
          "Charter",
          "Georgia",
          "serif",
        ],
        mono: ["Iosevka Slab", "IBM Plex Mono", "monospace"],
      },
      maxWidth: {
        reading: "70ch",
      },
    },
  },
  plugins: [],
};

export default config;
