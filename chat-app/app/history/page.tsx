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
