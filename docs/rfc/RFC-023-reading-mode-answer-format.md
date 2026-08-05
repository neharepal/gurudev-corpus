## RFC-023: Reading-mode Q&A — drop the always-cite ceremony

Author: Neha Repal · Draft 2026-08-05

## Summary

When a devotee asks a question from inside the reader (Reading Mode Q&A, the sidebar drawer at `/read/<slug>`), the current response shape mirrors QA Mode: `framing` + N `citations[]` + `synthesis`, each citation with a `whyChosen` setup sentence and a verbatim quote. This is right for open exploration but wrong for a reader who already has the book open — the citation cards duplicate what's on-screen. RFC-023 introduces a lightweight Reading-Q&A answer shape: **the response is a plain synthesis + conclusion; no citations by default.** If the user asks a citation-ish question ("where does he say that", "cite that", "source?"), the LLM appends up to 3 links in a small "Sources" block. Ships alongside the U2 fix for reading-mode citation links (currently non-functional because the drawer captures the updated page).

## Context — what surfaced this

- **User feedback (Neha, 2026-08-05):** "Let's remove the constraint of always giving citations (the user is already reading!). Let's just give the simple answer to the question. If that answer should contain links — only then should they be added."
- **U2 bug caught the same day:** citation attribution links in Reading Mode Q&A open a same-slug soft-nav that updates the article silently behind the still-open drawer, so nothing appears to happen. The next iteration of the citation UI is the right place to fix this — not a patch to the current one that's about to be replaced.
- **Ninad's earlier feedback (2026-08-04)** that Q&A responses read as rigid cards produced the "woven prose" refactor in commit `4d170da`. That refactor helped QA Mode but made the redundancy worse in Reading Mode by placing `whyChosen` as connective prose above every quote — right where the reader's eye lands.

This RFC does NOT change QA Mode (`/chat` route). QA Mode keeps always-cite because the user is exploring, not reading.

## Current behavior (baseline to change)

Endpoint: `POST /api/ask` with mode inferred from route. Reading Mode Q&A currently uses the QA schema (`framing`, `framingParagraphs`, `citations[]`, `synthesis`) plus a `work: <slug>` scope filter — it is QA Mode with a fixed book filter. The `emit_reading_response` tool (in `tools/prompts.py:440-478`) is a different, older simple-inline-reading path (single `framing` + single `passage`), NOT the same code path as the drawer Q&A. This RFC is about the drawer Q&A; the simple-reading path is out of scope.

Frontend render (`chat-app/app/read/[slug]/page.tsx:1310-1348`):
- `renderInlineMd(m.answer.framing)` — one-line framing
- For each citation: `{c.whyChosen}` as connective prose → `<QuoteBlock variant="inline">` with attribution link
- `renderBlockMd(m.answer.synthesis)` — closing paragraph

Prompt (`tools/prompts.py`): the QA system prompt (`SYSTEM_PROMPT_QA`, not `SYSTEM_PROMPT_READING`) is used, which mandates citations for every answer body. No mode-specific opt-out.

## The design

### A new answer shape for Reading Mode Q&A

Introduce a distinct schema. The response payload gains a `format: "reading-qa" | "qa"` discriminator. When `format === "reading-qa"`:

```ts
type ReadingQaAnswer = {
  format: "reading-qa";
  question: string;                // echoed
  text: string;                    // markdown, the full answer — synthesis + conclusion
  passageLinks?: PassageLink[];    // absent or [] by default; populated only when
                                   //   the user's question implies asking for a source
};

type PassageLink = {
  label: string;                   // descriptive prose — "where Gurudev discusses
                                   //   nama-smaran", NOT a raw reference
  workSlug: string;                // canonical slug
  page: number;                    // reader page number for /read/<slug>?page=N
  workTitle?: string;              // shown when linking to a DIFFERENT work
};
```

`text` is the entire answer — a synthesis + conclusion, the way a knowledgeable companion would explain the concept to someone holding the book. Markdown allowed (bullets, tables, bold/italic per the existing renderers). **No inline link markers, no verbatim quotes.** The frontend renders `text` through `renderBlockMd` — same as today's synthesis field — and that's it.

