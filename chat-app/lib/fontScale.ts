/**
 * System-wide reader-text font scale.
 *
 * A single multiplier — persisted per-device in localStorage — that scales
 * every content-heavy text surface across the app: reader body paragraphs,
 * Q&A framing, quote-body cards, pravachan example bodies. Chrome (headers,
 * labels, buttons, navigation) is deliberately NOT scaled — the goal is
 * readability of the source material, not to reflow the interface.
 *
 * Applied as the CSS custom property `--app-font-scale` on `<html>`.
 * globals.css uses it via `calc(<base-size> * var(--app-font-scale, 1))` on
 * selectors that opt in. The default (`1`) means "no change from base."
 *
 * Discrete tiers so the buttons feel definite and the persisted value is a
 * small integer index — avoids float-serialization quirks in localStorage.
 */

export const FONT_SCALES = [0.9, 1.0, 1.15, 1.3] as const;
export const DEFAULT_FONT_SCALE_IDX = 1;
export const FONT_SCALE_KEY = "gd:read:fontScale:v1";

/** SSR-safe read. Returns the persisted index, or the default if none. */
export function readStoredIdx(): number {
  if (typeof window === "undefined") return DEFAULT_FONT_SCALE_IDX;
  try {
    const raw = window.localStorage.getItem(FONT_SCALE_KEY);
    if (raw == null) return DEFAULT_FONT_SCALE_IDX;
    const n = parseInt(raw, 10);
    if (Number.isFinite(n) && n >= 0 && n < FONT_SCALES.length) return n;
  } catch {
    // storage unavailable — treat as default.
  }
  return DEFAULT_FONT_SCALE_IDX;
}

export function writeStoredIdx(idx: number): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FONT_SCALE_KEY, String(idx));
  } catch {
    // storage full / unavailable — the in-memory change still applies.
  }
}

/** Apply the multiplier to `<html>` so every descendant sees the CSS var. */
export function applyToRoot(idx: number): void {
  if (typeof document === "undefined") return;
  const scale = FONT_SCALES[Math.max(0, Math.min(FONT_SCALES.length - 1, idx))];
  document.documentElement.style.setProperty("--app-font-scale", String(scale));
}

/** Cross-tab sync + storage-event handler wiring for `useEffect` callers. */
export function subscribeToStorage(onChange: (idx: number) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = (e: StorageEvent) => {
    if (e.key !== FONT_SCALE_KEY) return;
    onChange(readStoredIdx());
  };
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}
