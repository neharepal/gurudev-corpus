# Conversation history (saved question threads) — design

**Date:** 2026-07-03
**Status:** Approved (brainstorm) — formalized in **RFC-012**, which supersedes
this doc where they differ. Finalized after review: **no fixed cap** (keep all,
evict oldest on quota) and **Q&A is the only visible chat mode** (Pravachan
decommissioned from the UI, code kept; data model stays mode-general).
**Surface:** chat-app (Next.js)

## Problem

Q&A answers are ephemeral. A question is driven entirely by the URL `?q=`, and
follow-ups live in memory (they vanish on reload). Testers asked for a way to
**look back at previous answers**. There is no login, so history must be
**device-local**.

## Decisions (from brainstorm)

| Decision | Choice |
|---|---|
| Persistence scope | **Device-local** (browser), no accounts/server |
| What a thread saves | **Full thread** — initial Q&A + all follow-ups |
| Where surfaced | **Landing shelf (QnA mode) + dedicated /history page** |
| /history scope | **Q&A + Pravachan** together |
| Storage tech | **localStorage + cap**, mirroring `lib/readingProgress.ts` |

Industry-standard context: durable cross-device history needs accounts +
server-side storage (post-demo work). For a no-login app the standard is
browser storage; localStorage suits a capped list of text threads.

## Architecture

Mirrors the existing `readingProgress` pattern (a capped localStorage list
surfaced as a mode-scoped shelf). Five well-bounded units:

1. `lib/conversationHistory.ts` — pure storage module.
2. `lib/answerSnippet.ts` — pure preview-text helper.
3. `components/YourQuestionsShelf.tsx` — landing shelf (QnA mode only).
4. `app/history/page.tsx` — full history list route.
5. Integration edits in `app/chat/page.tsx` — save on completion, hydrate on reopen.

### 1. Data model + storage module

New `lib/conversationHistory.ts`:

```ts
export type SavedTurn = {
  question: string;
  answer: QAAnswer | PravachanAnswer;
};

export type SavedThread = {
  id: string;                 // deterministic: stable hash of `${mode}|${lang}|${question}`
  mode: "qa" | "pravachan";
  lang: "en" | "mr";
  question: string;           // initial question
  answer: QAAnswer | PravachanAnswer;   // initial answer (full object, incl. citations)
  followUps: SavedTurn[];     // follow-up Q/A pairs, in order
  createdAt: number;          // epoch ms
  updatedAt: number;          // bumped when a follow-up is appended
};
```

API (same shape and error-handling as `readingProgress.ts`):

- `const KEY = "gd:chat:history:v1";`
- `const CAP = 50;`
- `threadId(mode, lang, question): string` — deterministic id (same basis as the
  existing `gd:qa:v1:${mode}|${lang}|${q}` session cache key).
- `loadThreads(): SavedThread[]` — parse; corrupt/absent → `[]`.
- `upsertThread(t: SavedThread): void` — replace any existing entry with the same
  `id`, move to front, `slice(0, CAP)`, persist. Best-effort `try/catch`.
- `removeThread(id: string): void`
- `clearAll(): void`

**Deterministic id rationale:** re-asking the same question updates one thread
instead of creating duplicates, and it reuses the existing `?q=` routing plus the
`#3` session cache key. Accepted trade-off: re-asking overwrites the stored
answer with the latest one (acceptable for "look back").

### 2. Save + reopen flow

**Save** (in `app/chat/page.tsx`):
- On the initial stream `done` (where the `#3` sessionStorage cache is already
  written), also `upsertThread({ id, mode, lang, question, answer, followUps: [], createdAt: now, updatedAt: now })`.
- On each follow-up `done`, `upsertThread` the same `id` with the appended
  `followUps` and a fresh `updatedAt`.

**Reopen** (extends the existing `#3` hydrate on mount):
- Compute `id = threadId(mode, lang, q)`.
- If a `SavedThread` exists for `id`, restore its `answer` **and** `followUps`
  into state and **skip the fetch** (no LLM call). Opening from the shelf or
  /history shows the whole saved conversation instantly.
- The session cache remains the fast path; the localStorage thread is the
  durable source that also restores follow-ups.

### 3. UI surfaces

**`components/YourQuestionsShelf.tsx`** — rendered on the landing page **only in
QnA mode**, in the same slot as `ContinueReadingShelf` (`app/page.tsx:371`).
Shows the most recent 3 **Q&A** threads (heading "Your questions" / "तुमचे प्रश्न")
+ "See all →" linking to `/history`. Each card links to
`/chat?mode=qa&lang=<lang>&q=<question>`. No "Continue reading" in QnA mode; no
"Your questions" in Reading mode (mode-scoped, matching existing behavior).

**`app/history/page.tsx`** — new route listing **all** saved threads (Q&A +
Pravachan), newest-first. Each row: question, mode badge (Q&A / Pravachan),
relative date, answer snippet, follow-up count, and a 🗑 delete affordance. A
"Clear all" action and a "◁ Back" link to `/`. Row click →
`/chat?mode=<mode>&lang=<lang>&q=<question>`. Delete → `removeThread` + local
re-render (same pattern as `ContinueReadingShelf`'s remove).

**`lib/answerSnippet.ts`** — pure helper returning a short preview string for a
thread, extracted from the existing `buildAnswerText` logic in `chat/page.tsx`
(QA → framing / first citation; Pravachan → first example). Reused by both the
shelf and the history list.

### 4. Error handling & edge cases

- All storage access wrapped in `try/catch`; failures degrade silently and never
  break the answer stream (matches `readingProgress`).
- Corrupt/absent store → `[]`.
- Cap: keep newest `CAP` (50), evict oldest.
- Versioned key (`:v1`) so a future shape change can migrate/discard cleanly.
- Private-mode / quota-exceeded: save is best-effort; the app still works without
  persistence.

### 5. Testing

chat-app has no frontend test framework, and `readingProgress.ts` ships untested
— this design matches that. `conversationHistory.ts` and `answerSnippet.ts` are
**pure and independently verifiable**; correctness is confirmed end-to-end in the
running app (ask → appears in shelf/history → reopen restores thread + follow-ups
with no new `/api/ask` call → delete removes it). Adding vitest for the two pure
modules is a reasonable optional follow-up, not part of this scope.

## Out of scope

- Accounts, server-side storage, cross-device sync.
- Search / rename of threads.
- Persisting the reading-mode drawer chats into global history (already stored
  per-book under `gd:read:${slug}:chat:v2`).
- A Pravachan-mode landing shelf (Pravachan threads are reachable via /history).

## Files

- New: `lib/conversationHistory.ts`, `lib/answerSnippet.ts`,
  `components/YourQuestionsShelf.tsx`, `app/history/page.tsx`.
- Edited: `app/chat/page.tsx` (save on done + follow-up; hydrate follow-ups on
  reopen), `app/page.tsx` (render `YourQuestionsShelf` in QnA mode).
