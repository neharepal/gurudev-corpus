# RFC-012: Conversation history (saved question threads)

**Status:** PROPOSED
**Author:** Neha (with Claude)
**Created:** 2026-07-03
**Last updated:** 2026-07-03

## Summary

Persist Q&A and Pravachan conversations device-locally so devotees can look back
at previous answers — a "Your questions" shelf in QnA mode plus a dedicated
`/history` page — reusing the existing `readingProgress` localStorage pattern.

## Motivation

Answers are currently ephemeral. A question is driven entirely by the URL `?q=`,
and follow-ups live in React state that is lost on reload. From QA testing:
*"we need some way to save the conversations/question threads — people need a way
to look back at the answers."*

There is no login and no server-side user state (that is post-demo work, see
RFC-004 and the reading-mode precedent). So history must be **device-local**. The
app already does exactly this for reading position: `lib/readingProgress.ts`
keeps a capped list in `localStorage` and surfaces it as a mode-scoped
"Continue reading" shelf. Conversation history is the same shape for the QnA and
Pravachan modes.

## Goals & non-goals

**Goals**

- Save each conversation as a **full thread** — the initial question/answer plus
  every follow-up — so reopening shows the conversation exactly as it was.
- Surface recent Q&A threads as a **"Your questions"** shelf on the landing page,
  shown **only in QnA mode** (parallel to `ContinueReadingShelf`).
- Provide a **`/history`** page listing **all** saved threads (Q&A + Pravachan)
  with reopen and delete.
- Reopening a thread restores it **from storage with no new `/api/ask` call**.
- Reuse the `readingProgress` storage pattern and the existing `?q=` routing.

**Non-goals**

- Accounts, server-side storage, cross-device sync.
- Search or rename of threads.
- Folding the reading-mode drawer chats (already stored per-book under
  `gd:read:${slug}:chat:v2`) into global history.
- A Pravachan-mode landing shelf (Pravachan threads are reachable via `/history`).

## Proposed design

Five well-bounded units; the two `lib/` modules are pure and independently
testable.

### Data model + storage module — `lib/conversationHistory.ts`

```ts
export type SavedTurn = {
  question: string;
  answer: QAAnswer | PravachanAnswer;
};

export type SavedThread = {
  id: string;                 // deterministic: stable hash of `${mode}|${lang}|${question}`
  mode: "qa" | "pravachan";
  lang: "en" | "mr";
  question: string;                       // initial question
  answer: QAAnswer | PravachanAnswer;     // initial answer (full object, incl. citations)
  followUps: SavedTurn[];                 // follow-up Q/A pairs, in order
  createdAt: number;                      // epoch ms
  updatedAt: number;                      // bumped when a follow-up is appended
};
```

API (same shape/error-handling as `readingProgress.ts`):

- `KEY = "gd:chat:history:v1"`, `CAP = 50`.
- `threadId(mode, lang, question)` — deterministic id; same basis as the existing
  `gd:qa:v1:${mode}|${lang}|${q}` session-cache key (RFC-010 follow-up work).
- `loadThreads()` → newest-first array; corrupt/absent → `[]`.
- `upsertThread(t)` → replace any entry with the same `id`, move to front,
  `slice(0, CAP)`, persist; best-effort `try/catch`.
- `removeThread(id)`, `clearAll()`.

### Save + reopen flow — `app/chat/page.tsx`

- **Save:** on the initial stream `done` event (where the session cache is already
  written) also `upsertThread(...)`; on each follow-up `done`, `upsertThread` the
  same `id` with the appended `followUps` and a fresh `updatedAt`.
- **Reopen:** on mount, compute `id = threadId(mode, lang, q)`; if a `SavedThread`
  exists, restore `answer` **and** `followUps` and **skip the fetch**. Opening
  from the shelf or `/history` shows the whole saved conversation instantly with
  no LLM call. (This extends the existing session-cache hydrate to also restore
  follow-ups from durable storage.)

### UI surfaces

- `components/YourQuestionsShelf.tsx` — landing page, **QnA mode only**, same slot
  as `ContinueReadingShelf` (`app/page.tsx:371`). Recent 3 Q&A threads +
  "See all →" → `/history`. Cards link to `/chat?mode=qa&lang=…&q=…`.
- `app/history/page.tsx` — new route, all threads (Q&A + Pravachan) newest-first.
  Row: question, mode badge, relative date, answer snippet, follow-up count, 🗑
  delete; plus "Clear all" and "◁ Back". Row click → `/chat?mode=…&lang=…&q=…`.
- `lib/answerSnippet.ts` — pure preview-text helper extracted from the existing
  `buildAnswerText` (QA → framing / first citation; Pravachan → first example).

### Error handling

`try/catch` around all storage access; failures degrade silently and never break
the answer stream. Corrupt store → `[]`. Cap keeps newest 50, evicts oldest.
Versioned key (`:v1`) allows a clean future migration.

## Alternatives considered

- **Server-side + accounts (the full industry standard).** Durable, cross-device,
  the real ChatGPT/Claude.ai model. Rejected for now: requires auth + backend user
  state, which the app deliberately doesn't have yet. The data model here is clean
  enough to sync later if accounts arrive.
- **IndexedDB instead of localStorage.** Async, effectively unlimited, better for
  very large/unbounded history. Rejected: overkill for a capped list of text
  threads, and it introduces a new async pattern where the codebase already has a
  proven synchronous localStorage helper (`readingProgress`).
- **Save initial answer only (drop follow-ups).** Simpler, but a "thread" that
  loses its follow-ups isn't the conversation the user had; testers explicitly
  want to look back at the whole exchange.
- **Random UUID per ask instead of a deterministic id.** Would let identical
  questions coexist as separate threads. Rejected: it breaks the clean reuse of
  the `?q=` route and session-cache key, and clutters history with duplicates. The
  deterministic id dedupes; the cost (a re-ask overwrites the stored answer) is
  acceptable for a "look back" feature.

## Tradeoffs & risks

- **Device-local only:** history on a phone won't appear on a shared temple
  tablet, and it's lost if the user clears browser data. Acceptable given no login;
  called out to users implicitly by living in "their" browser.
- **Re-ask overwrites:** because the id is deterministic, re-asking the same
  question replaces the stored answer (LLM output is non-deterministic). Fine for
  looking back; not a version history.
- **Storage limits:** `localStorage` is ~5 MB and synchronous. Full threads with
  citations are a few KB each; the `CAP = 50` bound keeps total size small and
  writes cheap. Quota-exceeded is caught and degrades to "not saved."
- **Privacy:** questions may be personal; they stay on-device, and "Clear all" +
  per-thread delete give the user control.

## Open questions

- Should the QnA-mode shelf show recent **Q&A only** (current plan, mode-scoped) or
  recent threads across both chat modes? Current plan: Q&A only; both appear on
  `/history`.
- Is `CAP = 50` right, or should the shelf/history cap differ?
- Do we want a Pravachan-mode shelf later, or is `/history` sufficient for those?

## References

- Design spec: `docs/superpowers/specs/2026-07-03-conversation-history-design.md`
- Pattern mirrored: `chat-app/lib/readingProgress.ts`, `ContinueReadingShelf` in
  `chat-app/app/page.tsx`
- RFC-004 (chat UI & UX), RFC-010 (progressive streaming; the session-answer cache
  this reuses)
