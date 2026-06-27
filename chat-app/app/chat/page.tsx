"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import AnswerToolbar from "../../components/AnswerToolbar";
import MeditativeLoader from "../../components/MeditativeLoader";
import QuoteBlock from "../../components/QuoteBlock";
import { authorDisplayName } from "../../lib/authors";
import {
  type ModeId,
  type PravachanAnswer,
  type QAAnswer,
} from "../../data/mock-conversations";
import {
  askApiStream,
  AskError,
  type HistoryTurn,
  type ReportCitation,
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
    sectionThesis: string;
    sectionGurudevsWords: string;
    sectionStories: string;
    sectionYourQuestion: string;
    worksReferenced: string;
    loading: string;
    gathering: string;
    composing: string;
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
    sectionThesis: "Thesis",
    sectionGurudevsWords: "Gurudev's words",
    sectionStories: "Stories",
    sectionYourQuestion: "Your question",
    worksReferenced: "Works referenced",
    loading: "Searching the literature...",
    gathering: "Gathering the passages...",
    composing: "Composing the answer...",
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
    sectionThesis: "मांडणी",
    sectionGurudevsWords: "गुरुदेवांचे शब्द",
    sectionStories: "आठवणी",
    sectionYourQuestion: "तुमचा प्रश्न",
    worksReferenced: "संदर्भ",
    loading: "साहित्यातून शोधत आहोत...",
    gathering: "उतारे जमा करत आहोत...",
    composing: "उत्तर रचत आहोत...",
    errorNoQuestion: "प्रश्न नाही. सुरुवातीला परत जाऊन प्रश्न विचारा.",
    errorGeneric: "उत्तर मिळवता आले नाही. कृपया पुन्हा प्रयत्न करा.",
    errorBadResponse: "अनपेक्षित प्रतिसाद.",
  },
};

// A follow-up turn carries its own streamed answer, just like the initial turn.
// `loading` / `streaming` / `error` mirror the initial-answer states.
type FollowUpTurn = {
  question: string;
  answer: QAAnswer | PravachanAnswer | null;
  loading: boolean;
  streaming: boolean;
  error: string | null;
};

// Extract the compact citation list from a completed answer, used to build
// the history payload sent to the backend so it can instruct the model not
// to repeat already-cited passages.
function extractCitedPassages(
  ans: QAAnswer | PravachanAnswer | null,
): HistoryTurn["cited_passages"] {
  if (!ans) return [];
  if (ans.kind === "qa") {
    // Guard: during streaming a citation can exist before its `quote` is filled.
    return (ans.citations ?? [])
      .filter((c) => c?.quote)
      .map((c) => ({
        workTitle: c.quote.workTitle,
        location: c.quote.location,
      }));
  }
  // Pravachan: gurudevsWords + examples. Guard against partially-streamed
  // items whose `quote` isn't populated yet (reading it would crash mid-stream).
  const out: HistoryTurn["cited_passages"] = [];
  if (ans.gurudevsWords?.workTitle) {
    out.push({
      workTitle: ans.gurudevsWords.workTitle,
      location: ans.gurudevsWords.location,
    });
  }
  for (const ex of ans.examples ?? []) {
    if (ex?.quote) {
      out.push({ workTitle: ex.quote.workTitle, location: ex.quote.location });
    }
  }
  return out;
}

// Extract richer citations (including quote body) for the RFC-004 report payload.
// Separate from extractCitedPassages (history-only, no body) to keep the types clean.
function extractReportCitations(
  ans: QAAnswer | PravachanAnswer | null,
): ReportCitation[] {
  if (!ans) return [];
  if (ans.kind === "qa") {
    return (ans.citations ?? [])
      .filter((c) => c?.quote)
      .map((c) => ({
        workTitle: c.quote.workTitle,
        location: c.quote.location,
        body: c.quote.body || undefined,
      }));
  }
  // Pravachan: gurudevsWords + examples.
  const out: ReportCitation[] = [];
  if (ans.gurudevsWords?.workTitle) {
    out.push({
      workTitle: ans.gurudevsWords.workTitle,
      location: ans.gurudevsWords.location,
      body: ans.gurudevsWords.body || undefined,
    });
  }
  for (const ex of ans.examples ?? []) {
    if (ex?.quote) {
      out.push({
        workTitle: ex.quote.workTitle,
        location: ex.quote.location,
        body: ex.quote.body || undefined,
      });
    }
  }
  return out;
}

