"use client";

import { type CSSProperties, type ReactElement } from "react";

/**
 * MeditativeLoader — a calm, on-theme progress animation.
 *
 * Concentric ripples radiate outward from a softly breathing ॐ — like the
 * resonance of a singing bowl — in the app's maroon/gold palette. Used both as
 * the big pre-answer loader and (with `compact`) as an inline indicator that
 * stays alive through the later background waits (e.g. while the model grounds
 * its citations). Pure CSS + inline SVG, no dependencies. Honours
 * `prefers-reduced-motion`.
 *
 * Note: every paint-critical attribute (`fill`, `width`/`height`, the ॐ colour)
 * is set as a real SVG attribute, not only via the scoped CSS — otherwise the
 * first paint (before styled-jsx applies) falls back to SVG defaults, which
 * render the ripples as a solid black disc at 300×150.
 */
export default function MeditativeLoader({
  label,
  isDeva = false,
  compact = false,
}: {
  label: string;
  isDeva?: boolean;
  compact?: boolean;
}): ReactElement {
  const size = compact ? 38 : 92;
  const rings = compact ? [0, 1] : [0, 1, 2, 3];
  const duration = compact ? 2.8 : 3.4; // seconds per ripple cycle
  const baseR = compact ? 26 : 18; // ripple starts at the ॐ's edge, not inside
  const scaleEnd = compact ? 1.7 : 2.7;
  const glowR = compact ? 24 : 17;
  const omFont = compact ? 46 : 28;

  return (
    <div
      className={`ml-wrap ${compact ? "ml-compact" : ""}`}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      <svg
        className="ml-svg"
        width={size}
        height={size}
        viewBox="0 0 120 120"
        aria-hidden="true"
      >
        <defs>
          <radialGradient id="ml-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--accent-gold)" stopOpacity="0.5" />
            <stop offset="65%" stopColor="var(--accent-gold)" stopOpacity="0.1" />
            <stop offset="100%" stopColor="var(--accent-gold)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* breathing centre glow + ॐ (drawn first so ripples read above it) */}
        <circle className="ml-glow" cx="60" cy="60" r={glowR} fill="url(#ml-glow)" />
        <text
          className="ml-om"
          x="60"
          y="61"
          fill="#7A2E2A"
          textAnchor="middle"
          dominantBaseline="central"
          style={{ fontSize: omFont }}
        >
          ॐ
        </text>

        {/* expanding ripples — emanate from the ॐ's edge outward */}
        {rings.map((i) => (
          <circle
            key={i}
            className="ml-ripple"
            cx="60"
            cy="60"
            r={baseR}
            fill="none"
            vectorEffect="non-scaling-stroke"
            style={
              {
                stroke:
                  i % 2 === 0 ? "var(--accent-maroon)" : "var(--accent-gold)",
                animationDelay: `${(i * duration) / rings.length}s`,
                animationDuration: `${duration}s`,
                "--ml-scale-end": scaleEnd,
              } as CSSProperties
            }
          />
        ))}
      </svg>

      <p className={`ml-label ${isDeva ? "font-deva" : ""}`}>{label}</p>

      <style jsx>{`
        .ml-wrap {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 14px;
          padding: 28px 0 10px;
        }
        .ml-compact {
          flex-direction: row;
          align-items: center;
          gap: 11px;
          padding: 12px 0 4px;
        }
        .ml-svg {
          overflow: visible;
          flex-shrink: 0;
        }
        .ml-glow {
          transform-box: fill-box;
          transform-origin: center;
          animation: ml-breathe 3.4s ease-in-out infinite;
        }
        .ml-om {
          fill: var(--accent-maroon);
          font-weight: 600;
          transform-box: fill-box;
          transform-origin: center;
          animation: ml-breathe 3.4s ease-in-out infinite;
        }
        .ml-ripple {
          fill: none;
          stroke-width: 1.5;
          opacity: 0;
          transform-box: fill-box;
          transform-origin: center;
          animation-name: ml-ripple;
          animation-timing-function: ease-out;
          animation-iteration-count: infinite;
        }
        .ml-label {
          margin: 0;
          font-style: italic;
          font-size: 15px;
          color: var(--text-tertiary);
          letter-spacing: 0.02em;
          animation: ml-fade 3.2s ease-in-out infinite;
        }
        .ml-compact .ml-label {
          font-size: 14px;
        }
        @keyframes ml-ripple {
          0% {
            transform: scale(1);
            opacity: 0;
          }
          12% {
            opacity: 0.7;
          }
          100% {
            transform: scale(var(--ml-scale-end, 2.6));
            opacity: 0;
          }
        }
        @keyframes ml-breathe {
          0%,
          100% {
            transform: scale(1);
            opacity: 0.85;
          }
          50% {
            transform: scale(1.08);
            opacity: 1;
          }
        }
        @keyframes ml-fade {
          0%,
          100% {
            opacity: 0.55;
          }
          50% {
            opacity: 1;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .ml-glow,
          .ml-om,
          .ml-ripple,
          .ml-label {
            animation: none;
          }
          .ml-ripple {
            opacity: 0.25;
          }
        }
      `}</style>
    </div>
  );
}
