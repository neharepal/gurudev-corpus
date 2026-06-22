"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import AnswerToolbar from "../../components/AnswerToolbar";
import QuoteBlock from "../../components/QuoteBlock";
import { usePersistentState } from "../../hooks/usePersistentState";
import {
  type ModeId,
  type PravachanAnswer,
  type QAAnswer,
  type Quote,
} from "../../data/mock-conversations";
import {
  askApiStream,
  AskError,
  type StreamEvent,
} from "../../lib/api";

type Lang = "en" | "mr";

// Language-aware UI labels for the chat surface. Verbatim quote bodies
// stay in their original language (ADR-007); shell + section labels
// switch with the toggle. The answer content itself — framing, rationale,
// synthesis — comes pre-translated from the API per ADR-010, so the page
// is otherwise language-blind.
const L: Record<
  Lang,
  {
    backToStart: string;
    you: string;
    gurudevSangrah: string;
    whyThisPassage: string;
    whyThisStory: string;
    askPlaceholder: string;
    send: string;
    framingFollowUp1: string;
    framingFollowUpN: string;
    sectionThesis: string;
    sectionGurudevsWords: string;
    sectionStories: string;
    sectionYourQuestion: string;
    worksReferenced: string;
    loading: string;
    errorNoQuestion: string;
    errorGeneric: string;
    errorBadResponse: string;
  }
> = {
  en: {
    backToStart: "◁ Back to start",
    you: "You",
    gurudevSangrah: "Gurudev Sangrah",
    whyThisPassage: "Why this passage:",
    whyThisStory: "Why this story:",
    askPlaceholder: "Ask a follow-up...",
    send: "Send",
    framingFollowUp1: "Here is another passage that touches on this:",
    framingFollowUpN: "And this passage may also be relevant:",
    sectionThesis: "Thesis",
    sectionGurudevsWords: "Gurudev's words",
    sectionStories: "Stories",
    sectionYourQuestion: "Your question",
    worksReferenced: "Works referenced",
    loading: "Searching the literature...",
    errorNoQuestion: "No question provided. Go back to start and ask something.",
    errorGeneric: "Couldn't load the answer. Please try again.",
    errorBadResponse: "Unexpected response from the corpus.",
  },
  mr: {
    backToStart: "◁ सुरुवातीला परत",
    you: "तुम्ही",
    gurudevSangrah: "गुरुदेव संग्रह",
    whyThisPassage: "हा उतारा का?:",
    whyThisStory: "ही आठवण का?:",
    askPlaceholder: "पुढील प्रश्न विचारा...",
    send: "पाठवा",
    framingFollowUp1: "हा आणखी एक उतारा या विषयाशी संबंधित आहे:",
    framingFollowUpN: "आणि हाही उतारा संबंधित असू शकतो:",
    sectionThesis: "मांडणी",
    sectionGurudevsWords: "गुरुदेवांचे शब्द",
    sectionStories: "आठवणी",
    sectionYourQuestion: "तुमचा प्रश्न",
    worksReferenced: "संदर्भ",
    loading: "साहित्यातून शोधत आहोत...",
    errorNoQuestion: "प्रश्न नाही. सुरुवातीला परत जाऊन प्रश्न विचारा.",
    errorGeneric: "उत्तर मिळवता आले नाही. कृपया पुन्हा प्रयत्न करा.",
    errorBadResponse: "अनपेक्षित प्रतिसाद.",
  },
};

type FollowUpTurn = {
  question: string;
  framing: string;
  quote: Quote;
  whyChosen: string;
};

// Tiny deterministic hash so the localStorage key stays compact regardless
// of question length. Not cryptographic — just a stable bucket id.
function hashQuestion(q: string | null): string {
  if (!q) return "default";
  let h = 0;
  for (let i = 0; i < q.length; i++) {
    h = (h * 31 + q.charCodeAt(i)) | 0;
  }
  // Convert to unsigned, then base36 for a short readable suffix.
  return (h >>> 0).toString(36);
}

