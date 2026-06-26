"use client";

import Link from "next/link";
import {
  useParams,
  useSearchParams,
} from "next/navigation";
import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import type { ReadingPage } from "../../../data/mock-conversations";
import { usePersistentState } from "../../../hooks/usePersistentState";
import { askApi, AskError } from "../../../lib/api";
import { upsertProgress } from "../../../lib/readingProgress";

type Lang = "en" | "mr";

type ChatTurn = {
  question: string;
  framing: string;
  passage: string;
};

// Language-aware UI labels for the reading surface. Verbatim passages
// stay in their source language (ADR-007). Source titles inside the
// citation lines stay in their published language (canonical work
// titles are not translated). UI shell + framing + button labels switch
// with the language toggle.
const L: Record<
  Lang,
  {
    backToStart: string;
    backToPravachan: string;
    pageXofY: (current: number, total: number) => string;
    previous: string;
    next: string;
    askAboutThisWork: string;
    continueChat: (n: number) => string;
    aboutThisWork: string;
    closeChat: string;
    emptyHint: string;
    youAsked: string;
    framingFirst: string;
    framingFollowUp: string;
    askPlaceholderFirst: string;
    askPlaceholderFollowUp: string;
    ask: string;
    loading: string;
    errorGeneric: string;
  }
> = {
  en: {
    backToStart: "◁ Back to start",
    backToPravachan: "◁ Back to your Pravachan",
    pageXofY: (c, t) => `Page ${c} of ${t}`,
    previous: "◁ Previous",
    next: "Next ▷",
    askAboutThisWork: "Ask about this work",
    continueChat: (n) => `Continue chat (${n})`,
    aboutThisWork: "About this work",
    closeChat: "Close chat",
    emptyHint:
      "Ask a question about this work — answers cite a passage from the text below.",
    youAsked: "You asked",
    framingFirst: "Here is what this work says:",
    framingFollowUp: "And this passage may also be relevant:",
    askPlaceholderFirst: "Ask about this work...",
    askPlaceholderFollowUp: "Ask a follow-up...",
    ask: "Ask",
    loading: "Searching this work...",
    errorGeneric: "Couldn't load an answer. Please try again.",
  },
  mr: {
    backToStart: "◁ सुरुवातीला परत",
    backToPravachan: "◁ तुमच्या प्रवचनाकडे परत",
    pageXofY: (c, t) => `पान ${c} / ${t}`,
    previous: "◁ मागे",
    next: "पुढे ▷",
    askAboutThisWork: "या ग्रंथाविषयी विचारा",
    continueChat: (n) => `संवाद चालू ठेवा (${n})`,
    aboutThisWork: "या ग्रंथाविषयी",
    closeChat: "संवाद बंद करा",
    emptyHint:
      "या ग्रंथाविषयी प्रश्न विचारा — उत्तरात खालील मजकुरातून एक उतारा दिला जाईल.",
    youAsked: "तुम्ही विचारले",
    framingFirst: "या ग्रंथात याविषयी हे सांगितले आहे:",
    framingFollowUp: "आणि हाही उतारा संबंधित असू शकतो:",
    askPlaceholderFirst: "या ग्रंथाविषयी विचारा...",
    askPlaceholderFollowUp: "पुढील प्रश्न विचारा...",
    ask: "विचारा",
    loading: "या ग्रंथातून शोधत आहोत...",
    errorGeneric: "उत्तर मिळवता आले नाही. कृपया पुन्हा प्रयत्न करा.",
  },
};

// useSearchParams needs a Suspense boundary in Next 15.
export default function ReadingPageRoute() {
  return (
    <Suspense fallback={null}>
      <ReadingPage />
    </Suspense>
  );
}

