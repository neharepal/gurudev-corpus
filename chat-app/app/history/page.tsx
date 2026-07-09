"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { Lang } from "../../components/ModeTabs";
import {
  loadThreads,
  removeThread,
  clearThreadsByLang,
  type SavedThread,
} from "../../lib/conversationHistory";
import { answerSnippet } from "../../lib/answerSnippet";

function relDate(ms: number, isMr: boolean): string {
  const d = Math.floor((Date.now() - ms) / 86400000);
  if (d <= 0) return isMr ? "आज" : "today";
  if (d === 1) return isMr ? "काल" : "yesterday";
  return isMr ? `${d} दिवसांपूर्वी` : `${d} days ago`;
}

export default function HistoryPageRoute() {
  return (
    <Suspense fallback={null}>
      <HistoryPage />
    </Suspense>
  );
}

function HistoryPage() {
  const search = useSearchParams();
  const lang: Lang = (search.get("lang") as Lang | null) ?? "en";
  const isMr = lang === "mr";
  const [threads, setThreads] = useState<SavedThread[]>([]);

  useEffect(() => {
    // Only show threads in the current UI language (no cross-language mixing).
    setThreads(loadThreads().filter((t) => t.lang === lang));
  }, [lang]);

  function handleRemove(id: string) {
    removeThread(id);
    setThreads(loadThreads().filter((t) => t.lang === lang));
  }
  function handleClearAll() {
    clearThreadsByLang(lang);
    setThreads([]);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-6">
      <header
        className="mb-5 flex items-center justify-between pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        <Link
          href={`/?lang=${lang}`}
          className={`text-[14px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {isMr ? "◁ मागे" : "◁ Back"}
        </Link>
        <span
          className={`text-[17px] font-semibold ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-primary)" }}
        >
          {isMr ? "तुमचे प्रश्न" : "Your questions"}
        </span>
        {threads.length > 0 ? (
          <button
            type="button"
            onClick={handleClearAll}
            className={`text-[13px] ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-tertiary)", background: "transparent" }}
          >
            {isMr ? "सर्व हटवा" : "Clear all"}
          </button>
        ) : (
          <span style={{ width: 52 }} />
        )}
      </header>

      {threads.length === 0 ? (
        <p
          className={`mt-10 text-center text-[15px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-tertiary)" }}
        >
          {isMr ? "अजून जतन केलेले प्रश्न नाहीत." : "No saved questions yet."}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {threads.map((t) => {
            const isDeva = /[ऀ-ॿ]/.test(t.question);
            const followN = t.followUps.length;
            const badge = isMr
              ? t.mode === "qa"
                ? "प्रश्नोत्तर"
                : "प्रवचन"
              : t.mode === "qa"
                ? "Q&A"
                : "Pravachan";
            const followLabel =
              followN > 0
                ? isMr
                  ? ` · ${followN} पाठपुरावा`
                  : ` · ${followN} follow-up${followN > 1 ? "s" : ""}`
                : "";
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
                      className={`rounded-full px-2 py-0.5 text-[11px] ${isMr ? "font-deva" : ""}`}
                      style={{ background: "rgba(122,46,42,0.12)", color: "#5A2520" }}
                    >
                      {badge}
                    </span>
                    <span
                      className={`text-[12px] ${isMr ? "font-deva" : ""}`}
                      style={{ color: "var(--text-tertiary)" }}
                    >
                      {relDate(t.updatedAt, isMr)}
                      {followLabel}
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
                  aria-label={isMr ? "हटवा" : "Delete"}
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
