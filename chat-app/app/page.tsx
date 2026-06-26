"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import MenuDrawer from "../components/MenuDrawer";
import { type Lang } from "../components/ModeTabs";
import {
  DEFAULT_READING_SLUG,
  SUGGESTIONS,
  type ModeId,
  type Suggestion,
} from "../data/mock-conversations";
import { usePersistentState } from "../hooks/usePersistentState";
import {
  loadProgress,
  removeProgress,
  type ProgressRecord,
} from "../lib/readingProgress";

// Shape returned by /api/works (proxied from the Python backend).
type ReadableWork = {
  slug: string;
  title: string;
  author: string;
  languages: string[];
};

// Single-language labels. English is the default per user direction
// (2026-06-14) — Marathi is reachable via the EN/मराठी toggle next to the
// mode tabs.
const TITLE = {
  en: "Gurudev Sangrah",
  mr: "गुरुदेव संग्रह",
} as const;

const TAGLINE = {
  en: "Philosopher-saint of the Nimbal sampradaya · 1886–1957",
  mr: "निंबाळ संप्रदायाचे संत आणि तत्त्वज्ञ · १८८६–१९५७",
} as const;

const PLACEHOLDERS: Record<Lang, Record<ModeId, string>> = {
  en: {
    qa: "Ask anything...",
    pravachan: "Suggest a theme for a pravachan...",
    reading: "Ask about the passage...",
  },
  mr: {
    qa: "काहीही विचारा...",
    pravachan: "एक विषय सुचवा...",
    reading: "एक प्रश्न विचारा...",
  },
};

const TRY_PREFIX = { en: "Try:", mr: "उदा.:" } as const;

// Mode-aware Send labels — each mode performs a different action, so
// the button text changes to match (Round-2 critic: make the tabs work).
const SEND_LABELS: Record<ModeId, { en: string; mr: string }> = {
  qa: { en: "Ask", mr: "विचारा" },
  pravachan: { en: "Gather", mr: "गोळा करा" },
  reading: { en: "Open", mr: "उघडा" },
};

// One-line helper text beneath the composer explaining what the active
// mode actually does, in plain language for the demo audience.
const MODE_HELPER: Record<ModeId, { en: string; mr: string }> = {
  qa: {
    en: "Get verbatim passages from the literature that answer your question.",
    mr: "तुमच्या प्रश्नाला साहित्यातील उतार्‍यांद्वारे उत्तर मिळवा.",
  },
  pravachan: {
    en: "Gather examples and quotes to compose a discourse on your theme.",
    mr: "प्रवचनासाठी उद्धरणे आणि उदाहरणे गोळा करा.",
  },
  reading: {
    en: "Open a book or chapter and read the source text directly.",
    mr: "थेट ग्रंथ किंवा अध्याय उघडून वाचा.",
  },
};

// useSearchParams requires a Suspense boundary in Next 15.
export default function LandingPageRoute() {
  return (
    <Suspense fallback={null}>
      <LandingPage />
    </Suspense>
  );
}

