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
import FontScaleControl from "../../../components/FontScaleControl";
import QuoteBlock from "../../../components/QuoteBlock";
import ReadingQaAnswer from "../../../components/ReadingQaAnswer";
import type {
  QAAnswer,
  ReadingQaAnswer as ReadingQaAnswerType,
  ReadingPage,
} from "../../../data/mock-conversations";
import { usePersistentState } from "../../../hooks/usePersistentState";
import { askApi, AskError, reportCorrection } from "../../../lib/api";
import { renderInlineMd } from "../../../lib/render-inline-md";
import { renderBlockMd } from "../../../lib/render-block-md";
import {
  isVerseParagraph,
  splitVerseBlocks,
  splitVerseCitation,
  mergeSentenceContinuations,
} from "../../../lib/verse-detection";
import type { CorrectionRequest } from "../../../lib/api";
import { upsertProgress } from "../../../lib/readingProgress";

type Lang = "en" | "mr";

// RFC-023: the drawer now stores either shape. Old cached QAAnswer entries
// from before the format migration still deserialise fine — the render
// branch below picks by `answer.format === "reading-qa"` and otherwise
// falls back to the QA render. Old entries lack `format` so they land in
// the QA fallback, which is exactly what the pre-RFC-023 render expected.
type ChatTurn = {
  question: string;
  answer: QAAnswer | ReadingQaAnswerType;
};

// Table of contents shape returned by /api/read-toc. Chapters carry the
// printed reader-page number they land on so a click can jump straight to
// that page. Sections group chapters under ## headings (भाग १, भाग २, …);
// works without ## headings return an empty `sections` and the TOC UI is
// hidden entirely (no dead affordance).
type TocChapter = { title: string; page: number };
// `page` is present when the section itself is a leaf (0 chapters underneath —
// e.g. MiM's standalone Chapter I as a `##`). Rendered as a clickable jump row
// in that case instead of a bare header.
type TocSection = { title: string | null; chapters: TocChapter[]; page?: number };
type TocData = {
  workSlug: string;
  workTitle: string;
  author: string;
  sections: TocSection[];
  flat: TocChapter[];
};

// Module-scope so the initial-state expressions below can consult it
// synchronously (before any TOC fetch has resolved). Any slug listed here
// causes the reader to inject a TOC page as displayed page 1, shifting
// every subsequent body page by +1. Keep in sync with the (identical) set
// used further down for render-time decisions — one source of truth.
//
// Add a slug here only after (1) its canonical text.md matches the actual
// source book (title, structure, size), (2) has clean ##/### chapter
// markers matching that source, (3) /read/{slug}/toc returns the expected
// sections, (4) Neha eyeballs the rendered TOC. See ADR-019 and memory
// `project_toc_allowlist`.
//
// `mysticism-in-maharashtra`: added 2026-08-03 after the full-book re-ingest
// (Surya OCR of IA scan `dli.ministry.14639`, 553-page 1933 monograph)
// replaced the previous 146-line preface-only canonical. Structure verified
// via /toc endpoint (7 sections: Preface + Chapter I standalone + 5 Parts
// with their chapters, 20 chapters total, 459 `####` sub-items).
const TOC_ALLOWED_SLUGS = new Set<string>([
  "kakanchi-pravachane",
  "mysticism-in-maharashtra",
  "bhagavadgita-as-pathway-to-god-realization",
]);

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
    backToAnswer: string;
    backToPrevious: string;
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
    yourNamePlaceholder: string;
    submitCorrection: string;
    cancelCorrection: string;
    correctionSent: string;
    correctionSending: string;
    correctionError: string;
    tocButton: string;
    tocDrawerTitle: string;
    closeToc: string;
    tocEmpty: string;
  }
