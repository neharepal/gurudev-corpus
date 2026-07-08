# Conversation History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Q&A/Pravachan conversations device-locally so users can reopen past answers via a QnA-mode "Your questions" shelf and a `/history` page.

**Architecture:** Mirror the existing `lib/readingProgress.ts` pattern — a `localStorage`-backed module surfaced by a mode-scoped shelf. Two pure `lib/` modules (storage + snippet), one shelf component, one new route, and integration edits in the chat page to save on completion and rehydrate (including follow-ups) on reopen.

**Tech Stack:** Next.js 15 (app router, client components), TypeScript, `localStorage`. No new dependencies.

## Global Constraints

- SSR-safe: every `localStorage` access guarded by `typeof window === "undefined"` returning a safe default (matches `readingProgress.ts`).
- Storage key: `gd:chat:history:v1`. **No fixed count cap** — keep all threads; on `QuotaExceededError`, evict the oldest and retry so the newest always saves.
- Data model stays **mode-general** (`mode: "qa" | "pravachan"`) even though Pravachan is hidden from the UI — legacy Pravachan threads must still render.
- `Lang = "en" | "mr"`. Reuse existing types `QAAnswer`, `PravachanAnswer` from `lib/api.ts`.
- No test framework exists in chat-app (see RFC-012 §Testing). Per-task gates are `npx tsc --noEmit` for type/interface correctness plus concrete in-app verification. The two pure modules are additionally exercised end-to-end in Tasks 3–5.
- Follow existing code style: inline styles + Tailwind as in `ContinueReadingShelf`.

---

### Task 1: Storage module `lib/conversationHistory.ts`

**Files:**
- Create: `chat-app/lib/conversationHistory.ts`

**Interfaces:**
- Consumes: `QAAnswer`, `PravachanAnswer` from `chat-app/data/mock-conversations.ts`.
- Produces:
  - `type SavedTurn = { question: string; answer: QAAnswer | PravachanAnswer }`
  - `type SavedThread = { id: string; mode: "qa" | "pravachan"; lang: "en" | "mr"; question: string; answer: QAAnswer | PravachanAnswer; followUps: SavedTurn[]; createdAt: number; updatedAt: number }`
  - `threadId(mode: string, lang: string, question: string): string`
  - `loadThreads(): SavedThread[]` (newest-first by `updatedAt`)
  - `upsertThread(thread: SavedThread): void` (preserves prior `createdAt`)
  - `removeThread(id: string): void`
  - `clearAll(): void`

- [ ] **Step 1: Write the module**

```ts
// chat-app/lib/conversationHistory.ts
/**
 * Conversation history — device-local persistence of chat threads.
 * localStorage, SSR-safe. Mirrors lib/readingProgress.ts. See RFC-012.
 *
 * Key: gd:chat:history:v1
 * No fixed cap: keep all threads; on QuotaExceededError evict oldest and retry
 * so the newest thread is never the one dropped.
 */
import type { QAAnswer, PravachanAnswer } from "../data/mock-conversations";

export type SavedTurn = {
  question: string;
  answer: QAAnswer | PravachanAnswer;
};

export type SavedThread = {
  id: string;
  mode: "qa" | "pravachan";
  lang: "en" | "mr";
  question: string;
  answer: QAAnswer | PravachanAnswer;
  followUps: SavedTurn[];
  createdAt: number;
  updatedAt: number;
};

const KEY = "gd:chat:history:v1";

/** Deterministic id — same basis as the session-answer cache key. */
export function threadId(mode: string, lang: string, question: string): string {
  return `${mode}|${lang}|${question.trim()}`;
}

export function loadThreads(): SavedThread[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SavedThread[];
    if (!Array.isArray(parsed)) return [];
    return parsed.slice().sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

/** Persist newest-first; on quota error, drop the oldest and retry. */
function persist(threads: SavedThread[]): void {
  let list = threads.slice().sort((a, b) => b.updatedAt - a.updatedAt);
  // eslint-disable-next-line no-constant-condition
  while (true) {
    try {
      localStorage.setItem(KEY, JSON.stringify(list));
      return;
    } catch {
      if (list.length <= 1) return; // can't shrink further; give up silently
      list = list.slice(0, list.length - 1); // drop oldest (list is newest-first)
    }
  }
}

export function upsertThread(thread: SavedThread): void {
  if (typeof window === "undefined") return;
  const all = loadThreads();
  const prior = all.find((t) => t.id === thread.id);
  // Preserve the original createdAt so re-saves/reopens don't reset it.
  const merged: SavedThread = prior
    ? { ...thread, createdAt: prior.createdAt }
    : thread;
  persist([merged, ...all.filter((t) => t.id !== thread.id)]);
}

export function removeThread(id: string): void {
  if (typeof window === "undefined") return;
  persist(loadThreads().filter((t) => t.id !== id));
}

export function clearAll(): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
```

