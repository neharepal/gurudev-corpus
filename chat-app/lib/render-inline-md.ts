// Minimal inline-markdown renderer for LLM answer text.
//
// The LLM often emits `**bold**` section headings and occasional `*italic*`
// emphasis inside framing paragraphs — meant to make long summaries scannable.
// Rendering these as plain text leaves the `**` markers visible (2026-07-21
// report).
//
// This helper handles ONLY inline bold (`**text**`) and italic (`*text*`) —
// no headings, lists, code, tables, links. That's deliberate:
//   • Keeps the render surface tiny (no XSS from HTML injection since we
//     return React nodes, not innerHTML)
//   • Covers the observed LLM-emitted markdown
//   • Avoids pulling in a full markdown lib for a single answer field
//
// Returns an array of React nodes (strings and <strong>/<em> elements) that
// can be dropped straight into a <p> or <span> children slot.

import type { ReactNode } from "react";
import { Fragment, createElement } from "react";

// Match `**bold**` first, THEN `*italic*` inside each non-bold segment, so
// asterisks nested in bold text (`**foo *bar* baz**`) still work.
const BOLD_RE = /\*\*([^*]+?)\*\*/g;
const ITAL_RE = /\*([^*\s][^*]*?[^*\s]|[^*\s])\*/g;

function renderItalic(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  ITAL_RE.lastIndex = 0;
  while ((m = ITAL_RE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      createElement("em", { key: `${keyPrefix}i${m.index}` }, m[1]),
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function renderInlineMd(text: string | null | undefined): ReactNode {
  if (!text) return null;
  const nodes: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  BOLD_RE.lastIndex = 0;
  while ((m = BOLD_RE.exec(text)) !== null) {
    // Text before this bold span — recurse for italic
    if (m.index > last) {
      nodes.push(
        ...renderItalic(text.slice(last, m.index), `pre${m.index}-`),
      );
    }
    nodes.push(
      createElement(
        "strong",
        { key: `b${m.index}` },
        ...renderItalic(m[1], `bi${m.index}-`),
      ),
    );
    last = m.index + m[0].length;
  }
  // Trailing text after the last bold span
  if (last < text.length) {
    nodes.push(...renderItalic(text.slice(last), `post-`));
  }
  return createElement(Fragment, null, ...nodes);
}