> = {
  en: {
    backToStart: "◁ Back to start",
    backToPravachan: "◁ Back to your Pravachan",
    backToAnswer: "◁ Back to your answer",
    backToPrevious: "◁ Back",
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
    yourNamePlaceholder: "Your name (required)",
    submitCorrection: "Submit",
    cancelCorrection: "Cancel",
    correctionSent: "Thank you — sent for review",
    correctionSending: "Sending…",
    correctionError: "Could not send — please try again.",
    tocButton: "☰ Contents",
    tocDrawerTitle: "Contents",
    closeToc: "Close contents",
    tocEmpty: "No index available for this work.",
  },
  mr: {
    backToStart: "◁ सुरुवातीला परत",
    backToPravachan: "◁ तुमच्या प्रवचनाकडे परत",
    backToAnswer: "◁ तुमच्या उत्तराकडे परत",
    backToPrevious: "◁ मागे परत",
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
    yourNamePlaceholder: "तुमचे नाव (आवश्यक)",
    submitCorrection: "पाठवा",
    cancelCorrection: "रद्द करा",
    correctionSent: "धन्यवाद — पुनरावलोकनासाठी पाठवले",
    correctionSending: "पाठवत आहे…",
    correctionError: "पाठवता आले नाही — कृपया पुन्हा प्रयत्न करा.",
    tocButton: "☰ अनुक्रमणिका",
    tocDrawerTitle: "अनुक्रमणिका",
    closeToc: "अनुक्रमणिका बंद करा",
    tocEmpty: "या ग्रंथासाठी अनुक्रमणिका उपलब्ध नाही.",
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

  // If we arrived from a Q&A or Pravachan via "Read in full", surface a return
  // link so the devotee can get back to where they were without losing it.
  const returnTo = search.get("from");
  // The `from` URL encodes the origin surface in its own `?mode=` query (e.g.
  // `/chat?mode=qa&...`). Parse it so the back link reads "Back to your answer"
  // for Q&A vs "Back to your Pravachan" for pravachan — not a hardcoded label.
  const returnMode = (() => {
    if (!returnTo) return null;
    const qIdx = returnTo.indexOf("?");
    if (qIdx === -1) return null;
    try {
      return new URLSearchParams(returnTo.slice(qIdx + 1)).get("mode");
    } catch {
      return null;
    }
  })();
  // Content language vs UI language are two DIFFERENT things (2026-07-23):
  //   - contentLang comes from the URL. It selects which text.md to fetch
  //     for this book (a Marathi book has to load its Marathi file). This
  //     also flows into the correction request so we edit the right file.
  //   - uiLang comes from the user's persisted preference (the same
  //     `gd:lang` key the landing page uses). It drives labels, font, the
  //     answer language of the drawer's Q&A, and the back-link to home.
  //
  // Before the split, clicking a Marathi book flipped the whole UI to
  // Marathi even for an English-preferring reader. Split so the reader
  // stays in the language they chose while the book plays in its own.
  const contentLang: Lang = (search.get("lang") as Lang | null) ?? "en";
  const [uiLang] = usePersistentState<Lang>("gd:lang", "en");
  const lbl = L[uiLang];
  const isMr = uiLang === "mr";

  // If a ?page= param is present (e.g. from a "Read in full" citation link
  // that carries readPage), parse it so we can jump to the right page after
  // the persistent state hydrates. NaN-safe: if the param is not an integer,
  // urlPage stays null and the persisted page is used unchanged.
  //
  // URL contract: `?page=N` is the BACKEND page number (what the citation
  // enricher writes as `quote.readPage`). Persistent state + everything
  // else in this component works in DISPLAYED page numbering — when a
  // TOC page is injected (allow-listed slug), displayed = backend + 1.
  // Translate at the URL boundary so downstream state stays consistent.
  const urlPageRaw = search.get("page");
  const urlPage = urlPageRaw !== null ? parseInt(urlPageRaw, 10) : null;
  const hasUrlPage = urlPage !== null && !Number.isNaN(urlPage) && urlPage >= 1;
  const willInjectTocPage = TOC_ALLOWED_SLUGS.has(slug);
  const initialCurrentPage = hasUrlPage
    ? (willInjectTocPage ? urlPage! + 1 : urlPage!)
    : 1;

  // Reading position + drawer chat are scoped to this work and persisted
  // across visits so the devotee can leave and come back where they were.
  // When a `?page=` deep-link is present it is the source of truth: seed
  // currentPage from it AND skip localStorage hydration so the persisted page
  // can't clobber it (see usePersistentState `skipHydration`). Without a URL
  // page, behave normally — restore the reader's last position.
  const [currentPage, setCurrentPage] = usePersistentState<number>(
    `gd:read:${slug}:page`,
    initialCurrentPage,
    { skipHydration: hasUrlPage },
  );
  const [messages, setMessages] = usePersistentState<ChatTurn[]>(
    // v3: RFC-023 changed the drawer answer shape to `{format:"reading-qa",
    // text, passageLinks}`. Bumping v2→v3 discards the old QA-shape entries
    // that would render as an empty ReadingQaAnswer (their `text` is
    // undefined). Older restores just start with an empty conversation —
    // acceptable for a UI cache.
    `gd:read:${slug}:chat:v3`,
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
  // Contributor name for corrections — required, and remembered on-device so a
  // repeat contributor types it once (no login). Feeds the RFC-004 flag queue.
  const [correctionName, setCorrectionName] = usePersistentState<string>(
    "gd:correction:name",
    "",
  );
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

  // Table of contents (RFC-018) — fetched once per (slug, contentLang), NOT
  // per page turn. Cached in state so both the drawer and the inline page-1
  // TOC render off the same data. Fetch failures fall through silently — an
  // empty / missing TOC hides the affordance entirely so we never render a
  // dead button.
  const [toc, setToc] = useState<TocData | null>(null);
  const [tocDrawerOpen, setTocDrawerOpen] = useState(false);
  // `tocResolved` flips true as soon as the /api/read-toc fetch either
  // succeeds OR fails, so the body-page fetch below can wait to decide
  // whether page 1 is a TOC-only view or a real body page. Without this
  // gate the reader briefly fetches chapter-1 body content on cold mount
  // before the TOC arrives, which then has to be re-fetched a beat later
  // as the pagination shift kicks in — the user sees a flash of wrong
  // content.
  const [tocResolved, setTocResolved] = useState(false);

  // Derived: does this work publish a TOC page? When true, displayed
  // page 1 is the TOC and the body pages shift by +1 in the numbering
  // the reader sees. The backend never knows about this shift — the
  // shift is applied when we call /api/read (subtract 1) and when we
  // render chapter-click targets from the TOC (add 1).
  //
  // Feature-gated: the TOC only renders for works whose canonical text.md
  // has been curated with meticulous chapter markers. Every other work's
  // extraction currently loses Shri Gurudev's chapter headings, so the
  // TOC would misrepresent the book. Expand this allow-list as each work
  // is reviewed. Note: the set itself lives at module scope (see top of
  // file) so both initial-state expressions and render-time gates use the
  // same source of truth.
  const hasTocPage = !!(
    toc &&
    toc.sections.length > 0 &&
    TOC_ALLOWED_SLUGS.has(slug)
  );

  // When a ?page= URL param is present, override the persisted page once on
  // mount. We use a ref so this override fires exactly once per navigation to
  // this URL (not on every re-render). The clamping to [1, totalPages] is
  // deferred until totalPages is available via the fetch; if the page is valid
  // before we have totalPages, we still apply it immediately and re-clamp below
  // once the fetch completes.
  // Track the last ?page= value we applied. We must re-apply whenever the URL's
  // page changes — not just once on mount — because clicking "Read in full" for a
  // book that's ALREADY open is a same-route navigation (Next.js updates the query
  // without remounting), so a once-on-mount guard would leave the reader on its
  // saved page. Prev/Next/slider change currentPage WITHOUT changing ?page, so
  // they never re-trigger this and don't get clobbered.
  const lastAppliedUrlPage = useRef<number | null>(null);
  const correctionCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (hasUrlPage && urlPage !== lastAppliedUrlPage.current) {
      lastAppliedUrlPage.current = urlPage;
      // Apply immediately (pre-clamp). Same URL→displayed translation as
      // the initial-state expression above — URL page is BACKEND page,
      // displayed page = backend + 1 for TOC-allow-listed slugs.
      const displayed = willInjectTocPage ? urlPage! + 1 : urlPage!;
      setCurrentPage(displayed);
    }
  }, [hasUrlPage, urlPage]);

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
    // Wait until we know whether this work has a TOC — otherwise the very
    // first fetch would go out at currentPage=1 (backend page 1 = chapter 1
    // content) and then get thrown away as soon as `hasTocPage` flips true.
    if (!tocResolved) return;
    // Displayed page 1 is the TOC-only view when this work has a TOC.
    // Don't fetch anything — the paragraph area renders the TOC and the
    // reader never sees chapter-1 body until they page forward.
    if (hasTocPage && currentPage === 1) {
      setLoading(false);
      setFetchError(null);
      return;
    }
    setLoading(true);
    setFetchError(null);
    // Backend still uses body-page numbering. When a TOC page exists the
    // displayed page is +1 vs. the backend page, so subtract before the
    // request. The API + proxies are untouched by this shift.
    const backendPage = hasTocPage ? currentPage - 1 : currentPage;
    const qs = new URLSearchParams({ slug, page: String(backendPage) });
    if (contentLang) qs.set("lang", contentLang);
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
          // Clamp currentPage to [1, displayedTotal]. Needed when the ?page=
          // URL param was out of the valid range for this work. The reader's
          // displayed total includes the TOC page, so add 1 when hasTocPage.
          const displayedTotal = data.totalPages + (hasTocPage ? 1 : 0);
          setCurrentPage((p) => Math.max(1, Math.min(displayedTotal, p)));
          // Record reading progress in displayed-page numbering so the
          // "Continue reading" shelf matches what the reader sees on the
          // slider and Prev/Next.
          upsertProgress({
            slug,
            workTitle: data.workTitle,
            page: currentPage,
            totalPages: displayedTotal,
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
  }, [slug, contentLang, currentPage, hasTocPage, tocResolved]);

  // TOC fetch — separate from the paginated body fetch above so page turns
  // don't re-fetch the (often-large) TOC. Runs once per (slug, contentLang).
  // Silent-fail: if the endpoint 404s or the response is malformed, `toc`
  // stays null and every TOC surface (button, drawer, inline block) hides.
  useEffect(() => {
    let cancelled = false;
    // Reset both toc + tocResolved when the slug/lang change so the body
    // fetch waits for the new work's TOC before deciding page 1 shape.
    setTocResolved(false);
    setToc(null);
    const qs = new URLSearchParams({ slug });
    if (contentLang) qs.set("lang", contentLang);
    fetch(`/api/read-toc?${qs.toString()}`)
      .then((res) => {
        if (!res.ok) throw new Error(`toc ${res.status}`);
        return res.json() as Promise<TocData>;
      })
      .then((data) => {
        if (!cancelled) setToc(data);
      })
      .catch(() => {
        if (!cancelled) setToc(null);
      })
      .finally(() => {
        if (!cancelled) setTocResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, contentLang]);

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
        // RFC-023: the drawer sends "reading-qa" so the backend routes to
        // SYSTEM_PROMPT_READING_QA + emit_reading_qa_response. The response
        // is discriminated by `format`, not `kind`.
        mode: "reading-qa",
        question: q,
        lang: uiLang,
        work: slug,
      });
      // Narrow via the RFC-023 discriminator. Backend also produces the
      // shape when the LLM misfires (format field is always set by pydantic
      // literal), so if we don't see it something upstream is very wrong.
      if (!("format" in resp) || resp.format !== "reading-qa") {
        throw new AskError("Unexpected response shape", 500);
      }
      const turn: ChatTurn = {
        question: q,
        answer: {
          format: "reading-qa",
          question: resp.question,
          text: resp.text,
          passageLinks: resp.passageLinks,
        },
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
    const name = correctionName.trim();
    if (!edited || edited === original) {
      closeCorrectionEditor();
      return;
    }
    if (!name) return; // name is required; Submit is also disabled without it
    setCorrectionStatus("sending");
    const req: CorrectionRequest = {
      kind: "correction",
      slug,
      page: currentPage,
      paragraph: n,
      original,
      corrected: edited,
      lang: contentLang,
      question: "",
      mode: "reading",
      name,
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

  // Body pages the backend knows about. `displayedTotal` adds the TOC
  // page when this work has one, giving the numbering the reader sees on
  // the slider, "Page X of Y", and Prev/Next bounds.
  const backendTotal = pageData?.totalPages ?? 1;
  const displayedTotal = backendTotal + (hasTocPage ? 1 : 0);

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
    <TocStyles />
    <main className="mx-auto flex min-h-screen max-w-[760px] flex-col px-5 pt-5 pb-24 sm:pb-6">
      <header
        className="mb-5 pb-3"
        style={{ borderBottom: "1px solid var(--border-soft)" }}
      >
        {/* Back links — top-left to match chat + landing surfaces.
            "Back to start" ALWAYS goes to the reading landing. When an origin
            URL is present via ?from= (e.g. a Q&A session or another book), a
            second link back to that exact origin is shown beside it. The two
            links must have distinct destinations — "start" is the landing, the
            origin link is the answer/pravachan the reader came from. Font
            controls (A− / A+) sit on the right of the same row and share the
            app-wide scale via <FontScaleControl>. */}
        <div className="mb-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link
              href={`/?mode=reading&lang=${uiLang}`}
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
                {returnMode === "qa"
                  ? lbl.backToAnswer
                  : returnMode === "pravachan"
                    ? lbl.backToPravachan
                    : lbl.backToPrevious}
              </Link>
            ) : null}
          </div>
          <FontScaleControl variant="inline" />
        </div>
        {/* Work title block. Canonical work title + author stay in their
            published language; chapter label is descriptive metadata so we
            translate it where we have an MR equivalent. */}
        <div>
          <div
            className="text-[20px] font-semibold leading-tight"
            style={{ color: "var(--text-primary)" }}
          >
            {pageData?.workTitle ?? toc?.workTitle ?? slug.replace(/-/g, " ")}
          </div>
          <div
            className="text-[13.5px]"
            style={{ color: "var(--text-secondary)" }}
          >
            {pageData
              ? hasTocPage && currentPage === 1
                ? `${pageData.author} · ${lbl.tocDrawerTitle}`
                : pageData.chapter &&
                    // Reject obvious noise (year fragments, |I| citation
                    // artifacts) but no length cap — real book chapter
                    // titles are often long ("Chapter I. Introduction: The
                    // Development of Indian Mysticism…") and dropping them
                    // leaves the reader with no context on continuation
                    // pages. Long subtitles wrap gracefully.
                    !/(19|20)\d{2}/.test(pageData.chapter) &&
                    !/[|I]\s+\S+\s+[|I]\s/.test(pageData.chapter)
                  ? `${pageData.author} · ${pageData.chapter}`
                  : pageData.author
              : toc?.author ?? ""}
          </div>
        </div>
        {/* Table-of-contents affordance — only rendered when the fetched TOC
            has real sections AND the work is in the curated allow-list
            (see TOC_ALLOWED_SLUGS). Books whose extraction lost their chapter
            markers are excluded until they are reviewed. */}
        {hasTocPage ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setTocDrawerOpen(true)}
              className={`rounded-[4px] px-3 py-1.5 text-[13px] ${
                isMr ? "font-deva" : ""
              }`}
              style={{
                background: "var(--bg-surface)",
                color: "var(--accent-maroon)",
                border: "1px solid var(--accent-maroon)",
                cursor: "pointer",
              }}
            >
              {lbl.tocButton}
            </button>
          </div>
        ) : null}
      </header>

      {/* Progress slider — draggable/clickable range input styled as the
          parchment progress bar. Scrubbing updates the live readout only;
          setCurrentPage (and the fetch) fire on pointer/keyboard release so
          we avoid a fetch-storm while the user drags. */}
      <div className="mb-6">
        <input
          type="range"
          min={1}
          max={displayedTotal}
          step={1}
          value={sliderValue}
          onChange={onSliderChange}
          onMouseUp={commitSliderFromEvent}
          onTouchEnd={commitSliderFromEvent}
          onKeyUp={commitSliderFromEvent}
          aria-label={lbl.pageXofY(sliderValue, displayedTotal)}
          aria-valuemin={1}
          aria-valuemax={displayedTotal}
          aria-valuenow={sliderValue}
          className="gd-page-slider"
          style={
            {
              "--slider-pct": `${Math.min(100, Math.round(((sliderValue - 1) / Math.max(1, displayedTotal - 1)) * 100))}%`,
            } as CSSProperties
          }
        />
        <div
          className={`mt-1.5 text-[12px] text-right ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--text-secondary)" }}
        >
          {lbl.pageXofY(sliderValue, displayedTotal)}
        </div>
      </div>

      {/* Reading column, capped at ~70ch per ADR-006. */}
      <article className="mx-auto w-full max-w-reading flex-1">
        {hasTocPage && currentPage === 1 && toc ? (
          /* Displayed page 1 = the TOC-only view (no body fetch happens). */
          <section className="reading-toc-inline">
            <h2
              className={`mb-4 text-[16px] font-semibold ${
                isMr ? "font-deva" : ""
              }`}
              style={{
                color: "var(--accent-maroon)",
                fontFamily: "var(--font-serif)",
                letterSpacing: "0.02em",
              }}
            >
              {lbl.tocDrawerTitle}
            </h2>
            <TocBody
              toc={toc}
              hasTocPage={hasTocPage}
              isMr={isMr}
              onChapterClick={(displayedPage) => setCurrentPage(displayedPage)}
            />
          </section>
        ) : loading ? (
          <p className="text-[15px] italic" style={{ color: "var(--text-tertiary)" }}>
            Loading…
          </p>
        ) : fetchError ? (
          <p className="text-[15px]" style={{ color: "var(--accent-maroon)" }}>
            {fetchError}
          </p>
        ) : (
          <>
            {/* Ornamental chapter opener — shown ONLY on the first page of
                a chapter (like a printed book's chapter-title page). The
                subtitle in the header carries the chapter name as a running
                head on continuation pages, so this decoration doesn't need
                to repeat on every page. */}
            {pageData?.chapter && pageData?.chapterStart ? (
              <div
                className="mb-8 mt-2"
                style={{ color: "var(--text-secondary)" }}
              >
                <div className="flex items-center gap-4">
                  <div
                    className="flex-1"
                    style={{ borderTop: "1px dotted var(--border-stronger)" }}
                    aria-hidden
                  />
                  <span
                    aria-hidden
                    style={{ color: "var(--accent-maroon)", fontSize: "22px", opacity: 0.9 }}
                  >
                    ❖
                  </span>
                  <div
                    className="flex-1"
                    style={{ borderTop: "1px dotted var(--border-stronger)" }}
                    aria-hidden
                  />
                </div>
                {(() => {
                  // Split "Chapter I. Introduction: The Development..." into
                  // `Chapter I` (headline) + descriptive subtitle. Matches
                  // Ranade's own printed layout (CHAPTER I. on its own line,
                  // descriptive title beneath in serif). Anything that doesn't
                  // parse falls back to the whole string as headline.
                  const ch = pageData.chapter ?? "";
                  const m = ch.match(/^(Chapter\s+[IVXL]+|Part\s+[IVXL]+)\.?\s*(.*)$/i);
                  const head = (m ? m[1] : ch).trim();
                  const rest = (m ? m[2] : "").trim();
                  return (
                    <>
                      <div
                        className={`mt-4 text-center uppercase ${isMr ? "font-deva" : ""}`}
                        style={{
                          color: "var(--accent-maroon)",
                          fontSize: "calc(20px * var(--app-font-scale, 1))",
                          letterSpacing: "0.16em",
                          fontWeight: 700,
                          lineHeight: 1.3,
                        }}
                      >
                        {head}
                      </div>
                      {rest ? (
                        <div
                          className={`mt-2 text-center ${isMr ? "font-deva" : ""}`}
                          style={{
                            color: "var(--accent-maroon)",
                            fontSize: "calc(16px * var(--app-font-scale, 1))",
                            fontFamily: "var(--font-serif)",
                            fontStyle: "normal",
                            lineHeight: 1.4,
                            fontWeight: 500,
                            maxWidth: "36em",
                            marginLeft: "auto",
                            marginRight: "auto",
                          }}
                        >
                          {rest}
                        </div>
                      ) : null}
                    </>
                  );
                })()}
              </div>
            ) : null}
            {/* Pre-process paragraphs to merge Surya-split sentences (prev
                ends without terminator + current starts lowercase). Purely
                presentational — canonical text is untouched. */}
            {mergeSentenceContinuations(pageData?.paragraphs ?? []).map((para, idx) => (
          <div
            key={para.n}
            className="mb-0"
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
                    <input
                      type="text"
                      value={correctionName}
                      onChange={(e) => setCorrectionName(e.target.value)}
                      placeholder={lbl.yourNamePlaceholder}
                      disabled={correctionStatus === "sending" || correctionStatus === "sent"}
                      className={`mt-2 block w-full rounded-[6px] px-2.5 py-1.5 text-[14px] ${isMr ? "font-deva" : ""}`}
                      style={{
                        fontFamily: "var(--font-serif)",
                        color: "var(--text-primary)",
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
                            disabled={correctionStatus === "sending" || !correctionName.trim()}
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
                ) : para.is_subheading ? (
                  /* `####+` sub-section marker from the source markdown (e.g.
                      Ranade's numbered TOC items in MiM, or the preface's
                      Roman-numeral dividers I / II / III / IV). Short
                      roman-only marks render as a centered small-caps
                      divider; titled ones render as bold serif in title
                      case (matching the printed book). */
                  (() => {
                    const isRomanOnly = /^\s*[IVXL]+\.?\s*$/.test(para.body);
                    if (isRomanOnly) {
                      return (
                        <div className="my-8 flex items-center justify-center gap-4">
                          <div
                            style={{
                              width: "3.5em",
                              borderTop: "1px solid var(--border-stronger)",
                              opacity: 0.5,
                            }}
                            aria-hidden
                          />
                          <span
                            className={isMr ? "font-deva" : ""}
                            style={{
                              color: "var(--accent-maroon)",
                              fontFamily: "var(--font-serif)",
                              fontSize: "calc(18px * var(--app-font-scale, 1))",
                              fontWeight: 700,
                              letterSpacing: "0.18em",
                            }}
                          >
                            {para.body.replace(/\.$/, "")}
                          </span>
                          <div
                            style={{
                              width: "3.5em",
                              borderTop: "1px solid var(--border-stronger)",
                              opacity: 0.5,
                            }}
                            aria-hidden
                          />
                        </div>
                      );
                    }
                    return (
                      <h4
                        className={`mt-7 mb-3 ${isMr ? "font-deva" : ""}`}
                        style={{
                          color: "var(--accent-maroon)",
                          fontFamily: "var(--font-serif)",
                          fontSize: "calc(17px * var(--app-font-scale, 1))",
                          fontWeight: 700,
                          lineHeight: 1.35,
                        }}
                      >
                        {para.body}
                      </h4>
                    );
                  })()
                ) : (() => {
                  /* Normal paragraph display. Font size scales via the
                      --app-font-scale CSS var set on <html> by FontScaleControl,
                      shared with chat/pravachan body text. Verse detection
                      logic lives in `lib/verse-detection.ts` (unit-tested).
                      A paragraph may contain embedded verse runs (e.g. a
                      Plotinus quote in Greek nested inside English commentary),
                      so we split into an ordered [prose/verse/prose/…] list
                      and render each block appropriately. */
                  const rendered = para.body.replace(/\f/g, "").replace(/^\s*[*•]\s+/, "");
                  // Verse detection uses the RESOLVED content language from
                  // the backend response (falls back correctly when the URL
                  // requests `en` on a Marathi-only work). Marathi/Hindi
                  // body prose must not trip the embedded-verse detector.
                  const resolvedLang = pageData?.language ?? contentLang;
                  const blocks = splitVerseBlocks(rendered, {
                    isMarathi: resolvedLang === "mr" || resolvedLang === "hi",
                  });
                  const cornerBase: React.CSSProperties = {
                    position: "absolute",
                    width: "12px",
                    height: "12px",
                    pointerEvents: "none",
                  };
                  const bracketColor = "var(--accent-maroon)";
                  return (
                    <>
                      {blocks.map((blk, i) => {
                        if (blk.type === "verse") {
                          /* Split off a trailing citation (e.g. `॥ XIII.
                              12-13.` or `Iśa. Up. 2.`) so it renders on its
                              own line below, smaller + muted. */
                          const { verse: verseText, citation } = splitVerseCitation(blk.text);
                          return (
                            <div key={`v-${i}`} className="my-10 mx-auto" style={{ maxWidth: "30em", textAlign: "center" }}>
                              <span
                                aria-hidden
                                style={{
                                  display: "inline-block",
                                  color: "var(--accent-maroon)",
                                  fontSize: "18px",
                                  lineHeight: 1,
                                  opacity: 0.72,
                                  marginBottom: "14px",
                                }}
                              >
                                ❈
                              </span>
                              <div
                                className="font-deva"
                                style={{
                                  position: "relative",
                                  color: "var(--text-primary)",
                                  fontFamily: 'var(--font-deva, "Sanskrit 2003", "Noto Sans Devanagari", "Kohinoor Devanagari", "Mangal", serif)',
                                  fontSize: "calc(16.5px * var(--app-font-scale, 1))",
                                  lineHeight: 2.0,
                                  padding: "18px 22px",
                                }}
                                aria-label="verse"
                              >
                                <span aria-hidden style={{ ...cornerBase, top: 0, left: 0, borderTop: `1px solid ${bracketColor}`, borderLeft: `1px solid ${bracketColor}` }} />
                                <span aria-hidden style={{ ...cornerBase, top: 0, right: 0, borderTop: `1px solid ${bracketColor}`, borderRight: `1px solid ${bracketColor}` }} />
                                <span aria-hidden style={{ ...cornerBase, bottom: 0, left: 0, borderBottom: `1px solid ${bracketColor}`, borderLeft: `1px solid ${bracketColor}` }} />
                                <span aria-hidden style={{ ...cornerBase, bottom: 0, right: 0, borderBottom: `1px solid ${bracketColor}`, borderRight: `1px solid ${bracketColor}` }} />
                                <div>{verseText}</div>
                                {citation ? (
                                  <div
                                    style={{
                                      marginTop: "10px",
                                      fontFamily: "var(--font-serif)",
                                      fontSize: "calc(13.5px * var(--app-font-scale, 1))",
                                      color: "var(--text-secondary, #6E5B3E)",
                                      letterSpacing: "0.02em",
                                    }}
                                  >
                                    {citation}
                                  </div>
                                ) : null}
                              </div>
                            </div>
                          );
                        }
                        return (
                          <p
                            key={`p-${i}`}
                            className={`gd-read-p ${
                              i === 0 && idx === 0 && pageData?.chapterStart ? "gd-read-p--flush" : ""
                            }`}
                            style={{
                              color: "var(--text-primary)",
                              lineHeight: 1.7,
                              fontSize: "calc(17.5px * var(--app-font-scale, 1))",
                            }}
                          >
                            {blk.text}
                          </p>
                        );
                      })}
                    </>
                  );
                })()}
                {/* Correction affordance — mounted only while this paragraph is
                    hovered/focused, so it reserves no space otherwise and
                    paragraphs stay flush (book look). */}
                {activeCorrectionN !== para.n && hoveredN === para.n && (
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
                    }}
                  >
                    ✏ {lbl.suggestCorrection}
                  </button>
                )}
            </div>
          </div>
        ))}
          </>
        )}
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
          onClick={() => setCurrentPage((p) => Math.min(displayedTotal, p + 1))}
          disabled={currentPage >= displayedTotal}
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

    </main>
    {/* Floating "Ask" affordance — viewport-fixed (position: fixed) so it
        stays reachable no matter where the reader has scrolled. Hidden when
        the drawer is open so the two affordances don't visually stack.
        Previously docked at the article foot: reader had to scroll a
        long-form book chapter to reach it (2026-07-21 UX report). */}
    {!chatOpen ? (
      <button
        type="button"
        onClick={() => setChatOpen(true)}
        aria-label={
          messages.length === 0
            ? lbl.askAboutThisWork
            : lbl.continueChat(messages.length)
        }
        className={`fixed bottom-6 right-6 z-20 inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-[14px] font-semibold transition-transform hover:scale-105 ${
          isMr ? "font-deva" : ""
        }`}
        style={{
          background: "#6B1F1F",
          color: "#F4EAC9",
          border: "1px solid #4F1414",
          boxShadow: "0 4px 14px rgba(60, 30, 10, 0.28)",
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
    ) : null}
    {/* Right-side answer drawer — slides in from the right so it doesn't
        disturb the reading column. Fixed position; height uses dynamic
        viewport units (100dvh) so the drawer shrinks when the mobile
        keyboard opens instead of leaving the composer trapped below the
        keyboard fold. Full-width on phones (composer would be cropped at
        400px on a 375px viewport); 400px on ≥640px. */}
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="Chat about this work"
      className="fixed right-0 top-0 z-30 flex h-[100dvh] w-full flex-col transition-transform sm:w-[400px]"
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

      {/* Conversation — scrollable. Empty state when nothing asked yet.
          `overscroll-contain` blocks scroll-chaining to the body (which,
          combined with the drawer's `position: fixed`, would otherwise
          leave the underlying reader stuck after keyboard dismissal on
          iOS/Android). */}
      <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4">
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
              {/* RFC-023 answer render. Discriminator: `format === "reading-qa"`
                  → new ReadingQaAnswer (plain synthesis + optional Sources
                  footer). Otherwise fall back to the QA-shape render (still
                  used to display older cached entries that predate the
                  format migration). */}
              {(() => {
                const ans = m.answer;
                if ("format" in ans && ans.format === "reading-qa") {
                  return (
                    <ReadingQaAnswer
                      text={ans.text}
                      passageLinks={ans.passageLinks}
                      currentSlug={slug}
                      lang={uiLang}
                      onNav={() => setChatOpen(false)}
                    />
                  );
                }
                // QA answer: framing paragraph(s), citations (QuoteBlock +
                // whyChosen rationale), optional synthesis. Only reached
                // for legacy cached entries — new drawer asks are always
                // reading-qa shape (RFC-023).
                const qa = ans as QAAnswer;
                return (
                  <>
                    {qa.framing ? (
                      <p
                        className={`mb-3 text-[14px] ${isMr ? "font-deva" : ""}`}
                        style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
                      >
                        {renderInlineMd(qa.framing)}
                      </p>
                    ) : null}
                    {(qa.citations ?? []).filter((c) => c?.quote?.body).map((c, ci) => (
                      <div
                        key={ci}
                        id={c.quote?.passage ? `cite-${c.quote.passage}` : undefined}
                        className="scroll-mt-4"
                      >
                        {c.whyChosen ? (
                          <p
                            className={`mb-1 text-[14px] ${isMr ? "font-deva" : ""}`}
                            style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
                          >
                            {renderInlineMd(c.whyChosen)}
                          </p>
                        ) : null}
                        <QuoteBlock quote={c.quote} lang={uiLang} variant="inline" />
                      </div>
                    ))}
                    {qa.synthesis ? (
                      <div
                        className={`mt-2 text-[14px] synthesis-body ${isMr ? "font-deva" : ""}`}
                        style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
                      >
                        {renderBlockMd(qa.synthesis)}
                      </div>
                    ) : null}
                  </>
                );
              })()}
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
    {/* Table-of-contents drawer (RFC-018) — slides in from the LEFT so it
        doesn't collide with the right-side chat drawer above. Only mounts
        when the fetched TOC has real sections AND the work is in the
        curated allow-list (see TOC_ALLOWED_SLUGS). Click-outside-to-close:
        the semi-transparent backdrop is a sibling element behind the drawer
        that dismisses on click. */}
    {hasTocPage ? (
      <>
        {/* Backdrop — click anywhere off the drawer to close. Only rendered
            (and only capturing pointer events) while the drawer is open, so
            it never blocks the reading column when the TOC is idle. */}
        {tocDrawerOpen ? (
          <div
            onClick={() => setTocDrawerOpen(false)}
            className="fixed inset-0 z-20"
            style={{
              background: "rgba(30, 20, 10, 0.25)",
              backdropFilter: "blur(2px)",
            }}
            aria-hidden
          />
        ) : null}
        <aside
          role="dialog"
          aria-modal="false"
          aria-label={lbl.tocDrawerTitle}
          className="fixed left-0 top-0 z-30 flex h-[100dvh] w-full flex-col transition-transform sm:w-[380px]"
          style={{
            transform: tocDrawerOpen ? "translateX(0)" : "translateX(-100%)",
            background: "var(--bg-surface)",
            borderRight: "1px solid var(--border-soft)",
            boxShadow: "6px 0 24px rgba(60, 30, 10, 0.12)",
            visibility: tocDrawerOpen ? "visible" : "hidden",
            pointerEvents: tocDrawerOpen ? "auto" : "none",
          }}
        >
          {/* Drawer header — title + close (×). */}
          <div
            className="flex items-center justify-between px-4 py-3"
            style={{ borderBottom: "1px solid var(--border-soft)" }}
          >
            <div>
              <h2
                className={`text-[15px] font-semibold leading-tight ${
                  isMr ? "font-deva" : ""
                }`}
                style={{
                  color: "#6B1F1F",
                  fontFamily: "var(--font-serif)",
                }}
              >
                {lbl.tocDrawerTitle}
              </h2>
              <p
                className="text-[12px] leading-tight"
                style={{ color: "var(--text-secondary)" }}
              >
                {toc.workTitle}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setTocDrawerOpen(false)}
              aria-label={lbl.closeToc}
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
          {/* Drawer body — scrollable list of sections + chapters. Clicking
              any chapter jumps the reader to that page and closes the drawer
              so we don't stay in the way of the destination page.
              `overscroll-contain` matches the chat drawer so the underlying
              reader can't get scroll-locked when this drawer overlays it. */}
          <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4">
            <TocBody
              toc={toc}
              hasTocPage={hasTocPage}
              isMr={isMr}
              onChapterClick={(displayedPage) => {
                setCurrentPage(displayedPage);
                setTocDrawerOpen(false);
              }}
            />
          </div>
        </aside>
      </>
    ) : null}
    </>
  );
}