- [ ] **Step 2: Typecheck**

Run: `cd chat-app && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0, no errors.

- [ ] **Step 3: Behavior self-check (read the code against these cases)**

Confirm by inspection: `upsertThread` twice with the same `id` yields ONE entry (dedup via `filter`), `createdAt` preserved, `updatedAt` from the new object; `loadThreads` returns newest-first; corrupt/absent storage → `[]`. (Runtime verification happens in Tasks 3–5.)

- [ ] **Step 4: Commit**

```bash
git add chat-app/lib/conversationHistory.ts
git commit -m "feat(history): device-local conversation storage module (RFC-012)"
```

---

### Task 2: Snippet helper `lib/answerSnippet.ts`

**Files:**
- Create: `chat-app/lib/answerSnippet.ts`

**Interfaces:**
- Consumes: `QAAnswer`, `PravachanAnswer` from `data/mock-conversations.ts`.
- Produces: `answerSnippet(answer: QAAnswer | PravachanAnswer, max?: number): string`

- [ ] **Step 1: Write the module**

```ts
// chat-app/lib/answerSnippet.ts
/** Short preview text for a saved thread. Pure. Mirrors buildAnswerText's field
 * priority (chat/page.tsx): QA → framing/synthesis/first citation; Pravachan →
 * thesis/first example. */
import type { QAAnswer, PravachanAnswer } from "../data/mock-conversations";

export function answerSnippet(
  answer: QAAnswer | PravachanAnswer,
  max = 140,
): string {
  let text = "";
  if (answer.kind === "qa") {
    text =
      answer.framing ||
      answer.synthesis ||
      answer.citations?.[0]?.quote?.body ||
      "";
  } else {
    text = answer.thesis || answer.examples?.[0]?.quote?.body || "";
  }
  text = text.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}
```

- [ ] **Step 2: Typecheck**

Run: `cd chat-app && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0. (If `synthesis` is not a field on `QAAnswer`, drop that clause — verify against `lib/api.ts` `QAAnswer` first; `framing` is guaranteed.)

- [ ] **Step 3: Commit**

```bash
git add chat-app/lib/answerSnippet.ts
git commit -m "feat(history): answer snippet helper for thread previews"
```

---

### Task 3: Save on completion + rehydrate on reopen (`app/chat/page.tsx`)

**Files:**
- Modify: `chat-app/app/chat/page.tsx` (imports; the mount hydrate block ~line 262; add a persistence effect after the initial-fetch effect)

**Interfaces:**
- Consumes: `threadId`, `upsertThread`, `loadThreads`, `SavedThread` (Task 1).
- Produces: nothing new for later tasks (writes to `localStorage`).

- [ ] **Step 1: Add the import**

Near the other lib imports at the top of `app/chat/page.tsx`:

```ts
import { threadId, upsertThread, loadThreads } from "../../lib/conversationHistory";
```

- [ ] **Step 2: Rehydrate full thread (answer + follow-ups) on mount**

In the initial fetch `useEffect`, replace the existing session-cache hydrate block (the `const cacheKey = ...; try { const cached = sessionStorage.getItem(cacheKey) ... }` block, ~lines 262–276) with a version that prefers the durable saved thread:

