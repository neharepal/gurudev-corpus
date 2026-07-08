"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Lang } from "./ModeTabs";
import { loadThreads, type SavedThread } from "../lib/conversationHistory";
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