// Build the answer prose text for RFC-004 reviewer context.
// Joins framing/synthesis for QA; thesis for Pravachan.
function buildAnswerText(ans: QAAnswer | PravachanAnswer | null): string | undefined {
  if (!ans) return undefined;
  if (ans.kind === "qa") {
    const parts: string[] = [];
    if (ans.framing) parts.push(ans.framing);
    if (ans.synthesis) parts.push(ans.synthesis);
    return parts.join("\n\n") || undefined;
  }
  // Pravachan: thesis is the answer voice text.
  return ans.thesis || undefined;
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
  const pathname = usePathname();

  const modeFromUrl = (search.get("mode") as ModeId | null) ?? "qa";
  const langFromUrl = (search.get("lang") as Lang | null) ?? "en";
  const questionFromUrl = search.get("q");

  // Build the current page URL to pass as the `from` origin on "Read in full"
  // links, so the reader's back link can return to this Q&A session.
  // Guard for SSR: usePathname/useSearchParams are safe in "use client" components
  // but we defensively check for a non-empty pathname.
  const searchStr = search.toString();
  const fromUrl = pathname
    ? `${pathname}${searchStr ? `?${searchStr}` : ""}`
    : undefined;

  const mode = modeFromUrl;
  const lang = langFromUrl;
  const lbl = L[lang];
  const [followUp, setFollowUp] = useState("");
  // Follow-ups are intentionally in-memory / session-scoped: reopening a
  // question always starts a fresh thread rather than rehydrating a prior
  // session's follow-ups from storage.
  const [followUps, setFollowUps] = useState<FollowUpTurn[]>([]);

  // Initial answer comes from /api/ask.
  const [answer, setAnswer] = useState<QAAnswer | PravachanAnswer | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  // `streaming` stays true from request start until the stream ends (done /
  // error / abort). `loading` turns off on the FIRST content; `streaming`
  // keeps a progress indicator alive through the later background waits
  // (e.g. the multi-second pause while the model grounds its citations).
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    setStreaming(true);
    setError(null);
    setAnswer(null);

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
    // coalesces bursty events into at most one redraw per frame.
    let renderPending = false;
    const scheduleRender = () => {
      if (renderPending) return;
      renderPending = true;
      requestAnimationFrame(() => {
        renderPending = false;
        setAnswer({ ...draft } as unknown as QAAnswer | PravachanAnswer);
      });
    };

    // Phase 2 (RFC-010): delta events carry dotted paths like
    // "citations.0.quote.body". This helper walks the path top-down,
    // copying each parent before descending, then applies `updater` at the leaf.
    // Iterative form (recursive form was silently throwing in production —
    // suspected closure-variable capture issue with the inner `recur`).
    const withPathUpdated = (
      obj: Record<string, unknown>,
      pathStr: string,
      updater: (current: unknown) => unknown,
    ): Record<string, unknown> => {
      const segs: Array<string | number> = pathStr
        .split(".")
        .map((s) => (/^\d+$/.test(s) ? parseInt(s, 10) : s));
      if (segs.length === 0) return obj;

      const result: Record<string, unknown> = { ...obj };
      // Walk down, creating shallow copies for each segment we descend into.
      // `parent` always points at the structure we'll mutate in this iteration.
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let parent: any = result;
      for (let i = 0; i < segs.length - 1; i++) {
        const seg = segs[i];
        const nextSeg = segs[i + 1];
        const existing = parent[seg];
        let copy: unknown;
        if (typeof nextSeg === "number") {
          // Next level is an array index → ensure THIS level holds an array.
          copy = Array.isArray(existing) ? [...existing] : [];
        } else {
          // Next level is an object key → ensure THIS level holds an object.
          copy =
            existing && typeof existing === "object" && !Array.isArray(existing)
              ? { ...(existing as Record<string, unknown>) }
              : {};
        }
        parent[seg] = copy;
        parent = copy;
      }
      const leaf = segs[segs.length - 1];
      parent[leaf] = updater(parent[leaf]);
      return result;
    };

    const handleEvent = (event: StreamEvent) => {
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
          setStreaming(false);
          return;
        case "error":
          setError(event.message);
          setLoading(false);
          setStreaming(false);
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
        setStreaming(false);
      },
    );
    return () => {
      ctrl.abort();
      setStreaming(false);
    };
  }, [mode, lang, questionFromUrl]);

  function appendFollowUp() {
    const q = followUp.trim();
    if (!q || !answer) return;

    // Build conversation history: every prior turn (initial + follow-ups),
    // carrying the question and a compact list of already-cited passages.
    // This is sent to the backend so the model can avoid repeating them.
    const history: HistoryTurn[] = [
      { question: questionFromUrl ?? "", cited_passages: extractCitedPassages(answer) },
      ...followUps.map((t) => ({
        question: t.question,
        cited_passages: extractCitedPassages(t.answer),
      })),
    ];

    // Add a placeholder turn immediately so the UI shows the question + loader.
    const turnIndex = followUps.length;
    setFollowUps((prev) => [
      ...prev,
      { question: q, answer: null, loading: true, streaming: true, error: null },
    ]);
    setFollowUp("");

    // Stream the follow-up answer from the backend, just like the initial request.
    const initialDraft: Record<string, unknown> =
      mode === "qa"
        ? { kind: "qa", question: "", framing: "", citations: [] }
        : { kind: "pravachan", question: "", examples: [] };

    let draft: Record<string, unknown> = initialDraft;
    let firstContentSeen = false;

    const markContentArrived = () => {
      if (!firstContentSeen) {
        firstContentSeen = true;
        setFollowUps((prev) => {
          const next = [...prev];
          next[turnIndex] = { ...next[turnIndex], loading: false };
          return next;
        });
      }
    };

    let renderPending = false;
    const scheduleRender = () => {
      if (renderPending) return;
      renderPending = true;
      requestAnimationFrame(() => {
        renderPending = false;
        const snapshot = { ...draft } as unknown as QAAnswer | PravachanAnswer;
        setFollowUps((prev) => {
          const next = [...prev];
          if (next[turnIndex]) {
            next[turnIndex] = { ...next[turnIndex], answer: snapshot };
          }
          return next;
        });
      });
    };

    const withPathUpdated = (
      obj: Record<string, unknown>,
      pathStr: string,
      updater: (current: unknown) => unknown,
    ): Record<string, unknown> => {
      const segs: Array<string | number> = pathStr
        .split(".")
        .map((s) => (/^\d+$/.test(s) ? parseInt(s, 10) : s));
      if (segs.length === 0) return obj;
      const result: Record<string, unknown> = { ...obj };
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let parent: any = result;
      for (let i = 0; i < segs.length - 1; i++) {
        const seg = segs[i];
        const nextSeg = segs[i + 1];
        const existing = parent[seg];
        let copy: unknown;
        if (typeof nextSeg === "number") {
          copy = Array.isArray(existing) ? [...existing] : [];
        } else {
          copy =
            existing && typeof existing === "object" && !Array.isArray(existing)
              ? { ...(existing as Record<string, unknown>) }
              : {};
        }
        parent[seg] = copy;
        parent = copy;
      }
      const leaf = segs[segs.length - 1];
      parent[leaf] = updater(parent[leaf]);
      return result;
    };

    const handleEvent = (event: StreamEvent) => {
      switch (event.type) {
        case "retrieval":
          return;
        case "delta": {
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
          const prev = (draft[event.array] as unknown[] | undefined) ?? [];
          const next = [...prev];
          next[event.index] = event.value;
          draft = { ...draft, [event.array]: next };
          scheduleRender();
          markContentArrived();
          return;
        }
        case "done":
          if (event.response.kind !== "reading") {
            setFollowUps((prev) => {
              const next = [...prev];
              next[turnIndex] = {
                ...next[turnIndex],
                answer: event.response as QAAnswer | PravachanAnswer,
                loading: false,
                streaming: false,
              };
              return next;
            });
          } else {
            setFollowUps((prev) => {
              const next = [...prev];
              next[turnIndex] = {
                ...next[turnIndex],
                loading: false,
                streaming: false,
                error: lbl.errorBadResponse,
              };
              return next;
            });
          }
          return;
        case "error":
          setFollowUps((prev) => {
            const next = [...prev];
            next[turnIndex] = {
              ...next[turnIndex],
              loading: false,
              streaming: false,
              error: event.message,
            };
            return next;
          });
          return;
      }
    };

    askApiStream(
      { mode, question: q, lang, history },
      handleEvent,
    ).catch((e: unknown) => {
      if ((e as { name?: string })?.name === "AbortError") return;
      const msg = e instanceof AskError ? e.message : lbl.errorGeneric;
      setFollowUps((prev) => {
        const next = [...prev];
        next[turnIndex] = {
          ...next[turnIndex],
          loading: false,
          streaming: false,
          error: msg,
        };
        return next;
      });
    });
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
          </div>
          {loading ? (
            <MeditativeLoader label={lbl.loading} isDeva={lang === "mr"} />
          ) : error ? (
            <p
              className={lang === "mr" ? "font-deva" : ""}
              style={{ color: "var(--accent-maroon)" }}
            >
              {error}
            </p>
          ) : answer?.kind === "qa" ? (
            <QAAnswerBody answer={answer} lbl={lbl} lang={lang} fromUrl={fromUrl} />
          ) : answer?.kind === "pravachan" ? (
            <PravachanAnswerBody answer={answer} lbl={lbl} lang={lang} fromUrl={fromUrl} />
          ) : null}

          {/* Inline progress: the first content has appeared but the stream is
              still running (e.g. the multi-second wait while citations are
              grounded). Keep a calm signal that work is in flight. */}
          {!loading && streaming && !error ? (
            <MeditativeLoader
              compact
              isDeva={lang === "mr"}
              label={
                (() => {
                  const a = answer as
                    | { classification?: string; citations?: unknown[] }
                    | null;
                  const awaitingCitations =
                    a?.classification === "doctrinal" &&
                    (a?.citations?.length ?? 0) === 0;
                  return awaitingCitations ? lbl.gathering : lbl.composing;
                })()
              }
            />
          ) : null}
        </div>

        {/* Toolbar at the foot of the answer — only show once the answer
            actually loaded. */}
        {answer ? (
          <div
            className="mb-8 pt-3"
            style={{ borderTop: "1px solid var(--border-soft)" }}
          >
            <AnswerToolbar
              lang={lang}
              question={questionFromUrl ?? answer.question ?? ""}
              mode={mode}
              citations={extractReportCitations(answer)}
              answerText={buildAnswerText(answer)}
            />
          </div>
        ) : null}

        {/* Follow-up turns — each makes a real /api/ask call with conversation
            history so the model brings new material and understands context. */}
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
              {turn.loading ? (
                <MeditativeLoader label={lbl.loading} isDeva={lang === "mr"} />
              ) : turn.error ? (
                <p
                  className={lang === "mr" ? "font-deva" : ""}
                  style={{ color: "var(--accent-maroon)" }}
                >
                  {turn.error}
                </p>
              ) : turn.answer?.kind === "qa" ? (
                <QAAnswerBody answer={turn.answer} lbl={lbl} lang={lang} fromUrl={fromUrl} />
              ) : turn.answer?.kind === "pravachan" ? (
                <PravachanAnswerBody answer={turn.answer} lbl={lbl} lang={lang} fromUrl={fromUrl} />
              ) : null}

              {/* Inline streaming progress for this follow-up turn */}
              {!turn.loading && turn.streaming && !turn.error ? (
                <MeditativeLoader
                  compact
                  isDeva={lang === "mr"}
                  label={lbl.composing}
                />
              ) : null}
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
  fromUrl,
}: {
  answer: QAAnswer;
  lbl: (typeof L)[Lang];
  lang: Lang;
  fromUrl?: string;
}) {
  const isMr = lang === "mr";

  // Meta layout — no quotes, no "Why this passage" lines, no synthesis.
  // Guard: during streaming `citations` can be undefined before the first delta.
  if ((answer.citations ?? []).length === 0) {
    // Prefer `framingParagraphs` (real array, reliable) over splitting
    // `framing` on \n{2,} (LLMs often skip the newlines and emit one wall).
    // Guard: `framing` may be empty string or undefined early in streaming.
    const metaParagraphs =
      answer.framingParagraphs && answer.framingParagraphs.length > 0
        ? answer.framingParagraphs
        : (answer.framing ?? "").split(/\n{2,}/).filter(Boolean);
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
                    {ref.author ? ` · ${authorDisplayName(ref.author)}` : ""}
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
  // Guard: `framing` may be empty string or undefined early in streaming.
  const doctrinalParagraphs =
    answer.framingParagraphs && answer.framingParagraphs.length > 0
      ? answer.framingParagraphs
      : (answer.framing ?? "").split(/\n{2,}/).filter(Boolean);
  return (
    <div>
      {doctrinalParagraphs.map((para, i) => (
        <p key={i} className={`mb-3 text-[16.5px] ${isMr ? "font-deva" : ""}`}>
          {para}
        </p>
      ))}
      {/* Guard: filter to citations whose quote.body is present before rendering.
          During streaming a citation slot can exist before its quote is filled;
          QuoteBlock returns null for missing body but c.whyChosen beside it
          would still appear stray — skip the whole item until it's renderable. */}
      {(answer.citations ?? []).filter((c) => c?.quote?.body).map((c, i) => (
        <div key={i} className="mb-6">
          <QuoteBlock quote={c.quote} lang={lang} fromUrl={fromUrl} />
          {c.whyChosen ? (
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
          ) : null}
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
  fromUrl,
}: {
  answer: PravachanAnswer;
  lbl: (typeof L)[Lang];
  lang: Lang;
  fromUrl?: string;
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
          <QuoteBlock quote={answer.gurudevsWords} lang={lang} fromUrl={fromUrl} />
        </PravachanSection>
      ) : null}

      <PravachanSection heading={lbl.sectionStories} isDeva={isMr}>
        <ol className="m-0 list-decimal pl-5">
          {/* Guard: filter to examples that have at least a title so we never
              render a completely empty list item mid-stream. quote.body is
              guarded inside QuoteBlock; whyThisExample is guarded inline. */}
          {(answer.examples ?? []).filter((ex) => ex?.title).map((ex, i) => (
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
              {/* QuoteBlock already returns null if !quote?.body; pass
                  ex.quote as-is (may be undefined until its delta arrives). */}
              <QuoteBlock quote={ex.quote} lang={lang} fromUrl={fromUrl} />
              {/* Guard: skip the "Why this story" line until the field arrives. */}
              {ex.whyThisExample ? (
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
              ) : null}
              {ex.readSlug ? (
                <Link
                  href={(() => {
                    const qs = new URLSearchParams();
                    // Use the real current URL when available; fall back to a
                    // stable pravachan URL so old bookmarks keep working.
                    qs.set("from", fromUrl ?? `/chat?mode=pravachan&lang=${lang}`);
                    qs.set("lang", lang);
                    return `/read/${ex.readSlug}?${qs.toString()}`;
                  })()}
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
