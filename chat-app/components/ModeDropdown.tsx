"use client";

import { useEffect, useRef, useState } from "react";
import { MODES, type ModeId } from "../data/mock-conversations";

type Props = {
  mode: ModeId;
  onSelect: (mode: ModeId) => void;
};

// Mode dropdown lives in the top-right of every screen per RFC-004 §Landing.
// Scales to any number of modes without claiming horizontal real estate.
export default function ModeDropdown({ mode, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const activeLabel = MODES.find((m) => m.id === mode)?.label ?? "Q&A";

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (
        containerRef.current &&
        event.target instanceof Node &&
        !containerRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative"
      style={{ fontFamily: "var(--font-serif)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 rounded-[4px] px-3 py-1.5 text-[13px]"
        style={{
          border: "1px solid var(--accent-maroon)",
          color: "var(--accent-maroon)",
          background: "var(--bg-surface)",
        }}
      >
        <span style={{ color: "var(--text-secondary)" }}>Mode:</span>
        <span>{activeLabel}</span>
        <span className="ml-0.5 text-[10px] leading-none">▾</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-1 min-w-[170px] overflow-hidden rounded-[4px]"
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--accent-maroon)",
            boxShadow: "0 2px 8px rgba(45, 41, 36, 0.08)",
          }}
        >
          {MODES.map((m) => {
            const selected = m.id === mode;
            return (
              <button
                key={m.id}
                role="menuitemradio"
                aria-checked={selected}
                onClick={() => {
                  onSelect(m.id);
                  setOpen(false);
                }}
                className="block w-full cursor-pointer px-3.5 py-2 text-left text-[13px]"
                style={{
                  background: selected ? "var(--bg-panel)" : "transparent",
                  color: selected
                    ? "var(--accent-maroon)"
                    : "var(--text-primary)",
                  borderBottom: "1px solid var(--border-soft)",
                  fontWeight: selected ? 600 : 400,
                }}
              >
                {selected ? "✓ " : "  "}
                {m.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
