"use client";

import { useEffect, useState } from "react";
import {
  FONT_SCALES,
  applyToRoot,
  readStoredIdx,
  subscribeToStorage,
  writeStoredIdx,
} from "../lib/fontScale";

/**
 * Compact A− / A+ control for the app-wide reader-text scale. Mount anywhere;
 * writes the change to `<html>` immediately so every scaled surface reflows
 * without a re-render. Cross-tab consistent via the storage event.
 *
 * The `floating` variant is the default for surfaces that don't have a header
 * of their own (chat, pravachan) — pins to the top-right of the viewport,
 * translucent, hidden behind a semi-transparent chip so it never dominates
 * the reading column. `inline` drops it into an existing header row.
 */
export default function FontScaleControl({
  variant = "floating",
}: {
  variant?: "floating" | "inline";
}) {
  const [idx, setIdx] = useState<number>(1);

  // Hydrate from localStorage on mount + apply to <html>. Subsequent updates
  // in another tab (same origin) sync in via the storage event.
  useEffect(() => {
    const initial = readStoredIdx();
    setIdx(initial);
    applyToRoot(initial);
    return subscribeToStorage((next) => {
      setIdx(next);
      applyToRoot(next);
    });
  }, []);

  const bump = (delta: number) => {
    setIdx((prev) => {
      const next = Math.max(0, Math.min(FONT_SCALES.length - 1, prev + delta));
      writeStoredIdx(next);
      applyToRoot(next);
      return next;
    });
  };

  const atMin = idx === 0;
  const atMax = idx === FONT_SCALES.length - 1;

  const wrapperClass =
    variant === "floating"
      ? // Pinned to the viewport top-right; sits above content but stays
        // out of the way of the primary action column. Backdrop-blur so it
        // reads even on top of the parchment texture.
        //
        // `pointer-events-none` on the wrapper is critical: the chip covers
        // ~60×30 px of viewport in the top-right corner, and without this
        // any content scrolling behind it (e.g. a citation's "Read in full"
        // link) would be silently non-clickable in that region — reported
        // 2026-08-02. Buttons re-enable pointer-events on themselves so
        // A− / A+ still work.
        "pointer-events-none fixed right-3 top-3 z-40 flex items-center gap-1 rounded-[6px] px-1.5 py-1 backdrop-blur-sm sm:right-4 sm:top-4"
      : "flex items-center gap-1";

  const wrapperStyle =
    variant === "floating"
      ? {
          background: "rgba(244, 234, 201, 0.7)",
          border: "1px solid var(--border-soft)",
        }
      : undefined;

  return (
    <div
      className={wrapperClass}
      style={wrapperStyle}
      role="group"
      aria-label="Reader text size"
    >
      <button
        type="button"
        onClick={() => bump(-1)}
        disabled={atMin}
        aria-label="Decrease text size"
        className="pointer-events-auto rounded-[4px] px-2 py-1 text-[13px] leading-none disabled:opacity-40"
        style={{
          color: "var(--text-secondary)",
          border: "1px solid var(--border-soft)",
          background: "transparent",
        }}
      >
        A−
      </button>
      <button
        type="button"
        onClick={() => bump(1)}
        disabled={atMax}
        aria-label="Increase text size"
        className="pointer-events-auto rounded-[4px] px-2 py-1 text-[15px] leading-none disabled:opacity-40"
        style={{
          color: "var(--text-secondary)",
          border: "1px solid var(--border-soft)",
          background: "transparent",
        }}
      >
        A+
      </button>
    </div>
  );
}