```ts
    const cacheKey = `gd:qa:v1:${mode}|${lang}|${q}`;

    // Durable rehydrate: a saved thread restores the answer AND follow-ups,
    // so reopening from the shelf/history shows the whole conversation with no
    // new /api/ask call.
    const saved = loadThreads().find((t) => t.id === threadId(mode, lang, q));
    if (saved) {
      setAnswer(saved.answer);
      setFollowUps(
        saved.followUps.map((t) => ({
          question: t.question,
          answer: t.answer,
          loading: false,
          streaming: false,
          error: null,
        })),
      );
      setLoading(false);
      setStreaming(false);
      setError(null);
      return; // do NOT re-fetch
    }

    // Fallback: session cache (answer only) — the fast path within a tab.
    try {
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) {
        setAnswer(JSON.parse(cached) as QAAnswer | PravachanAnswer);
        setLoading(false);
        setStreaming(false);
        setError(null);
        return;
      }
    } catch {
      // storage unavailable / bad JSON — fall through to a normal fetch.
    }
```

- [ ] **Step 3: Add a persistence effect (covers initial + follow-ups)**

Immediately AFTER the initial fetch `useEffect` (the one with deps `[mode, lang, questionFromUrl]`), add:

```ts
  // Persist the thread whenever the initial answer or any follow-up settles.
  // In-flight follow-ups (streaming) are excluded until complete.
  useEffect(() => {
    const q = questionFromUrl?.trim();
    if (!q || !answer || streaming) return; // wait for the initial stream to finish
    const settled = followUps
      .filter((t) => t.answer && !t.streaming)
      .map((t) => ({ question: t.question, answer: t.answer! }));
    const now = Date.now();
    upsertThread({
      id: threadId(mode, lang, q),
      mode,
      lang,
      question: q,
      answer,
      followUps: settled,
      createdAt: now, // upsertThread preserves the prior createdAt if it exists
      updatedAt: now,
    });
  }, [answer, followUps, streaming, mode, lang, questionFromUrl]);
```

- [ ] **Step 4: Typecheck**

Run: `cd chat-app && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0. (If `t.answer!` trips `no-non-null-assertion`, the `.filter((t) => t.answer && ...)` guarantees it; keep the assertion or map with a local `const a = t.answer; if (!a) ...`.)

- [ ] **Step 5: In-app verification**

With `npm run dev` running: ask a Q&A question; when it finishes, open DevTools → Application → Local Storage → `gd:chat:history:v1` and confirm one thread with the full `answer`. Ask a follow-up; confirm the same entry now has a `followUps[0]`. Hard-reload the page (same `?q=`) and confirm the answer + follow-up render **without a new `/api/ask`** request in the Network tab.

- [ ] **Step 6: Commit**

```bash
git add chat-app/app/chat/page.tsx
git commit -m "feat(history): save chat threads on completion; rehydrate follow-ups on reopen"
```

---

### Task 4: "Your questions" shelf (`components/YourQuestionsShelf.tsx` + wire into landing)

**Files:**
- Create: `chat-app/components/YourQuestionsShelf.tsx`
- Modify: `chat-app/app/page.tsx` (import; render in QnA mode next to the existing `ContinueReadingShelf` conditional, ~line 371)

**Interfaces:**
- Consumes: `loadThreads`, `removeThread`, `SavedThread` (Task 1); `answerSnippet` (Task 2); `Lang` from `components/ModeTabs`.
- Produces: `default export function YourQuestionsShelf({ lang }: { lang: Lang })`.

- [ ] **Step 1: Write the component**

```tsx
// chat-app/components/YourQuestionsShelf.tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Lang } from "./ModeTabs";
import { loadThreads, removeThread, type SavedThread } from "../lib/conversationHistory";
import { answerSnippet } from "../lib/answerSnippet";

const RECENT = 3; // shelf shows the most recent N Q&A threads