When `passageLinks` is populated (only when the user asked for sources), the frontend renders a small "Sources" block below `text`: each link is a single line with the descriptive label as the link text and (if the linked work is different from the current book) the work title in muted small text next to it.

QA Mode is unchanged. Its response payload still has `format: "qa"` (implicit if omitted) with the existing `citations[]` + `synthesis` shape. Retrieval, verification, chunking — all shared with QA Mode; only the response shape and the render change.

### When to include links (LLM guidance)

The LLM detects the user's intent from the question phrasing:
- **Include links when** the question implies asking for a source: "where does he say that", "cite that", "which book", "reference?", "source?", the word "quote" as a request rather than a noun, or a follow-up like "show me". Also include if the answer explicitly names a passage the reader wouldn't already have on-screen (e.g. "as Gurudev writes in Chapter 3…" — worth backing that up).
- **Do NOT include links** for the default case: the user asked "what does this mean?", "explain X", "why does Gurudev say Y" — they want understanding, not citation.
- **Cap:** at most 3 links per answer. If the LLM emits more, the backend keeps the first 3 in order and logs a warning.
- **Descriptive labels only.** "where Gurudev discusses nama-smaran" reads naturally in a "Sources:" list; "Kakanchi Pravachane, page 47" reads like an index.

### The U2 links fix — bundled in

Same-slug navigation (link opens a page in the currently-open book) must close the drawer, or the reader sees no visible change. In the new render, every passage link runs through a shared handler that:
- If `workSlug === currentSlug`: dispatch a soft-nav to `?page=N`, then `setChatOpen(false)`.
- If `workSlug !== currentSlug`: hard-nav to `/read/<workSlug>?page=N&from=<returnUrl>`.

The existing "back to your answer" affordance restores the drawer with the saved answer on the return path — see [[RFC-023-back-to-answer]] for that flow's ongoing bug (U5).

## Prompt change (`tools/prompts.py`)

Add `SYSTEM_PROMPT_READING_QA` (distinct from both `SYSTEM_PROMPT_QA` and the existing `SYSTEM_PROMPT_READING`). Key changes vs QA:

