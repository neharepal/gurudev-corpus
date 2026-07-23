// Block-level markdown renderer for LLM answer text.
//
// Per RFC-019, the `synthesis` field is the user-shaped answer body — when the
// reader asks for bullets / a numbered list / a table, that's where it lives.
// This renderer handles the block-level constructs; inline emphasis is
// delegated to render-inline-md.ts for each token of text content.
//
// Supported block constructs:
//   - `- item` or `* item`        → <ul><li>…</li></ul>
//   - `1. item`                   → <ol><li>…</li></ol>
//   - `| col | col |` (two-line)  → <table>
//   - blank line                  → paragraph break
//
// Deliberately narrow: no headings, no images, no arbitrary links, no code.
// The synthesis field should not need any of those; keeping the surface small
// keeps the XSS surface flat. We emit React nodes only (never
// dangerouslySetInnerHTML), and the inline renderer likewise emits nodes.
//
// Passage-letter link convention (RFC-019 §4a): items ending with " (A)" or
// " (B)" — a single uppercase letter in parens at end-of-line — get an
// <a href="#cite-A"> anchor around the letter that jumps to the matching
// citation card. The parent renderer is responsible for stamping id="cite-A"
// on each citation.

import type { ReactNode } from "react";
import { Fragment, createElement } from "react";
import { renderInlineMd } from "./render-inline-md";

// Match a trailing " (X)" where X is a single uppercase letter A–Z. Used to
// wrap the letter in an anchor that scrolls to the matching citation card.
const PASSAGE_LETTER_RE = /\s+\(([A-Z])\)\s*$/;

function renderItemContent(text: string, keyPrefix: string): ReactNode {
  // If the item ends with " (A)"-style passage-letter, split off that suffix
  // and wrap the letter in an anchor. Otherwise, just inline-render.
  const m = text.match(PASSAGE_LETTER_RE);
  if (!m) return renderInlineMd(text);
  const body = text.slice(0, m.index);
  const letter = m[1];
  return createElement(
    Fragment,
    null,
    renderInlineMd(body),
    " (",
    createElement(
      "a",
      {
        key: `${keyPrefix}-cite-${letter}`,
        href: `#cite-${letter}`,
        className: "cite-jump",
      },
      letter,
    ),
    ")",
  );
}

function isUnorderedBullet(line: string): boolean {
  return /^\s*[-*]\s+\S/.test(line);
}

function isOrderedBullet(line: string): boolean {
  return /^\s*\d+\.\s+\S/.test(line);
}

function isTableRow(line: string): boolean {
  // `| col | col |` — at least two pipe-delimited cells.
  return /^\s*\|.*\|\s*$/.test(line);
}

function isTableSeparator(line: string): boolean {
  // `| --- | --- |` — dashes and pipes only (with optional colons for align).
  return /^\s*\|(?:\s*:?-+:?\s*\|)+\s*$/.test(line);
}

function stripBullet(line: string): string {
  return line.replace(/^\s*[-*]\s+/, "").trimEnd();
}

function stripOrdered(line: string): string {
  return line.replace(/^\s*\d+\.\s+/, "").trimEnd();
}

function parseTableRow(line: string): string[] {
  // Trim, drop leading/trailing `|`, split on `|`, trim each cell.
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

export function renderBlockMd(text: string | null | undefined): ReactNode {
  if (!text) return null;
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const nodes: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    // Table: header row + separator row + zero-or-more body rows.
    if (
      isTableRow(line) &&
      i + 1 < lines.length &&
      isTableSeparator(lines[i + 1])
    ) {
      const header = parseTableRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && isTableRow(lines[i]) && !isTableSeparator(lines[i])) {
        rows.push(parseTableRow(lines[i]));
        i++;
      }
      nodes.push(
        createElement(
          "div",
          { key: `tbl-wrap-${key++}`, className: "md-table-wrap" },
          createElement(
            "table",
            { className: "md-table" },
            createElement(
              "thead",
              null,
              createElement(
                "tr",
                null,
                ...header.map((c, ci) =>
                  createElement(
                    "th",
                    { key: `h${ci}` },
                    renderInlineMd(c),
                  ),
                ),
              ),
            ),
            createElement(
              "tbody",
              null,
              ...rows.map((r, ri) =>
                createElement(
                  "tr",
                  { key: `r${ri}` },
                  ...r.map((c, ci) =>
                    createElement(
                      "td",
                      { key: `c${ci}` },
                      renderInlineMd(c),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      continue;
    }

    // Unordered list: consume consecutive bullet lines.
    if (isUnorderedBullet(line)) {
      const items: string[] = [];
      while (i < lines.length && isUnorderedBullet(lines[i])) {
        items.push(stripBullet(lines[i]));
        i++;
      }
      nodes.push(
        createElement(
          "ul",
          { key: `ul-${key++}`, className: "md-ul" },
          ...items.map((it, idx) =>
            createElement(
              "li",
              { key: `li${idx}` },
              renderItemContent(it, `ul${key}-${idx}`),
            ),
          ),
        ),
      );
      continue;
    }

    // Ordered list: consume consecutive numbered lines.
    if (isOrderedBullet(line)) {
      const items: string[] = [];
      while (i < lines.length && isOrderedBullet(lines[i])) {
        items.push(stripOrdered(lines[i]));
        i++;
      }
      nodes.push(
        createElement(
          "ol",
          { key: `ol-${key++}`, className: "md-ol" },
          ...items.map((it, idx) =>
            createElement(
              "li",
              { key: `li${idx}` },
              renderItemContent(it, `ol${key}-${idx}`),
            ),
          ),
        ),
      );
      continue;
    }

    // Otherwise: gather consecutive non-blank, non-block-marker lines into a
    // paragraph. Break on blank line, bullet, or table row.
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !isUnorderedBullet(lines[i]) &&
      !isOrderedBullet(lines[i]) &&
      !isTableRow(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      nodes.push(
        createElement(
          "p",
          { key: `p-${key++}`, className: "md-p" },
          renderInlineMd(paraLines.join(" ")),
        ),
      );
    }
  }

  return createElement(Fragment, null, ...nodes);
}