export default function YourQuestionsShelf({ lang }: { lang: Lang }) {
  const [threads, setThreads] = useState<SavedThread[]>([]);
  const isMr = lang === "mr";

  useEffect(() => {
    setThreads(loadThreads().filter((t) => t.mode === "qa"));
  }, []);

  if (threads.length === 0) return null;
  const recent = threads.slice(0, RECENT);

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center justify-between">
        <p
          className={`text-[13.5px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-tertiary)" }}
        >
          {isMr ? "तुमचे प्रश्न:" : "Your questions:"}
        </p>
        <Link
          href="/history"
          className={`text-[13px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--accent-maroon)" }}
        >
          {isMr ? "सर्व पहा →" : "See all →"}
        </Link>
      </div>
      <ul className="flex flex-col gap-2">
        {recent.map((t) => {
          const isDeva = /[ऀ-ॿ]/.test(t.question);
          return (
            <li key={t.id}>
              <Link
                href={`/chat?mode=${t.mode}&lang=${t.lang}&q=${encodeURIComponent(t.question)}`}
                className="block rounded-[6px] px-3 py-2.5 transition-all"
                style={{
                  background: "rgba(244, 234, 201, 0.5)",
                  border: "1px solid rgba(122, 46, 42, 0.22)",
                  textDecoration: "none",
                }}
              >
                <span
                  className={`block truncate text-[14px] ${isDeva || isMr ? "font-deva" : ""}`}
                  style={{ color: "#5A2520" }}
                >
                  {t.question}
                </span>
                <span
                  className="block truncate text-[12.5px]"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {answerSnippet(t.answer, 90)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Wire into the landing page**

In `app/page.tsx`, add the import near the other component imports:

```ts
import YourQuestionsShelf from "../components/YourQuestionsShelf";
```

Find the existing reading-mode shelf conditional (~line 371):

```tsx
          {mode === "reading" && (
            <ContinueReadingShelf lang={lang} />
          )}
```

Add the QnA counterpart directly after it:

```tsx
          {mode === "qa" && <YourQuestionsShelf lang={lang} />}
```

- [ ] **Step 3: Typecheck**

Run: `cd chat-app && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0.

- [ ] **Step 4: In-app verification**

`npm run dev`, hard-reload the landing page in **Ask** mode: the "Your questions:" shelf lists your recent Q&A (most recent first, ≤3) with a snippet; "See all →" points to `/history`; clicking a card opens `/chat?...&q=...` and shows the saved thread. Switch to **Reading** mode: the shelf is gone (only Continue reading shows).

- [ ] **Step 5: Commit**

```bash
git add chat-app/components/YourQuestionsShelf.tsx chat-app/app/page.tsx
git commit -m "feat(history): 'Your questions' shelf on the QnA landing"
```

---

### Task 5: `/history` page (`app/history/page.tsx`)

**Files:**
- Create: `chat-app/app/history/page.tsx`

**Interfaces:**
- Consumes: `loadThreads`, `removeThread`, `clearAll`, `SavedThread` (Task 1); `answerSnippet` (Task 2).
- Produces: the `/history` route (default export React component).

- [ ] **Step 1: Write the page**

```tsx
// chat-app/app/history/page.tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  loadThreads,
  removeThread,
  clearAll,
  type SavedThread,
} from "../../lib/conversationHistory";
import { answerSnippet } from "../../lib/answerSnippet";

function relDate(ms: number): string {
  const d = Math.floor((Date.now() - ms) / 86400000);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  return `${d} days ago`;
}

export default function HistoryPage() {
  const [threads, setThreads] = useState<SavedThread[]>([]);

  useEffect(() => {
    setThreads(loadThreads());
  }, []);

  function handleRemove(id: string) {
    removeThread(id);
    setThreads(loadThreads());
  }
  function handleClearAll() {
    clearAll();
    setThreads([]);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-6">
      <header
        className="mb-5 flex items-center justify-between pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        <Link href="/" className="text-[14px]" style={{ color: "var(--text-secondary)" }}>
          ◁ Back
        </Link>
        <span className="text-[17px] font-semibold" style={{ color: "var(--text-primary)" }}>
          Your questions
        </span>
        {threads.length > 0 ? (
          <button
            type="button"
            onClick={handleClearAll}
            className="text-[13px]"
            style={{ color: "var(--text-tertiary)", background: "transparent" }}
          >
            Clear all
          </button>
        ) : (
          <span style={{ width: 52 }} />
        )}
      </header>

      {threads.length === 0 ? (
        <p className="mt-10 text-center text-[15px]" style={{ color: "var(--text-tertiary)" }}>
          No saved questions yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {threads.map((t) => {
            const isDeva = /[ऀ-ॿ]/.test(t.question);
            const followN = t.followUps.length;
            return (
              <li key={t.id} className="flex items-start gap-2">
                <Link
                  href={`/chat?mode=${t.mode}&lang=${t.lang}&q=${encodeURIComponent(t.question)}`}
                  className="min-w-0 flex-1 rounded-[6px] px-3 py-2.5"
                  style={{
                    background: "rgba(244, 234, 201, 0.5)",
                    border: "1px solid rgba(122, 46, 42, 0.22)",
                    textDecoration: "none",
                  }}
                >
                  <div className="mb-0.5 flex items-center gap-2">
                    <span
                      className="rounded-full px-2 py-0.5 text-[11px]"
                      style={{ background: "rgba(122,46,42,0.12)", color: "#5A2520" }}
                    >
                      {t.mode === "qa" ? "Q&A" : "Pravachan"}
                    </span>
                    <span className="text-[12px]" style={{ color: "var(--text-tertiary)" }}>
                      {relDate(t.updatedAt)}
                      {followN > 0 ? ` · ${followN} follow-up${followN > 1 ? "s" : ""}` : ""}
                    </span>
                  </div>
                  <div
                    className={`truncate text-[15px] ${isDeva ? "font-deva" : ""}`}
                    style={{ color: "#5A2520" }}
                  >
                    {t.question}
                  </div>
                  <div className="truncate text-[13px]" style={{ color: "var(--text-tertiary)" }}>
                    {answerSnippet(t.answer, 120)}
                  </div>
                </Link>
                <button
                  type="button"
                  aria-label="Delete"
                  onClick={() => handleRemove(t.id)}
                  className="shrink-0 px-2 py-2 text-[15px]"
                  style={{ color: "var(--text-tertiary)", background: "transparent" }}
                >
                  🗑
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd chat-app && npx tsc --noEmit -p tsconfig.json`
Expected: exit 0.

- [ ] **Step 3: In-app verification**

Navigate to `/history` (or click "See all →"): all saved threads appear newest-first with mode badge, relative date, follow-up count, and snippet. Click a row → opens the saved thread in `/chat`. Click 🗑 → the row disappears and stays gone after reload. "Clear all" empties the list and shows the empty state.

- [ ] **Step 4: Commit**

```bash
git add chat-app/app/history/page.tsx
git commit -m "feat(history): /history page with reopen, delete, and clear-all"
```

---

## Self-Review

**Spec coverage (RFC-012):**
- Full thread + follow-ups persisted → Task 1 model + Task 3 persistence effect. ✓
- Device-local, no cap, evict-oldest-on-quota → Task 1 `persist`. ✓
- Reopen with no LLM call → Task 3 rehydrate (returns before fetch). ✓
- QnA-mode shelf → Task 4. ✓
- /history (Q&A + Pravachan), delete, clear-all → Task 5. ✓
- Snippet helper → Task 2. ✓
- Mode-general data model (legacy Pravachan renders) → `mode` field + Task 5 badge handles both. ✓

**Type consistency:** `SavedThread`/`SavedTurn`/`threadId`/`loadThreads`/`upsertThread`/`removeThread`/`clearAll` names are identical across Tasks 1, 3, 4, 5. `answerSnippet` signature identical in Tasks 2, 4, 5. `Lang` imported from `components/ModeTabs` (existing convention).

**Placeholders:** none — every step has complete code.

**Confirmed against `data/mock-conversations.ts`:** `QAAnswer` has `framing: string` (required), `synthesis?: string` (optional), `citations: QACitation[]` (each `{ quote: Quote; whyChosen }`, `Quote.body`). `PravachanAnswer` has `thesis?: string`, `examples: PravachanExample[]` (each `{ quote: Quote }`). All field accesses in the snippet helper are valid.
