"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Lang } from "./ModeTabs";
import {
  loadThreads,
  removeThread,
  type SavedThread,
} from "../lib/conversationHistory";
import { answerSnippet } from "../lib/answerSnippet";

const RECENT = 3; // shelf shows the most recent N Q&A threads

export default function YourQuestionsShelf({ lang }: { lang: Lang }) {
  const [threads, setThreads] = useState<SavedThread[]>([]);
  const isMr = lang === "mr";

  useEffect(() => {
    // Show only threads in the current UI language — English mode lists English
    // threads, Marathi mode lists Marathi ones (no cross-language pollution).
    setThreads(loadThreads().filter((t) => t.mode === "qa" && t.lang === lang));
  }, [lang]);

  // Inline delete — previously the user had to click "See all →" to reach a
  // history page with delete affordances. Now the × sits on each row so the
  // most common cleanup (drop a stale question from the shelf) is one tap
  // from the landing page. 2026-07-21 report.
  function handleDelete(id: string, question: string, ev: React.MouseEvent) {
    ev.preventDefault();
    ev.stopPropagation();
    const confirmMsg = isMr
      ? `हा प्रश्न काढून टाकायचा?\n\n${question}`
      : `Delete this question?\n\n${question}`;
    if (!window.confirm(confirmMsg)) return;
    removeThread(id);
    setThreads((prev) => prev.filter((t) => t.id !== id));
  }

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
          href={`/history?lang=${lang}`}
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
            <li key={t.id} className="group relative">
              <Link
                href={`/chat?mode=${t.mode}&lang=${t.lang}&q=${encodeURIComponent(t.question)}`}
                className="block rounded-[6px] px-3 py-2.5 pr-9 transition-all"
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
              <button
                type="button"
                onClick={(e) => handleDelete(t.id, t.question, e)}
                aria-label={isMr ? "प्रश्न काढून टाका" : "Delete this question"}
                title={isMr ? "काढून टाका" : "Delete"}
                className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full text-[16px] leading-none opacity-40 transition-opacity hover:opacity-100 hover:bg-white/60 focus:opacity-100 focus:outline-none"
                style={{ color: "#5A2520" }}
              >
                ×
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