// One-time inline stylesheet for the TOC — colocated here so the file
// is fully self-contained (per constraint: only page.tsx may change).
// Media query drops the type size + tightens spacing under 640px so a
// 47-chapter index is comfortable to skim on a phone.
function TocStyles() {
  return (
    <style>{`
      .gd-toc-root { --gd-toc-fs: 15px; }
      .gd-toc-root summary { list-style: none; }
      .gd-toc-root summary::-webkit-details-marker { display: none; }
      .gd-toc-section { padding: 0; margin: 0; }
      .gd-toc-section + .gd-toc-section { margin-top: 20px; }
      .gd-toc-summary {
        display: flex;
        align-items: baseline;
        gap: 0.5em;
        padding: 6px 0;
        font-size: 15px;
        font-weight: 600;
        color: var(--accent-maroon);
      }
      .gd-toc-summary--underline {
        border-bottom: 1px solid var(--border-soft);
      }
      .gd-toc-summary--smallcaps {
        text-transform: uppercase;
        letter-spacing: 0.08em;
      }
      .gd-toc-list {
        list-style: none;
        margin: 6px 0 0 0;
        padding: 0;
      }
      .gd-toc-li { margin: 0; padding: 0; }
      .gd-toc-row {
        display: flex;
        align-items: baseline;
        width: 100%;
        background: none;
        border: none;
        padding: 4px 0;
        cursor: pointer;
        font-family: var(--font-serif);
        font-size: 15px;
        text-align: left;
        color: inherit;
        overflow: hidden;
      }
      .gd-toc-title {
        color: var(--accent-maroon);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        flex-shrink: 1;
        min-width: 0;
      }
      .gd-toc-leader {
        flex: 1;
        border-bottom: 1px dotted var(--border-soft);
        margin: 0 0.5em 0.25em;
        min-width: 1em;
      }
      .gd-toc-page {
        color: var(--text-tertiary);
        flex-shrink: 0;
        font-variant-numeric: tabular-nums;
      }
      .gd-toc-ornament {
        text-align: center;
        color: var(--accent-maroon);
        letter-spacing: 0.4em;
        margin: 10px 0 12px;
        font-size: 13px;
        opacity: 0.85;
      }
      @media (max-width: 639px) {
        .gd-toc-summary { font-size: 14px; padding: 4px 0; }
        .gd-toc-row { font-size: 14px; padding: 2px 0; }
        .gd-toc-list { margin-top: 4px; }
        .gd-toc-section + .gd-toc-section { margin-top: 14px; }
        .gd-toc-ornament { margin: 6px 0 8px; }
      }
    `}</style>
  );
}