function ReadingPage() {
  const params = useParams<{ slug: string }>();
  const search = useSearchParams();
  const slug = params?.slug ?? "pathway-to-god-in-hindi-literature";

  // If we arrived from a Pravachan brief via "Read in full", surface a
  // return link so the devotee can get back to their brief without losing it.
  const returnTo = search.get("from");
  const lang: Lang = (search.get("lang") as Lang | null) ?? "en";
  const lbl = L[lang];
  const isMr = lang === "mr";

  // Reading position + drawer chat are scoped to this work and persisted
  // across visits so the devotee can leave and come back where they were.
  const [currentPage, setCurrentPage] = usePersistentState<number>(
    `gd:read:${slug}:page`,
    1,
  );
  const [messages, setMessages] = usePersistentState<ChatTurn[]>(
    `gd:read:${slug}:chat`,
    [],
  );
  const [draft, setDraft] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  // Drawer asks /api/ask — pending shows a loading row while waiting.
  const [pending, setPending] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  // Real corpus fetch — re-runs whenever slug, lang, or currentPage changes.
  const [pageData, setPageData] = useState<ReadingPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    const qs = new URLSearchParams({ slug, page: String(currentPage) });
    if (lang) qs.set("lang", lang);
    fetch(`/api/read?${qs.toString()}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({})) as { error?: string };
          throw new Error(body.error ?? `Error ${res.status}`);
        }
        return res.json() as Promise<ReadingPage>;
      })
      .then((data) => {
        if (!cancelled) {
          setPageData(data);
          setLoading(false);
          // Record reading progress so the landing page can show a
          // "Continue reading" shelf. Upsert on every successful page load
          // (initial load + page turns) to keep lastReadAt fresh.
          upsertProgress({
            slug,
            workTitle: data.workTitle,
            page: currentPage,
            totalPages: data.totalPages,
            lastReadAt: Date.now(),
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFetchError(err instanceof Error ? err.message : "Failed to load");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug, lang, currentPage]);

  async function ask() {
    const q = draft.trim();
    if (!q || pending) return;
    // Open the drawer immediately so the user sees their question + loader
    // even before the API responds.
    setChatOpen(true);
    setPending(true);
    setAskError(null);
    setDraft("");
    try {
      const resp = await askApi({
        mode: "reading",
        question: q,
        lang,
        work: slug,
      });
      if (resp.kind !== "reading") {
        throw new AskError("Unexpected response shape", 500);
      }
      const isFollowUp = messages.length > 0;
      const turn: ChatTurn = {
        question: q,
        framing: isFollowUp ? lbl.framingFollowUp : lbl.framingFirst,
        passage: resp.passage,
      };
      setMessages((m) => [...m, turn]);
    } catch (e: unknown) {
      const msg =
        e instanceof AskError ? e.message : lbl.errorGeneric;
      setAskError(msg);
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void ask();
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void ask();
    }
  }

  const total = pageData?.totalPages ?? 1;
  const progress = Math.min(100, Math.round((currentPage / total) * 100));

  return (
    <>
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-6">
      <header
        className="mb-5 pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        {/* Back links — top-left to match chat + landing surfaces. */}
        <div className="mb-3 flex items-center gap-4">
          <Link
            href={`/?mode=reading&lang=${lang}`}
            className={`text-[14px] ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-secondary)" }}
          >
            {lbl.backToStart}
          </Link>
          {returnTo ? (
            <Link
              href={returnTo}
              className={`text-[14px] ${isMr ? "font-deva" : ""}`}
              style={{ color: "var(--accent-maroon)" }}
            >
              {lbl.backToPravachan}
            </Link>
          ) : null}
        </div>
        {/* Work title block. Canonical work title + author stay in their
            published language; chapter label is descriptive metadata so we
            translate it where we have an MR equivalent. */}
        <div>
          <div
            className="text-[20px] font-semibold leading-tight"
            style={{ color: "var(--text-primary)" }}
          >
            {pageData?.workTitle ?? slug.replace(/-/g, " ")}
          </div>
          <div
            className="text-[13.5px]"
            style={{ color: "var(--text-secondary)" }}
          >
            {pageData ? `${pageData.author} · ${pageData.chapter}` : ""}
          </div>
        </div>
      </header>

      {/* Progress bar — Page X of Y. */}
      <div className="mb-6 flex items-center gap-3">
        <div
          className="h-[6px] flex-1 overflow-hidden rounded-full"
          style={{ background: "var(--bg-panel)" }}
        >
          <div
            className="h-full"
            style={{
              width: `${progress}%`,
              background: "var(--accent-gold)",
              transition: "width 220ms ease",
            }}
          />
        </div>
        <span
          className={`text-[13px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {lbl.pageXofY(currentPage, total)}
        </span>
      </div>

      {/* Reading column, capped at ~70ch per ADR-006. */}
      <article className="mx-auto w-full max-w-reading flex-1">
        {loading ? (
          <p className="text-[15px] italic" style={{ color: "var(--text-tertiary)" }}>
            Loading…
          </p>
        ) : fetchError ? (
          <p className="text-[15px]" style={{ color: "var(--accent-maroon)" }}>
            {fetchError}
          </p>
        ) : (pageData?.paragraphs ?? []).map((para) => (
          <div key={para.n} className="mb-7 flex gap-4">
            <div
              className="shrink-0 pt-1 font-mono text-[12px]"
              style={{ color: "var(--text-secondary)" }}
            >
              ¶ {para.n}
            </div>
            <p
              className="text-[17.5px]"
              style={{
                color: "var(--text-primary)",
                lineHeight: 1.7,
              }}
            >
              {para.body}
            </p>
          </div>
        ))}
      </article>

      {/* Forward/back navigation. */}
      <div
        className="mt-6 flex items-center justify-between pt-4"
        style={{ borderTop: "1px solid var(--border-soft)" }}
      >
        <button
          type="button"
          onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
          disabled={currentPage <= 1}
          className={`rounded-[4px] px-3 py-1.5 text-[13px] disabled:opacity-40 ${
            isMr ? "font-deva" : ""
          }`}
          style={{
            background: "var(--bg-surface)",
            color: "var(--accent-maroon)",
            border: "1px solid var(--accent-maroon)",
          }}
        >
          {lbl.previous}
        </button>
        <button
          type="button"
          onClick={() => setCurrentPage((p) => Math.min(total, p + 1))}
          disabled={currentPage >= total}
          className={`rounded-[4px] px-3 py-1.5 text-[13px] disabled:opacity-40 ${
            isMr ? "font-deva" : ""
          }`}
          style={{
            background: "var(--bg-surface)",
            color: "var(--accent-maroon)",
            border: "1px solid var(--accent-maroon)",
          }}
        >
          {lbl.next}
        </button>
      </div>

      {/* Single Ask entry — opens the right-side chat drawer. All Q&A
          interaction now lives in the drawer so follow-ups don't require
          scrolling back to the foot of the article. */}
      <div className="mt-6 flex justify-center">
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-[14px] font-semibold ${
            isMr ? "font-deva" : ""
          }`}
          style={{
            background: "#6B1F1F",
            color: "#F4EAC9",
            border: "1px solid #4F1414",
            boxShadow: "0 2px 8px rgba(60, 30, 10, 0.18)",
            cursor: "pointer",
          }}
        >
          <span aria-hidden>💬</span>
          <span>
            {messages.length === 0
              ? lbl.askAboutThisWork
              : lbl.continueChat(messages.length)}
          </span>
        </button>
      </div>
    </main>
    {/* Right-side answer drawer — slides in from the right so it doesn't
        disturb the reading column. Fixed position, full viewport height,
        ~400px wide. Closeable. */}
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="Chat about this work"
      className="fixed right-0 top-0 z-30 flex h-screen w-[400px] flex-col transition-transform"
      style={{
        transform: chatOpen ? "translateX(0)" : "translateX(100%)",
        background: "var(--bg-surface)",
        borderLeft: "1px solid var(--border-soft)",
        boxShadow: "-6px 0 24px rgba(60, 30, 10, 0.12)",
        visibility: chatOpen ? "visible" : "hidden",
        pointerEvents: chatOpen ? "auto" : "none",
      }}
    >
      {/* Drawer header. */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        <div>
          <h2
            className={`text-[15px] font-semibold leading-tight ${
              isMr ? "font-deva" : ""
            }`}
            style={{ color: "#6B1F1F", fontFamily: "var(--font-serif)" }}
          >
            {lbl.aboutThisWork}
          </h2>
          <p
            className="text-[12px] leading-tight"
            style={{ color: "var(--text-secondary)" }}
          >
            {pageData?.workTitle ?? slug.replace(/-/g, " ")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setChatOpen(false)}
          aria-label={lbl.closeChat}
          className="text-[22px] leading-none"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            color: "var(--text-secondary)",
            padding: "0 4px",
          }}
        >
          ×
        </button>
      </div>

      {/* Conversation — scrollable. Empty state when nothing asked yet. */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {messages.length === 0 ? (
          <p
            className={`text-[14px] italic ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-tertiary)" }}
          >
            {lbl.emptyHint}
          </p>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={i > 0 ? "mt-6 pt-6" : ""}
              style={
                i > 0
                  ? { borderTop: "1px solid var(--border-soft)" }
                  : undefined
              }
            >
              {/* Question. */}
              <div className="mb-3">
                <div
                  className={`gd-label mb-1 ${isMr ? "font-deva" : ""}`}
                  style={{ color: "var(--text-secondary)" }}
                >
                  {lbl.youAsked}
                </div>
                <p
                  className={`text-[15px] ${
                    /[ऀ-ॿ]/.test(m.question) ? "font-deva" : ""
                  }`}
                  style={{ color: "var(--text-primary)" }}
                >
                  {m.question}
                </p>
              </div>
              {/* Answer. Framing is language-aware (set in ask()); passage
                  body stays in its source language; attribution likewise. */}
              <p
                className={`mb-2 text-[14px] ${isMr ? "font-deva" : ""}`}
                style={{ color: "var(--text-secondary)" }}
              >
                {m.framing}
              </p>
              <blockquote
                className={`gd-quote ${
                  /[ऀ-ॿ]/.test(m.passage) ? "font-deva" : ""
                }`}
              >
                {m.passage}
              </blockquote>
              <p className="gd-quote-attr">
                — {pageData?.workTitle ?? ""}, {pageData?.chapter ?? ""} · {pageData?.author ?? ""}
              </p>
            </div>
          ))
        )}
        {/* In-flight indicator while the API returns. */}
        {pending ? (
          <p
            className={`mt-6 text-[14px] italic ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-tertiary)" }}
          >
            {lbl.loading}
          </p>
        ) : null}
        {askError ? (
          <p
            className={`mt-4 text-[14px] ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--accent-maroon)" }}
          >
            {askError}
          </p>
        ) : null}
      </div>

      {/* Composer at drawer foot — keeps the conversation continuable. */}
      <form
        onSubmit={onSubmit}
        className="flex items-end gap-2 p-3"
        style={{ borderTop: "1px solid var(--border-soft)" }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
          rows={2}
          placeholder={
            messages.length === 0
              ? lbl.askPlaceholderFirst
              : lbl.askPlaceholderFollowUp
          }
          aria-label={lbl.ask}
          disabled={pending}
          className={`block flex-1 resize-none rounded-[6px] bg-transparent px-2.5 py-1.5 text-[15px] outline-none ${
            isMr ? "font-deva" : ""
          }`}
          style={{
            fontFamily: "var(--font-serif)",
            color: "var(--text-primary)",
            lineHeight: 1.5,
            border: "1px solid var(--border-soft)",
          }}
        />
        <button
          type="submit"
          disabled={pending}
          className={`rounded-[5px] px-3.5 py-2 text-[13px] font-semibold disabled:opacity-50 ${
            isMr ? "font-deva" : ""
          }`}
          style={{
            background: "#6B1F1F",
            color: "#F4EAC9",
            border: "1px solid #4F1414",
            boxShadow: "inset 0 1px 0 rgba(255, 220, 170, 0.2)",
          }}
        >
          {lbl.ask}
        </button>
      </form>
    </aside>
    </>
  );
}
