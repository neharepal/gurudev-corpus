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
  if (typeof window === "undefined") return;
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
  let merged: SavedThread = thread;
  if (prior) {
    // Preserve createdAt. Also preserve updatedAt when the content is unchanged
    // (e.g. merely reopening a thread re-runs the save), so viewing a thread
    // doesn't reorder history — only a new answer/follow-up bumps it to the top.
    const unchanged =
      JSON.stringify({ a: prior.answer, f: prior.followUps }) ===
      JSON.stringify({ a: thread.answer, f: thread.followUps });
    merged = {
      ...thread,
      createdAt: prior.createdAt,
      updatedAt: unchanged ? prior.updatedAt : thread.updatedAt,
    };
  }
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