// TOC render body — shared between the inline page-1 view and the
// left-side drawer. Sections are `<details>` for native a11y + free
// keyboard handling; on mobile they seed closed so a 47-chapter index
// doesn't dump one giant scroll. Ornamented devotional style: dotted
// leaders between chapter title and page number, `❖` glyph dividing
// sections, small-caps section headings under a soft underline.
function TocBody({
  toc,
  onChapterClick,
  hasTocPage,
  isMr,
}: {
  toc: TocData;
  onChapterClick: (displayedPage: number) => void;
  hasTocPage: boolean;
  isMr: boolean;
}) {
  return (
    <div className="gd-toc-root">
      {toc.sections.map((section, si) => {
        const headingClasses = [
          "gd-toc-summary",
          "gd-toc-summary--underline",
          "gd-toc-summary--smallcaps",
          isMr ? "font-deva" : "",
        ]
          .filter(Boolean)
          .join(" ");
        // A section with 0 chapters but its own `page` is a leaf — e.g.
        // MiM's standalone `## Chapter I. Introduction: ...` which is a
        // peer of the Parts but has no `###` children. Render as a
        // clickable jump row instead of an empty header (which would
        // strand the reader with no way to navigate to it).
        const isLeafSection =
          section.chapters.length === 0 &&
          section.title != null &&
          typeof section.page === "number";
        return (
          <div key={si} className="gd-toc-section">
            {si > 0 ? (
              <div className="gd-toc-ornament" aria-hidden>
                ❖
              </div>
            ) : null}
            {isLeafSection ? (
              (() => {
                const displayedPage =
                  (section.page as number) + (hasTocPage ? 1 : 0);
                return (
                  <button
                    type="button"
                    onClick={() => onChapterClick(displayedPage)}
                    className="gd-toc-row gd-toc-row--leaf"
                  >
                    <span
                      className={`gd-toc-title ${isMr ? "font-deva" : ""}`}
                    >
                      {section.title}
                    </span>
                    <span className="gd-toc-leader" aria-hidden />
                    <span className="gd-toc-page">{displayedPage}</span>
                  </button>
                );
              })()
            ) : (
              <>
                <div className={headingClasses}>
                  <span>{section.title ?? "Chapters"}</span>
                </div>
                <ul className="gd-toc-list">
                  {section.chapters.map((ch, ci) => {
                    const displayedPage = ch.page + (hasTocPage ? 1 : 0);
                    return (
                      <li key={ci} className="gd-toc-li">
                        <button
                          type="button"
                          onClick={() => onChapterClick(displayedPage)}
                          className="gd-toc-row"
                        >
                          <span
                            className={`gd-toc-title ${
                              isMr ? "font-deva" : ""
                            }`}
                          >
                            {ch.title}
                          </span>
                          <span className="gd-toc-leader" aria-hidden />
                          <span className="gd-toc-page">{displayedPage}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