// Pick a follow-up citation by cycling through whatever the current API
// answer surfaced. Q&A citations carry both quote and whyChosen; Pravachan
// examples use whyThisExample which we treat as the rationale.
// When the real backend wires up per-follow-up retrieval, this helper goes
// away and each follow-up triggers its own askApi call.
// Returns null for meta-mode Q&A answers (no citations to cycle through).
function pickCitation(
  answer: QAAnswer | PravachanAnswer,
  index: number,
): { quote: Quote; whyChosen: string } | null {
  if (answer.kind === "qa") {
    const n = answer.citations.length;
    if (n === 0) return null;
    const c = answer.citations[index % n];
    return { quote: c.quote, whyChosen: c.whyChosen };
  }
  const n = answer.examples.length;
  if (n === 0) return null;
  const ex = answer.examples[index % n];
  return { quote: ex.quote, whyChosen: ex.whyThisExample };
}

// `useSearchParams` requires a Suspense boundary on the static-rendering path
// in Next 15 — wrap the body once at the route entry.
export default function ChatPageRoute() {
  return (
    <Suspense fallback={null}>
      <ChatPage />
    </Suspense>
  );
}

function ChatPage() {
  const search = useSearchParams();

  const modeFromUrl = (search.get("mode") as ModeId | null) ?? "qa";
  const langFromUrl = (search.get("lang") as Lang | null) ?? "en";
  const questionFromUrl = search.get("q");

  const mode = modeFromUrl;
  const lang = langFromUrl;
  const lbl = L[lang];
  const [followUp, setFollowUp] = useState("");
  // Conversation identity = (mode, question). Each unique opening question
  // is a distinct thread — going back to landing and asking a new question
  // must NOT inherit the previous question's follow-ups.
  const questionKey = hashQuestion(questionFromUrl);
  const [followUps, setFollowUps] = usePersistentState<FollowUpTurn[]>(
    `gd:chat:${mode}:${questionKey}:followups`,
    [],
  );

  // Initial answer comes from /api/ask. Loading + error states track the
  // initial fetch only; follow-ups reuse the cached answer for citation
  // cycling until per-follow-up retrieval is wired (POST_DEMO_TODO §2).
  const [answer, setAnswer] = useState<QAAnswer | PravachanAnswer | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Diagnostic counter for streaming events. Surfaced in the answer area so
  // we can tell at a glance whether the SSE handler is firing during the
  // perceived "wait" period. Reset to 0 on every new question.
  const [debugEventCount, setDebugEventCount] = useState(0);

  // Fetch the initial answer whenever the conversation identity changes.
  // Cancellable via AbortController so a fast back/forward doesn't race.
  //
  // Per RFC-010 this is now a streaming fetch: events arrive over SSE and we
  // build the answer state progressively. The loading state turns off on
  // the FIRST piece of content (not when the whole response finishes), so the
  // user sees text the moment Claude starts generating instead of staring at
  // a spinner for 30+ seconds.
  useEffect(() => {
    const q = questionFromUrl?.trim();
    if (!q) {
      setLoading(false);
      setError(L[lang].errorNoQuestion);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    setAnswer(null);
    setDebugEventCount(0);

    // Initial draft per mode — empty fields the LLM will fill in.
    const initialDraft: Record<string, unknown> =
      mode === "qa"
        ? { kind: "qa", question: "", framing: "", citations: [] }
        : { kind: "pravachan", question: "", examples: [] };

    let draft: Record<string, unknown> = initialDraft;
    let firstContentSeen = false;
    const markContentArrived = () => {
      if (!firstContentSeen) {
        setLoading(false);
        firstContentSeen = true;
      }
    };

    // Throttle setAnswer to once per animation frame. Each SSE event mutates
    // `draft`; one rAF callback flushes the latest draft to setAnswer. This
    // defends against React batching skipping frames when events burst, and
    // guarantees the UI redraws at least every ~16ms while updates pend.
    let renderPending = false;
    const scheduleRender = () => {
      if (renderPending) return;
      renderPending = true;
      requestAnimationFrame(() => {
        renderPending = false;
        setAnswer({ ...draft } as unknown as QAAnswer | PravachanAnswer);
      });
    };

    // Diagnostic: count events received. Surfaces in the loading text so you
    // can tell at a glance whether the React handler is firing during the
    // perceived "long wait" period.
    let eventCount = 0;
    let lastDebugSent = 0;
    const bumpDebug = () => {
      eventCount += 1;
      const now = Date.now();
      if (now - lastDebugSent > 100) {
        lastDebugSent = now;
        setDebugEventCount(eventCount);
      }
    };

    // Phase 2 (RFC-010): delta events carry dotted paths like
    // "citations.0.quote.body". This helper walks the path, creating
    // intermediate objects/arrays as needed, and applies `updater` to the leaf.
    const withPathUpdated = (
      obj: Record<string, unknown>,
      pathStr: string,
      updater: (current: unknown) => unknown,
    ): Record<string, unknown> => {
      const segs: Array<string | number> = pathStr
        .split(".")
        .map((s) => (/^\d+$/.test(s) ? parseInt(s, 10) : s));

      const recur = (cur: unknown, depth: number): unknown => {
        if (depth === segs.length) return updater(cur);
        const seg = segs[depth];
        if (typeof seg === "number") {
          const arr = Array.isArray(cur) ? [...cur] : [];
          arr[seg] = recur(arr[seg], depth + 1);
          return arr;
        }
        const next: Record<string, unknown> = {
          ...((cur && typeof cur === "object" && !Array.isArray(cur))
            ? (cur as Record<string, unknown>)
            : {}),
        };
        next[seg] = recur(next[seg], depth + 1);
        return next;
      };

      return recur(obj, 0) as Record<string, unknown>;
    };

    const handleEvent = (event: StreamEvent) => {
      bumpDebug();
      switch (event.type) {
        case "retrieval":
          return;
        case "delta": {
          // Path may be top-level ("framing", "synthesis") or nested
          // ("citations.0.quote.body", "examples.2.title"). Same handler.
          draft = withPathUpdated(draft, event.path, (current) => {
            return (typeof current === "string" ? current : "") + event.text;
          });
          scheduleRender();
          markContentArrived();
          return;
        }
        case "field":
          draft = { ...draft, [event.name]: event.value };
          scheduleRender();
          markContentArrived();
          return;
        case "field_close":
          return;
        case "array_item": {
          // Reconcile: replace the partially-built element with the final
          // value. By the time this fires, the delta typewriter has likely
          // already filled the same slot — the overwrite is a no-op visually
          // and a safety net if any delta got dropped.
          const prev = (draft[event.array] as unknown[] | undefined) ?? [];
          const next = [...prev];
          next[event.index] = event.value;
          draft = { ...draft, [event.array]: next };
          scheduleRender();
          markContentArrived();
          return;
        }
        case "done":
          // Reconcile: replace the progressively-built draft with the
          // fully-validated final response.
          if (event.response.kind === "reading") {
            setError(L[lang].errorBadResponse);
          } else {
            setAnswer(event.response as QAAnswer | PravachanAnswer);
          }
          setLoading(false);
          return;
        case "error":
          setError(event.message);
          setLoading(false);
          return;
      }
    };

    askApiStream({ mode, question: q, lang }, handleEvent, ctrl.signal).catch(
      (e: unknown) => {
        if ((e as { name?: string })?.name === "AbortError") return;
        const msg =
          e instanceof AskError ? e.message : L[lang].errorGeneric;
        setError(msg);
        setLoading(false);
      },
    );
    return () => ctrl.abort();
  }, [mode, lang, questionFromUrl]);

  function appendFollowUp() {
    const q = followUp.trim();
    if (!q || !answer) return;
    const index = followUps.length;
    const picked = pickCitation(answer, index);
    if (!picked) {
      // Meta-mode answers have no citations to cycle through. Skip the
      // follow-up rather than show an empty card — real backend will
      // issue a fresh /api/ask call per follow-up (POST_DEMO_TODO §2).
      setFollowUp("");
      return;
    }
    setFollowUps((prev) => [
      ...prev,
      {
        question: q,
        framing: index === 0 ? lbl.framingFollowUp1 : lbl.framingFollowUpN,
        quote: picked.quote,
        whyChosen: picked.whyChosen,
      },
    ]);
    setFollowUp("");
  }

  function submitFollowUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    appendFollowUp();
  }

  function onFollowUpKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      appendFollowUp();
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-6">
      {/* Mini header — just the back link now. Mode is no longer switchable
          from this surface (user 2026-06-15); start a fresh question to
          change modes. */}
      <header
        className="mb-5 flex items-center pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        <Link
          href="/"
          className={`text-[14px] ${lang === "mr" ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {lbl.backToStart}
        </Link>
      </header>

      <section className="flex-1">
        {/* Show the question the user just asked. Fall back to the answer's
            echo of the question (set by the backend) if the URL has none. */}
        <div className="mb-8">
          <div
            className={`gd-label mb-1 ${lang === "mr" ? "font-deva" : ""}`}
            style={{ color: "var(--text-secondary)" }}
          >
            {lbl.you}
          </div>
          <p
            className={`text-[16.5px] ${
              /[ऀ-ॿ]/.test(questionFromUrl ?? answer?.question ?? "")
                ? "font-deva"
                : ""
            }`}
            style={{ color: "var(--text-primary)" }}
          >
            {questionFromUrl ?? answer?.question ?? ""}
          </p>
        </div>

        {/* Answer body — loading, error, or content. */}
        <div className="mb-4">
          <div
            className={`gd-label mb-2 ${lang === "mr" ? "font-deva" : ""}`}
            style={{ color: "var(--accent-maroon)" }}
          >
            {lbl.gurudevSangrah}
            {debugEventCount > 0 ? (
              <span style={{ marginLeft: 12, fontFamily: "monospace", fontSize: 11, opacity: 0.5, fontWeight: "normal" }}>
                · {debugEventCount} stream events
              </span>
            ) : null}
          </div>
          {loading ? (
            <p
              className={`italic ${lang === "mr" ? "font-deva" : ""}`}
              style={{ color: "var(--text-tertiary)" }}
            >
              {lbl.loading}
              {debugEventCount > 0 ? (
                <span style={{ marginLeft: 12, fontFamily: "monospace", fontSize: 13, opacity: 0.7 }}>
                  · {debugEventCount} events
                </span>
              ) : null}
            </p>
          ) : error ? (
            <p
              className={lang === "mr" ? "font-deva" : ""}
              style={{ color: "var(--accent-maroon)" }}
            >
              {error}
            </p>
          ) : answer?.kind === "qa" ? (
            <QAAnswerBody answer={answer} lbl={lbl} lang={lang} />
          ) : answer?.kind === "pravachan" ? (
            <PravachanAnswerBody answer={answer} lbl={lbl} lang={lang} />
          ) : null}
        </div>

        {/* Toolbar at the foot of the answer — only show once the answer
            actually loaded. */}
        {answer ? (
          <div
            className="mb-8 pt-3"
            style={{ borderTop: "1px solid var(--border-soft)" }}
          >
            <AnswerToolbar lang={lang} />
          </div>
        ) : null}

        {/* Follow-up turns — each appended question + mock passage from
            the corpus. Replaces the previous noop submit. */}
        {followUps.map((turn, i) => (
          <div
            key={i}
            className="mb-8 pt-6"
            style={{ borderTop: "1px solid var(--border-soft)" }}
          >
            <div className="mb-6">
              <div
                className={`gd-label mb-1 ${lang === "mr" ? "font-deva" : ""}`}
                style={{ color: "var(--text-secondary)" }}
              >
                {lbl.you}
              </div>
              <p
                className={`text-[16.5px] ${
                  /[ऀ-ॿ]/.test(turn.question) ? "font-deva" : ""
                }`}
                style={{ color: "var(--text-primary)" }}
              >
                {turn.question}
              </p>
            </div>
            <div>
              <div
                className={`gd-label mb-2 ${lang === "mr" ? "font-deva" : ""}`}
                style={{ color: "var(--accent-maroon)" }}
              >
                {lbl.gurudevSangrah}
              </div>
              <p
                className={`mb-3 text-[16.5px] ${
                  lang === "mr" ? "font-deva" : ""
                }`}
              >
                {turn.framing}
              </p>
              <QuoteBlock quote={turn.quote} />
              <p
                className={`mt-2 text-[15px] leading-snug ${
                  lang === "mr" ? "font-deva" : ""
                }`}
                style={{ color: "var(--text-primary)" }}
              >
                <span
                  className={lang === "mr" ? "font-deva" : ""}
                  style={{ color: "var(--accent-maroon)", fontWeight: 600 }}
                >
                  {lbl.whyThisPassage}
                </span>{" "}
                {turn.whyChosen}
              </p>
            </div>
          </div>
        ))}
      </section>

      {/* Bottom-pinned follow-up — inline textarea + Send to match the
          landing-page composer pattern (Round-2 layout). */}
      <form
        onSubmit={submitFollowUp}
        className="mt-auto flex items-end gap-2 rounded-[8px] p-2"
        style={{
          background: "var(--bg-surface)",
          border: "1px solid var(--border-soft)",
        }}
      >
        <textarea
          value={followUp}
          onChange={(e) => setFollowUp(e.target.value)}
          onKeyDown={onFollowUpKey}
          rows={2}
          placeholder={lbl.askPlaceholder}
          aria-label={lbl.askPlaceholder}
          disabled={!answer}
          className={`block flex-1 resize-none bg-transparent px-3 py-2 text-[16px] outline-none ${
            lang === "mr" ? "font-deva" : ""
          }`}
          style={{
            fontFamily: lang === "mr" ? undefined : "var(--font-serif)",
            color: "var(--text-primary)",
            lineHeight: 1.55,
          }}
        />
        <button
          type="submit"
          disabled={!answer}
          className={`rounded-[5px] px-4 py-2 text-[13px] font-semibold disabled:opacity-50 ${
            lang === "mr" ? "font-deva" : ""
          }`}
          style={{
            background: "#6B1F1F",
            color: "#F4EAC9",
            border: "1px solid #4F1414",
            boxShadow: "inset 0 1px 0 rgba(255, 220, 170, 0.2)",
          }}
        >
          {lbl.send}
        </button>
      </form>
    </main>
  );
}

// Q&A answer body — per ADR-010, branches on citations.length:
//   - citations.length > 0  -> doctrinal layout (framing + quote blocks + optional synthesis)
//   - citations.length === 0 -> meta layout (framing as answer paragraph + optional references list)
function QAAnswerBody({
  answer,
  lbl,
  lang,
}: {
  answer: QAAnswer;
  lbl: (typeof L)[Lang];
  lang: Lang;
}) {
  const isMr = lang === "mr";

  // Meta layout — no quotes, no "Why this passage" lines, no synthesis.
  if (answer.citations.length === 0) {
    // Prefer `framingParagraphs` (real array, reliable) over splitting
    // `framing` on \n{2,} (LLMs often skip the newlines and emit one wall).
    const metaParagraphs =
      answer.framingParagraphs && answer.framingParagraphs.length > 0
        ? answer.framingParagraphs
        : answer.framing.split(/\n{2,}/);
    return (
      <div>
        {metaParagraphs.map((para, i) => (
          <p
            key={i}
            className={`mb-4 text-[16.5px] ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
          >
            {para}
          </p>
        ))}
        {answer.references && answer.references.length > 0 ? (
          <div className="mt-5">
            <div
              className={`gd-label mb-2 ${isMr ? "font-deva" : ""}`}
              style={{ color: "var(--accent-maroon)" }}
            >
              {lbl.worksReferenced}
            </div>
            <ul className="m-0 list-none p-0">
              {answer.references.map((ref, i) => {
                const isRefDeva = /[ऀ-ॿ]/.test(ref.workTitle);
                return (
                  <li
                    key={i}
                    className={`text-[15px] ${isRefDeva || isMr ? "font-deva" : ""}`}
                    style={{
                      color: "var(--text-secondary)",
                      lineHeight: 1.6,
                      marginBottom: 4,
                    }}
                  >
                    <span aria-hidden style={{ marginRight: 6 }}>—</span>
                    <span style={{ fontStyle: "italic" }}>{ref.workTitle}</span>
                    {ref.location ? `, ${ref.location}` : ""}
                    {ref.author ? ` · ${ref.author}` : ""}
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  // Doctrinal layout — unchanged from ADR-007.
  // Same paragraph-array fallback as meta: prefer the structured array
  // when present, otherwise split the string.
  const doctrinalParagraphs =
    answer.framingParagraphs && answer.framingParagraphs.length > 0
      ? answer.framingParagraphs
      : answer.framing.split(/\n{2,}/);
  return (
    <div>
      {doctrinalParagraphs.map((para, i) => (
        <p key={i} className={`mb-3 text-[16.5px] ${isMr ? "font-deva" : ""}`}>
          {para}
        </p>
      ))}
      {answer.citations.map((c, i) => (
        <div key={i} className="mb-6">
          <QuoteBlock quote={c.quote} />
          <p
            className={`mt-2 text-[15px] leading-snug ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-primary)" }}
          >
            <span
              className={isMr ? "font-deva" : ""}
              style={{ color: "var(--accent-maroon)", fontWeight: 600 }}
            >
              {lbl.whyThisPassage}
            </span>{" "}
            {c.whyChosen}
          </p>
        </div>
      ))}
      {answer.synthesis
        ? answer.synthesis.split(/\n{2,}/).map((para, i) => (
            <p
              key={i}
              className={`mt-4 text-[16.5px] ${isMr ? "font-deva" : ""}`}
              style={{ color: "var(--text-primary)" }}
            >
              {para}
            </p>
          ))
        : null}
    </div>
  );
}

// Pravachan brief revised 2026-06-14: 4 sections in fixed order
//   1. Your question (verbatim restatement of what the user asked)
//   2. Thesis (1-2 assistant sentences)
//   3. Gurudev's words (one canonical quote)
//   4. Examples (3-5 athvani, each with quote + "why this example" + read-in-full)
// Suggested-sequence section and bottom action buttons were dropped — the
// devotee orders the material themselves and copies what they want manually.
function PravachanAnswerBody({
  answer,
  lbl,
  lang,
}: {
  answer: PravachanAnswer;
  lbl: (typeof L)[Lang];
  lang: Lang;
}) {
  const isMr = lang === "mr";
  const isQuestionDeva = /[ऀ-ॿ]/.test(answer.question);
  return (
    <div>
      <PravachanSection heading={lbl.sectionYourQuestion} isDeva={isMr}>
        <blockquote
          className={`m-0 italic ${isQuestionDeva ? "font-deva" : ""}`}
          style={{
            borderLeft: "3px solid var(--border-soft)",
            paddingLeft: "16px",
            color: "var(--text-secondary)",
            fontSize: "16px",
            lineHeight: 1.6,
          }}
        >
          {answer.question}
        </blockquote>
      </PravachanSection>

      {answer.thesis ? (
        <PravachanSection heading={lbl.sectionThesis} isDeva={isMr}>
          <p className={`text-[16.5px] ${isMr ? "font-deva" : ""}`}>
            {answer.thesis}
          </p>
        </PravachanSection>
      ) : null}

      {answer.gurudevsWords ? (
        <PravachanSection heading={lbl.sectionGurudevsWords} isDeva={isMr}>
          <QuoteBlock quote={answer.gurudevsWords} />
        </PravachanSection>
      ) : null}

      <PravachanSection heading={lbl.sectionStories} isDeva={isMr}>
        <ol className="m-0 list-decimal pl-5">
          {answer.examples.map((ex, i) => (
            <li key={i} className="mb-6">
              <div
                className={`mb-1 text-[16.5px] font-semibold ${
                  /[ऀ-ॿ]/.test(ex.title) ? "font-deva" : ""
                }`}
                style={{ color: "var(--text-primary)" }}
              >
                {ex.title}
              </div>
              {ex.gloss ? (
                <div
                  className={`mb-1 text-[15.5px] ${
                    /[ऀ-ॿ]/.test(ex.gloss) ? "font-deva" : ""
                  }`}
                  style={{ color: "var(--text-secondary)" }}
                >
                  {ex.gloss}
                </div>
              ) : null}
              <QuoteBlock quote={ex.quote} />
              <div
                className={`mt-2 text-[15px] ${isMr ? "font-deva" : ""}`}
                style={{ color: "var(--text-primary)" }}
              >
                <span
                  className={isMr ? "font-deva" : ""}
                  style={{ color: "var(--accent-maroon)", fontWeight: 600 }}
                >
                  {lbl.whyThisStory}
                </span>{" "}
                {ex.whyThisExample}
              </div>
              {ex.readSlug ? (
                <Link
                  href={`/read/${ex.readSlug}?from=${encodeURIComponent(
                    `/chat?mode=pravachan&lang=${lang}`,
                  )}&lang=${lang}`}
                  className={`mt-2 inline-block text-[14px] ${
                    isMr ? "font-deva" : ""
                  }`}
                  style={{ color: "var(--accent-maroon)" }}
                >
                  {isMr ? "→ संपूर्ण वाचा" : "→ Read in full"}
                </Link>
              ) : null}
            </li>
          ))}
        </ol>
      </PravachanSection>
    </div>
  );
}

function PravachanSection({
  heading,
  children,
  isDeva,
}: {
  heading: string;
  children: React.ReactNode;
  isDeva?: boolean;
}) {
  return (
    <section className="mb-7">
      <h2
        className={`mb-2 text-[18px] font-semibold ${
          isDeva ? "font-deva" : ""
        }`}
        style={{ color: "var(--accent-maroon)" }}
      >
        {heading}
      </h2>
      {children}
    </section>
  );
}