function LandingPage() {
  const router = useRouter();
  const search = useSearchParams();
  const langFromUrl = search.get("lang") as Lang | null;
  // Honor an explicit ?mode= in the URL (e.g. returning from the reader to the
  // Reading landing); fall back to Q&A otherwise.
  const modeParam = search.get("mode");
  const initialMode: ModeId =
    modeParam === "reading" || modeParam === "pravachan" ? modeParam : "qa";
  const [mode, setMode] = useState<ModeId>(initialMode);
  // Lang is persisted across tabs/visits via localStorage. URL `?lang=`
  // wins when present (e.g. someone shares a Marathi link); otherwise we
  // fall back to whatever the devotee last selected.
  const [lang, setLang] = usePersistentState<Lang>("gd:lang", "en");
  const [draft, setDraft] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);

  // Real readable works fetched from the backend. Used to replace the
  // hardcoded Reading chips with works that actually have a text.md.
  // `null` means "not yet fetched / still loading"; `[]` means "fetched but
  // no readable works" (fallback to nothing shown).
  const [readableWorks, setReadableWorks] = useState<ReadableWork[] | null>(null);

  // Fetch the readable works list once on mount so the Reading chips
  // advertise only works with real content. We do not re-fetch on mode
  // change because the list is corpus-wide and doesn't change during a session.
  useEffect(() => {
    fetch("/api/works")
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { works?: ReadableWork[] } | null) => {
        if (data && Array.isArray(data.works)) {
          setReadableWorks(data.works);
        }
      })
      .catch(() => {
        // Backend unreachable; leave readableWorks null so we fall back to
        // not showing any Reading chips rather than showing broken ones.
      });
  }, []);

  // URL takes priority when present.
  useEffect(() => {
    if (langFromUrl === "en" || langFromUrl === "mr") {
      setLang(langFromUrl);
    }
  }, [langFromUrl, setLang]);

  // Clear the draft whenever mode or language changes — the suggestions
  // beneath also refresh, so a stale auto-filled question would no longer
  // match the surrounding context (user feedback 2026-06-14).
  useEffect(() => {
    setDraft("");
  }, [mode, lang]);

  // Build the suggestion chips for the current mode and language.
  // For Reading mode, we use the real works list from the backend; for
  // Q&A and Pravachan we keep the hardcoded suggestions unchanged.
  function getSuggestions(): Suggestion[] {
    if (mode !== "reading") {
      return SUGGESTIONS[mode][lang];
    }
    if (readableWorks === null) {
      // Still loading; show nothing (no chips yet).
      return [];
    }
    // Show up to 6 works as chips. Each chip's text is the work title;
    // the slug goes to /read/<slug>. Language: prefer the current UI
    // language if available, otherwise the first available language.
    return readableWorks.slice(0, 6).map((w) => {
      const preferredLang = w.languages.includes(lang) ? lang : w.languages[0];
      return {
        text: w.title,
        slug: w.slug,
        lang: preferredLang,
      };
    });
  }

  function submit(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    if (mode === "reading") {
      // Match the draft against the active reading suggestions and use
      // the chip's own slug. If the user typed a custom question that
      // doesn't match any chip, fall back to DEFAULT_READING_SLUG[lang].
      const suggestions = getSuggestions();
      const chip = suggestions.find((s) => s.text === trimmed);
      const slug = chip?.slug ?? DEFAULT_READING_SLUG[lang];
      // Use the chip's preferred language if present; otherwise current lang.
      const chipLang = (chip as (Suggestion & { lang?: string }) | undefined)?.lang ?? lang;
      router.push(`/read/${slug}?lang=${chipLang}`);
      return;
    }
    // Propagate lang too so the chat surface renders in the same language
    // the devotee chose on landing.
    const params = new URLSearchParams({ mode, q: trimmed, lang });
    router.push(`/chat?${params.toString()}`);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit(draft);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(draft);
    }
  }

  return (
    <>
      <MenuDrawer
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        lang={lang}
        setLang={setLang}
        mode={mode}
        setMode={setMode}
      />

      <main className="relative mx-auto flex min-h-screen max-w-[1100px] flex-col px-6 pt-10 pb-10">
        {/* Top-left: menu button — explicit text label + filled background
            so first-time users (including 65-year-olds on Zoom) recognize
            it as a control, not decoration. */}
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label={lang === "mr" ? "मेनू उघडा" : "Open menu"}
          className="absolute left-6 top-6 z-10 inline-flex items-center gap-2 rounded-[6px] px-3 py-2"
          style={{
            background: "rgba(122, 46, 42, 0.10)",
            border: "1.5px solid #7A2E2A",
            cursor: "pointer",
            color: "#6B1F1F",
            fontFamily: "var(--font-serif)",
            boxShadow: "0 2px 6px rgba(60, 30, 10, 0.10)",
          }}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#6B1F1F"
            strokeWidth="2.4"
            strokeLinecap="round"
          >
            <line x1="4" y1="7" x2="20" y2="7" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="17" x2="20" y2="17" />
          </svg>
          <span
            className={`text-[14px] font-semibold ${
              lang === "mr" ? "font-deva" : ""
            }`}
          >
            {lang === "mr" ? "मेनू" : "Menu"}
          </span>
        </button>

        {/* Title block — single static medallion (no animation: stillness
            is more devotional than cross-fades on a contemplative page).
            Flourish removed — the medallion + serif type carry the
            register on their own. */}
        <header className="mb-6 text-center">
          <PortraitMedallion />
          <h1
            className={`text-[42px] font-semibold leading-tight ${
              lang === "mr" ? "font-deva" : ""
            }`}
            style={{ letterSpacing: "-0.005em" }}
          >
            {TITLE[lang]}
          </h1>
          <p
            className={`mt-2 text-[16px] ${
              lang === "mr" ? "font-deva" : ""
            }`}
            style={{ color: "var(--text-secondary)" }}
          >
            {TAGLINE[lang]}
          </p>
        </header>

        {/* Mode is now selected via the drawer; a small chip above the
            composer shows the active mode and opens the drawer on click. */}
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          className="mx-auto mt-2 inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[12.5px]"
          style={{
            background: "rgba(122, 46, 42, 0.08)",
            border: "1px solid rgba(122, 46, 42, 0.25)",
            color: "#7A1F2B",
            fontFamily: "var(--font-serif)",
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.02em",
          }}
        >
          <span className="text-[10.5px] font-bold tracking-[0.1em]" style={{ opacity: 0.7 }}>
            {lang === "mr" ? "रीत" : "MODE"}
          </span>
          <span>
            {mode === "qa"
              ? lang === "mr" ? "प्रश्नोत्तर" : "Q&A"
              : mode === "pravachan"
                ? lang === "mr" ? "प्रवचन" : "Pravachan"
                : lang === "mr" ? "वाचन" : "Reading"}
          </span>
          <span aria-hidden style={{ opacity: 0.6 }}>›</span>
        </button>

        {/* Action block — composer is the primary draw, lifted into the
            visual center with a stronger 2px maroon border. Suggestions
            move BELOW it as a 3-column row of examples ("after seeing the
            box, here's what you might ask"). */}
        <div className="mx-auto mt-8 w-full max-w-[820px]">
          <form
            onSubmit={onSubmit}
            className="flex items-end gap-3 rounded-[8px] p-3"
            style={{
              background: "var(--bg-surface)",
              border: "2px solid #6B1F1F",
              boxShadow: "0 4px 16px rgba(60, 30, 10, 0.10)",
            }}
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              rows={3}
              placeholder={PLACEHOLDERS[lang][mode]}
              aria-label={lang === "mr" ? "विचारा" : "Ask anything"}
              className="block flex-1 resize-none bg-transparent px-3 py-2 text-[17px] outline-none"
              style={{
                fontFamily: "var(--font-serif)",
                color: "var(--text-primary)",
                lineHeight: 1.55,
                minHeight: 88,
              }}
            />
            <button
              type="submit"
              className="rounded-[5px] px-5 py-2.5 text-[14px] font-semibold"
              style={{
                background: "#6B1F1F",
                color: "#F4EAC9",
                border: "1px solid #4F1414",
                boxShadow: "inset 0 1px 0 rgba(255, 220, 170, 0.2)",
              }}
            >
              {SEND_LABELS[mode][lang]}
            </button>
          </form>

          {/* Helper text — explains in plain language what the active mode
              will do. Bumped to instruction weight (14px, warm dark brown,
              constrained measure) per Round-3 critic. */}
          <p
            className={`mx-auto mt-3 max-w-[560px] text-center text-[14px] leading-snug ${
              lang === "mr" ? "font-deva" : ""
            }`}
            style={{ color: "#5A4632", opacity: 0.85 }}
          >
            {MODE_HELPER[mode][lang]}
          </p>

          {/* "Continue reading" shelf — only shown in Reading mode, above
              the begin-a-new-work suggestions. Reads from localStorage on
              mount; hides itself when the list is empty. */}
          {mode === "reading" && (
            <ContinueReadingShelf lang={lang} />
          )}

          {/* Suggestions as a 3-column row of example chips beneath the
              composer — "or try one of these" rather than a preamble. */}
          <div className="mt-5">
            <p
              className="mb-2 text-center text-[13.5px]"
              style={{ color: "var(--text-tertiary)" }}
            >
              {TRY_PREFIX[lang]}
            </p>
            <ul className="grid grid-cols-1 gap-2 md:grid-cols-3">
              {getSuggestions().map(({ text }) => {
                const isDeva = /[ऀ-ॿ]/.test(text);
                return (
                  <li key={text}>
                    <button
                      type="button"
                      onClick={() => setDraft(text)}
                      className={`group flex w-full items-baseline gap-2 rounded-[6px] px-3 py-2.5 text-left text-[14px] leading-snug transition-all ${
                        isDeva ? "font-deva" : ""
                      }`}
                      style={{
                        color: "#5A2520",
                        background: "rgba(244, 234, 201, 0.5)",
                        border: "1px solid rgba(122, 46, 42, 0.22)",
                        cursor: "pointer",
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background =
                          "rgba(244, 234, 201, 0.85)";
                        e.currentTarget.style.borderColor =
                          "rgba(122, 46, 42, 0.4)";
                        e.currentTarget.style.transform = "translateY(-1px)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background =
                          "rgba(244, 234, 201, 0.5)";
                        e.currentTarget.style.borderColor =
                          "rgba(122, 46, 42, 0.22)";
                        e.currentTarget.style.transform = "translateY(0)";
                      }}
                    >
                      <span
                        aria-hidden
                        style={{
                          color: "#7A2E2A",
                          fontWeight: 700,
                          fontStyle: "normal",
                          flexShrink: 0,
                        }}
                      >
                        ›
                      </span>
                      <span>{text}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </main>
    </>
  );
}

// "Continue reading" shelf — displayed above the "begin a new work"
// suggestions when the Reading mode is active and the reader has opened at
// least one work. Reads `gd:read:progress` once on mount; re-reads after a
// remove action so the shelf stays in sync without a page reload.
function ContinueReadingShelf({ lang }: { lang: Lang }) {
  const [records, setRecords] = useState<ProgressRecord[]>([]);
  const isMr = lang === "mr";

  useEffect(() => {
    setRecords(loadProgress());
  }, []);

  function handleRemove(slug: string) {
    removeProgress(slug);
    setRecords(loadProgress());
  }

  if (records.length === 0) return null;

  return (
    <div className="mt-5">
      <p
        className={`mb-2 text-[13.5px] ${isMr ? "font-deva" : ""}`}
        style={{ color: "var(--text-tertiary)" }}
      >
        {isMr ? "वाचन चालू ठेवा:" : "Continue reading:"}
      </p>
      <ul className="flex flex-col gap-2">
        {records.map((rec) => {
          const pct = Math.min(
            100,
            Math.round((rec.page / Math.max(1, rec.totalPages)) * 100),
          );
          const isDeva = /[ऀ-ॿ]/.test(rec.workTitle);
          return (
            <li key={rec.slug} className="flex items-center gap-3">
              <Link
                href={`/read/${rec.slug}?lang=${lang}`}
                className="group flex min-w-0 flex-1 items-center gap-3 rounded-[6px] px-3 py-2.5 text-left transition-all"
                style={{
                  background: "rgba(244, 234, 201, 0.5)",
                  border: "1px solid rgba(122, 46, 42, 0.22)",
                  textDecoration: "none",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(244, 234, 201, 0.85)";
                  e.currentTarget.style.borderColor = "rgba(122, 46, 42, 0.4)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "rgba(244, 234, 201, 0.5)";
                  e.currentTarget.style.borderColor = "rgba(122, 46, 42, 0.22)";
                }}
              >
                {/* Title */}
                <span
                  className={`min-w-0 flex-1 truncate text-[14px] leading-snug ${
                    isDeva || isMr ? "font-deva" : ""
                  }`}
                  style={{ color: "#5A2520" }}
                >
                  {rec.workTitle}
                </span>
                {/* Progress bar + page label */}
                <span className="flex shrink-0 items-center gap-2">
                  <span
                    className="h-[5px] w-[64px] overflow-hidden rounded-full"
                    style={{ background: "rgba(122, 46, 42, 0.15)" }}
                  >
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${pct}%`,
                        background: "var(--accent-gold, #C89A3C)",
                      }}
                    />
                  </span>
                  <span
                    className={`text-[12px] tabular-nums ${isMr ? "font-deva" : ""}`}
                    style={{ color: "var(--text-secondary)" }}
                  >
                    {isMr
                      ? `पा.${rec.page}/${rec.totalPages}`
                      : `p.${rec.page}/${rec.totalPages}`}
                  </span>
                </span>
              </Link>
              {/* Remove control */}
              <button
                type="button"
                aria-label={
                  isMr
                    ? `${rec.workTitle} हटवा`
                    : `Remove ${rec.workTitle}`
                }
                onClick={() => handleRemove(rec.slug)}
                className="shrink-0 text-[16px] leading-none"
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-tertiary)",
                  padding: "4px 6px",
                  opacity: 0.6,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = "1";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = "0.6";
                }}
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

// Left-rail Gurudev portrait — pinned to the LEFT EDGE of the viewport
// (position: fixed), fills top-to-bottom with a hard right edge against
// which the content column begins. No mask fade, no sepia, no caption —
// devotees know the face.
// Round-13: single static medallion. Slideshow dropped per the critic
// (motion = "look here", forever — and the composer needs that attention).
// One iconic photo: the painted Pandit portrait, warm tones that integrate
// with the parchment. Medallion shrunk slightly so it stops dominating the
// page on first frame.
function PortraitMedallion() {
  return (
    <div
      aria-hidden="true"
      className="mx-auto mb-3 overflow-hidden"
      style={{
        width: 120,
        height: 160,
        borderRadius: "50%",
        border: "3px solid #6B4538",
        boxShadow:
          "0 4px 16px rgba(60, 30, 10, 0.28), inset 0 0 0 1px rgba(0, 0, 0, 0.10)",
      }}
    >
      <Image
        src="/lineage-portrait.jpg"
        alt=""
        width={854}
        height={1280}
        priority
        className="h-full w-full object-cover"
        style={{ objectPosition: "50% 30%" }}
      />
    </div>
  );
}
