"use client";

import Link from "next/link";
import {
  useParams,
  useSearchParams,
} from "next/navigation";
import {
  Suspense,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
  type TouchEvent,
} from "react";
import QuoteBlock from "../../../components/QuoteBlock";
import type { QAAnswer, ReadingPage } from "../../../data/mock-conversations";
import { usePersistentState } from "../../../hooks/usePersistentState";
import { askApi, AskError, reportCorrection } from "../../../lib/api";
import type { CorrectionRequest } from "../../../lib/api";
import { upsertProgress } from "../../../lib/readingProgress";

type Lang = "en" | "mr";

type ChatTurn = {
  question: string;
  answer: QAAnswer;
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
    whyThisPassage: string;
    askPlaceholderFirst: string;
    askPlaceholderFollowUp: string;
    ask: string;
    loading: string;
    errorGeneric: string;
    errorNotReadable: string;
    suggestCorrection: string;
    correctionPlaceholder: string;
    submitCorrection: string;
    cancelCorrection: string;
    correctionSent: string;
    correctionSending: string;
    correctionError: string;
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
      "Ask a question about this work — the answer draws on passages from this text.",
    youAsked: "You asked",
    whyThisPassage: "Why this passage:",
    askPlaceholderFirst: "Ask about this work...",
    askPlaceholderFollowUp: "Ask a follow-up...",
    ask: "Ask",
    loading: "Searching this work...",
    errorGeneric: "Couldn't load an answer. Please try again.",
    errorNotReadable: "This work isn't available to read yet.",
    suggestCorrection: "suggest a correction",
    correctionPlaceholder: "Edit the paragraph text…",
    submitCorrection: "Submit",
    cancelCorrection: "Cancel",
    correctionSent: "Thank you — sent for review",
    correctionSending: "Sending…",
    correctionError: "Could not send — please try again.",
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
      "या ग्रंथाविषयी प्रश्न विचारा — उत्तर या मजकुरातील उतार्‍यांवर आधारित असेल.",
    youAsked: "तुम्ही विचारले",
    whyThisPassage: "हा उतारा का?:",
    askPlaceholderFirst: "या ग्रंथाविषयी विचारा...",
    askPlaceholderFollowUp: "पुढील प्रश्न विचारा...",
    ask: "विचारा",
    loading: "या ग्रंथातून शोधत आहोत...",
    errorGeneric: "उत्तर मिळवता आले नाही. कृपया पुन्हा प्रयत्न करा.",
    errorNotReadable: "हा ग्रंथ अद्याप वाचण्यासाठी उपलब्ध नाही.",
    suggestCorrection: "सुधारणा सुचवा",
    correctionPlaceholder: "परिच्छेदाचा मजकूर संपादित करा…",
    submitCorrection: "पाठवा",
    cancelCorrection: "रद्द करा",
    correctionSent: "धन्यवाद — पुनरावलोकनासाठी पाठवले",
    correctionSending: "पाठवत आहे…",
    correctionError: "पाठवता आले नाही — कृपया पुन्हा प्रयत्न करा.",
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

  // If a ?page= param is present (e.g. from a "Read in full" citation link
  // that carries readPage), parse it so we can jump to the right page after
  // the persistent state hydrates. NaN-safe: if the param is not an integer,
  // urlPage stays null and the persisted page is used unchanged.
  const urlPageRaw = search.get("page");
  const urlPage = urlPageRaw !== null ? parseInt(urlPageRaw, 10) : null;
  const hasUrlPage = urlPage !== null && !Number.isNaN(urlPage) && urlPage >= 1;

  // Reading position + drawer chat are scoped to this work and persisted
  // across visits so the devotee can leave and come back where they were.
  const [currentPage, setCurrentPage] = usePersistentState<number>(
    `gd:read:${slug}:page`,
    1,
  );
  const [messages, setMessages] = usePersistentState<ChatTurn[]>(
    // v2: drawer chat now stores work-scoped Q&A answers (F17). Bumping the key
    // discards old {framing, passage}-shaped entries the new renderer can't use.
    `gd:read:${slug}:chat:v2`,
    [],
  );
  const [draft, setDraft] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  // Drawer asks /api/ask — pending shows a loading row while waiting.
  const [pending, setPending] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);

  // Per-paragraph correction editor state.
  // activeCorrectionN: the para.n of the currently-open editor, or null.
  const [activeCorrectionN, setActiveCorrectionN] = useState<number | null>(null);
  // Draft text in the correction textarea, keyed by para.n.
  const [correctionDraft, setCorrectionDraft] = useState<string>("");
  // "sending" | "sent" | "error" | null — status of the last POST.
  const [correctionStatus, setCorrectionStatus] = useState<
    "sending" | "sent" | "error" | null
  >(null);
  const [hoveredN, setHoveredN] = useState<number | null>(null);

  // Slider scrub value: tracks the live drag position so "Page X of Y" updates
  // in real time without triggering a fetch on every tick. Commits (calls
  // setCurrentPage) only on pointer/keyboard release events.
  const [sliderValue, setSliderValue] = useState<number>(currentPage);

  // Real corpus fetch — re-runs whenever slug, lang, or currentPage changes.
  const [pageData, setPageData] = useState<ReadingPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // When a ?page= URL param is present, override the persisted page once on
  // mount. We use a ref so this override fires exactly once per navigation to
  // this URL (not on every re-render). The clamping to [1, totalPages] is
  // deferred until totalPages is available via the fetch; if the page is valid
  // before we have totalPages, we still apply it immediately and re-clamp below
  // once the fetch completes.
  const urlPageApplied = useRef(false);
  const correctionCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (hasUrlPage && !urlPageApplied.current) {
      urlPageApplied.current = true;
      // Apply immediately (pre-clamp). The fetch useEffect below will re-clamp
      // to [1, totalPages] once data arrives if needed.
      setCurrentPage(urlPage!);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasUrlPage]);

  // Reset correction editor when the page or work changes.
  useEffect(() => {
    if (correctionCloseTimer.current !== null) {
      clearTimeout(correctionCloseTimer.current);
      correctionCloseTimer.current = null;
    }
    setActiveCorrectionN(null);
    setCorrectionDraft("");
    setCorrectionStatus(null);
    setHoveredN(null);
  }, [slug, currentPage]);

  // Keep the slider handle in sync with the authoritative currentPage
  // whenever it changes via Prev/Next, URL deep-link, or fetch clamp.
  useEffect(() => {
    setSliderValue(currentPage);
  }, [currentPage]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    const qs = new URLSearchParams({ slug, page: String(currentPage) });
    if (lang) qs.set("lang", lang);
    fetch(`/api/read?${qs.toString()}`)
      .then(async (res) => {
        if (!res.ok) {
          // 404 means the work has no readable text yet — show a friendly
          // message rather than the raw "Error 404" / backend detail.
          if (res.status === 404) {
            throw new Error(lbl.errorNotReadable);
          }
          const body = await res.json().catch(() => ({})) as { error?: string };
          throw new Error(body.error ?? `Error ${res.status}`);
        }
        return res.json() as Promise<ReadingPage>;
      })
      .then((data) => {
        if (!cancelled) {
          setPageData(data);
          setLoading(false);
          // Clamp currentPage to [1, totalPages]. Needed when the ?page= URL
          // param was out of the valid range for this work. setCurrentPage is
          // a no-op if already in range, so this is safe to call always.
          setCurrentPage((p) => Math.max(1, Math.min(data.totalPages, p)));
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
        mode: "qa",
        question: q,
        lang,
        work: slug,
      });
      if (resp.kind !== "qa") {
        throw new AskError("Unexpected response shape", 500);
      }
      const turn: ChatTurn = {
        question: q,
        answer: resp,
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

  function openCorrectionEditor(n: number, body: string) {
    setActiveCorrectionN(n);
    setCorrectionDraft(body);
    setCorrectionStatus(null);
  }

  function closeCorrectionEditor() {
    setActiveCorrectionN(null);
    setCorrectionDraft("");
    setCorrectionStatus(null);
  }

  async function submitCorrection(n: number, original: string) {
    const edited = correctionDraft.trim();
    if (!edited || edited === original) {
      closeCorrectionEditor();
      return;
    }
    setCorrectionStatus("sending");
    const req: CorrectionRequest = {
      kind: "correction",
      slug,
      page: currentPage,
      paragraph: n,
      original,
      corrected: edited,
      lang,
      question: "",
      mode: "reading",
    };
    try {
      await reportCorrection(req);
      setCorrectionStatus("sent");
      // Auto-close after 2 s so the reader returns to normal.
      if (correctionCloseTimer.current !== null) {
        clearTimeout(correctionCloseTimer.current);
      }
      correctionCloseTimer.current = setTimeout(() => {
        correctionCloseTimer.current = null;
        closeCorrectionEditor();
      }, 2000);
    } catch {
      setCorrectionStatus("error");
    }
  }

  const total = pageData?.totalPages ?? 1;

  // Update the live scrub position without triggering a fetch. Called on
  // every change event (drag tick, arrow key press).
  function onSliderChange(e: ChangeEvent<HTMLInputElement>) {
    setSliderValue(parseInt(e.target.value, 10));
  }

  // Commit the final slider position to currentPage, which triggers the
  // fetch useEffect. Reading from the event target avoids stale-closure
  // issues since React may still be batching the onChange state update at
  // the time these events fire. Called on mouseup, touchend, and keyup.
  function commitSliderFromEvent(
    e:
      | MouseEvent<HTMLInputElement>
      | TouchEvent<HTMLInputElement>
      | KeyboardEvent<HTMLInputElement>,
  ) {
    const v = parseInt(e.currentTarget.value, 10);
    if (!Number.isNaN(v)) {
      setSliderValue(v);   // keep local state in sync
      setCurrentPage(v);   // commit → triggers fetch
    }
  }

  return (
    <>
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-6">
      <header
        className="mb-5 pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        {/* Back links — top-left to match chat + landing surfaces.
            When an origin URL is present via ?from= (e.g. a Q&A session or
            another book in the reader), the primary back link returns there
            instead of the reading landing. The Pravachan-specific link is
            kept below so that legacy bookmarks with backToPravachan semantics
            still show a labelled link (it points to the same returnTo, which
            for Pravachan flows IS the Pravachan page). */}
        <div className="mb-3 flex items-center gap-4">
          <Link
            href={returnTo ?? `/?mode=reading&lang=${lang}`}
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

      {/* Progress slider — draggable/clickable range input styled as the
          parchment progress bar. Scrubbing updates the live readout only;
          setCurrentPage (and the fetch) fire on pointer/keyboard release so
          we avoid a fetch-storm while the user drags. */}
      <div className="mb-6">
        <input
          type="range"
          min={1}
          max={total}
          step={1}
          value={sliderValue}
          onChange={onSliderChange}
          onMouseUp={commitSliderFromEvent}
          onTouchEnd={commitSliderFromEvent}
          onKeyUp={commitSliderFromEvent}
          aria-label={lbl.pageXofY(sliderValue, total)}
          aria-valuemin={1}
          aria-valuemax={total}
          aria-valuenow={sliderValue}
          className="gd-page-slider"
          style={
            {
              "--slider-pct": `${Math.min(100, Math.round(((sliderValue - 1) / Math.max(1, total - 1)) * 100))}%`,
            } as CSSProperties
          }
        />
        <div
          className={`mt-1.5 text-[12px] text-right ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {lbl.pageXofY(sliderValue, total)}
        </div>
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
          <div
            key={para.n}
            className="mb-7"
            onMouseEnter={() => setHoveredN(para.n)}
            onMouseLeave={() => setHoveredN(null)}
            onFocus={() => setHoveredN(para.n)}
            onBlur={() => setHoveredN(null)}
          >
            <div>
                {activeCorrectionN === para.n ? (
                  /* Inline correction editor */
                  <div>
                    <textarea
                      value={correctionDraft}
                      onChange={(e) => setCorrectionDraft(e.target.value)}
                      rows={4}
                      placeholder={lbl.correctionPlaceholder}
                      disabled={correctionStatus === "sending" || correctionStatus === "sent"}
                      className={`block w-full resize-none rounded-[6px] px-2.5 py-1.5 text-[16px] ${isMr ? "font-deva" : ""}`}
                      style={{
                        fontFamily: "var(--font-serif)",
                        color: "var(--text-primary)",
                        lineHeight: 1.7,
                        border: "1px solid var(--accent-maroon)",
                        background: "var(--bg-surface)",
                        outline: "none",
                      }}
                    />
                    <div className="mt-2 flex items-center gap-3">
                      {correctionStatus === "sent" ? (
                        <span
                          className={`text-[13px] ${isMr ? "font-deva" : ""}`}
                          style={{ color: "var(--accent-maroon)" }}
                        >
                          {lbl.correctionSent}
                        </span>
                      ) : correctionStatus === "error" ? (
                        <>
                          <span
                            className={`text-[13px] ${isMr ? "font-deva" : ""}`}
                            style={{ color: "var(--accent-maroon)" }}
                          >
                            {lbl.correctionError}
                          </span>
                          <button
                            type="button"
                            onClick={() => void submitCorrection(para.n, para.body)}
                            className={`text-[13px] underline ${isMr ? "font-deva" : ""}`}
                            style={{ color: "var(--accent-maroon)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                          >
                            {lbl.submitCorrection}
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            onClick={() => void submitCorrection(para.n, para.body)}
                            disabled={correctionStatus === "sending"}
                            className={`rounded-[4px] px-3 py-1 text-[13px] font-semibold disabled:opacity-50 ${isMr ? "font-deva" : ""}`}
                            style={{
                              background: "#6B1F1F",
                              color: "#F4EAC9",
                              border: "1px solid #4F1414",
                              cursor: "pointer",
                            }}
                          >
                            {correctionStatus === "sending" ? lbl.correctionSending : lbl.submitCorrection}
                          </button>
                          <button
                            type="button"
                            onClick={closeCorrectionEditor}
                            className={`text-[13px] ${isMr ? "font-deva" : ""}`}
                            style={{ color: "var(--text-secondary)", background: "none", border: "none", cursor: "pointer", padding: 0 }}
                          >
                            {lbl.cancelCorrection}
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  /* Normal paragraph display */
                  <p
                    className="text-[17.5px]"
                    style={{
                      color: "var(--text-primary)",
                      lineHeight: 1.7,
                    }}
                  >
                    {para.body}
                  </p>
                )}
                {/* Correction affordance — shown only when editor is not open for this para. */}
                {activeCorrectionN !== para.n && (
                  <button
                    type="button"
                    onClick={() => openCorrectionEditor(para.n, para.body)}
                    className={`mt-1 text-[11px] ${isMr ? "font-deva" : ""}`}
                    aria-label={`${lbl.suggestCorrection} ¶${para.n}`}
                    style={{
                      color: "var(--text-tertiary)",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      padding: 0,
                      display: "block",
                      opacity: hoveredN === para.n ? 1 : 0,
                      transition: "opacity 150ms ease",
                    }}
                  >
                    ✏ {lbl.suggestCorrection}
                  </button>
                )}
            </div>
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
              {/* QA answer: framing paragraph(s), citations (QuoteBlock +
                  whyChosen rationale), optional synthesis. */}
              {m.answer.framing ? (
                <p
                  className={`mb-3 text-[14px] ${isMr ? "font-deva" : ""}`}
                  style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
                >
                  {m.answer.framing}
                </p>
              ) : null}
              {m.answer.citations.map((c, ci) => (
                <div key={ci} className="mb-4">
                  <QuoteBlock quote={c.quote} lang={lang} />
                  {c.whyChosen ? (
                    <p
                      className={`mt-1.5 text-[13px] leading-snug ${isMr ? "font-deva" : ""}`}
                      style={{ color: "var(--text-secondary)" }}
                    >
                      <span
                        style={{ color: "var(--accent-maroon)", fontWeight: 600 }}
                      >
                        {lbl.whyThisPassage}
                      </span>{" "}
                      {c.whyChosen}
                    </p>
                  ) : null}
                </div>
              ))}
              {m.answer.synthesis ? (
                <p
                  className={`mt-2 text-[14px] ${isMr ? "font-deva" : ""}`}
                  style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
                >
                  {m.answer.synthesis}
                </p>
              ) : null}
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