1. **Answer plainly.** "Answer as if speaking to a devotee holding the book. `text` is your full synthesis + conclusion — prose, not evidence dossier."
2. **No forced citation, no verbatim quotes.** "Do NOT quote the current passage back at them. Weave the meaning of the retrieved passages into your own words. The reader has the book open."
3. **Sources only if asked.** "Leave `passageLinks` empty unless the user's question implies they want a source — e.g. 'where does he say that', 'cite that', 'source?', 'which book', 'show me'. When you do include links, keep it to at most 3, and use descriptive labels ('where Gurudev discusses nama-smaran') not raw references."
4. **Language + length.** Same as QA (respect the toggle; length matches the question's own scale).

Add `emit_reading_qa_response` tool with the schema above. Existing `emit_qa_response` tool stays untouched.

Server routing (`tools/server.py::/api/ask` handler): mode dispatch — the reading-page caller sends `mode: "reading-qa"` (add a small field to the request body); server chooses which system prompt + tool to use. Default remains QA when the field is missing.

## Frontend render (`chat-app/app/read/[slug]/page.tsx`)

Add a new render branch before the existing citation loop:

```tsx
if (m.answer.format === "reading-qa") {
  return (
    <div>
      <ReadingQaAnswer
        text={m.answer.text}
        passageLinks={m.answer.passageLinks ?? []}
        currentSlug={slug}
        lang={uiLang}
        onNav={() => setChatOpen(false)}
      />
    </div>
  );
}
// existing QA render below (unchanged)
```

The `ReadingQaAnswer` component:
- Renders `text` through `renderBlockMd` — same as today's synthesis field (bullets, tables, bold, italic all supported).
- If `passageLinks?.length`, renders a "Sources" footer: a small heading + one line per link (up to 3), each an `<a>` with the descriptive label. Cross-work links append a muted work title in small type.
- Every link uses the shared onClick that closes the drawer on same-slug nav (the U2 fix).

No text-splitter or marker-parser needed. New files:
- `chat-app/lib/reading-qa-links.ts` — pure link URL builder + same-slug/cross-work detection. Unit-tested with a `.test.ts` sibling.
- `chat-app/components/ReadingQaAnswer.tsx` — the render component.

Response type (`chat-app/data/mock-conversations.ts` or wherever `Answer` is declared) gains the `format` discriminator + `ReadingQaAnswer` variant. TypeScript narrowing keeps the two branches honest.

## Rollout

1. **Land the schema + prompt behind a request flag.** Frontend sends `mode: "reading-qa"` from the reader drawer; backend routes to the new prompt. QA Mode untouched.
2. **Ship to prod.** Vercel picks up the frontend flag; backend docker image includes the new prompt.
3. **Watch for a day.** Ask a handful of questions from a book, verify the answers read naturally and the links point where they should.
4. **Remove the old QA-shape path from Reading Mode** (leave QA Mode alone). Only the flag-off branch stays behind, which is the current always-cite behavior — kept for rollback for one release cycle, then deleted.

## What this RFC does NOT solve

- **QA Mode format.** Unchanged. Always-cite continues to be right for chat.
- **Retrieval quality.** No change to chunker, embedder, reranker, MMR. See RFC-021 / RFC-022 for those.
- **Simple-reading inline path (`SYSTEM_PROMPT_READING`).** That tool is for a different UX and stays as it is.
- **Back-to-answer cache (U5).** Separate one-liner; ships independently.

## Non-goals

- Streaming markdown-inline links. We can compute link positions once at streaming completion; if streaming needs incremental links, that's a v2.
- Cross-language link labels. If the answer is in Marathi and the link target is an English book, the label is the English work title; we don't translate it.
- Multi-passage hover previews. `snippet` is a nice-to-have; if it adds latency, drop it.

## Design calls locked in (Neha, 2026-08-05)

- **No inline link markers.** Links appear only in the `passageLinks[]` array, rendered as a small "Sources" footer below `text`. No `{{link:N}}` parsing.
- **No hover tooltips / snippets.** Skip. Adds latency + LLM work for marginal value.
- **Cap 3, keep-first-3-and-warn.** Server truncates `passageLinks` to the first 3 in order and logs a warning if the LLM emits more. Does not retry.
- **Descriptive labels.** "where Gurudev discusses nama-smaran" — not "Kakanchi Pravachane, page 47".

## Resolved (Neha, 2026-08-05)

- **Cache-key migration:** bump to `gd:qa:v2:...`. Old `v1` entries are ignored (natural miss → refetch once). Simpler than dual-parsing.
- **Prompt language:** yes, add an explicit "do not paraphrase the current page back at the reader" line — it's a common LLM trap and the whole point of the redesign is to stop that behavior.

## References

- User feedback: session 2026-08-05.
- Ninad's woven-prose feedback: 2026-08-04.
- Related bugs: U1 (markdown rendering — fixed `3ad550a`), U2 (reading-mode links — bundled here), U5 (back-to-answer — separate).
- Prior format work: RFC-019 (secondary instructions), RFC-021 (citation fidelity).
- Files this RFC will touch when implemented:
  - `tools/prompts.py` — new `SYSTEM_PROMPT_READING_QA`, new `emit_reading_qa_response` tool.
  - `tools/server.py` — `/api/ask` mode dispatch + response-shape validation.
  - `chat-app/data/mock-conversations.ts` (or the actual `Answer` type location) — schema variant.
  - `chat-app/app/read/[slug]/page.tsx` — new render branch, drops the citation loop for reading-qa.
  - `chat-app/components/ReadingQaAnswer.tsx` — new.
  - `chat-app/lib/reading-qa-links.ts` + `.test.ts` — new.
- Related memory: `feedback_ship_only_with_approval.md`, `feedback_test_before_push.md`.

---

**Ready for Neha's review.** Once approved, I'll break the implementation into small commits: (1) backend schema + prompt behind the flag, (2) frontend render + new component, (3) tests, (4) rollout.
