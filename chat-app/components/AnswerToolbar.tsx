"use client";

// Per-answer toolbar — explicit text labels alongside the glyphs so
// older devotees on Zoom screen-share recognize the controls without
// having to decode icon-only buttons (user feedback 2026-06-15).
//
// Report issue (RFC-004): opens a modal with a required radio-category group
// and an optional detail textarea, POSTs category + auto-attached fields to
// /api/report (flag-and-queue), then shows a "Thank you" message.
//
// Share (RFC-004 §8): a small popover offering WhatsApp, Copy link, and
// (when available) the native Web Share API.

import { useState, useEffect, useRef } from "react";
import { reportIssue, type ReportCitation } from "../lib/api";

type Lang = "en" | "mr";

// ── RFC-004 flag categories ──────────────────────────────────────────────────
// These are the exact option labels from RFC-004 §Content flagging mechanism.
// The value sent to the backend is the English slug (category key).
type FlagCategory = {
  key: string;
  en: string;
  mr: string;
};

const FLAG_CATEGORIES: FlagCategory[] = [
  {
    key: "wrong-attribution",
    en: "Wrong attribution",
    mr: "चुकीचे संदर्भ",
  },
  {
    key: "quote-mismatch",
    en: "Quoted text doesn't match the source",
    mr: "उद्धृत मजकूर स्रोताशी जुळत नाही",
  },
  {
    key: "not-in-corpus",
    en: "Mentions something not actually in the corpus",
    mr: "संग्रहात नसलेली गोष्ट उल्लेख केली आहे",
  },
  {
    key: "translation-issue",
    en: "Translation or paraphrase issue",
    mr: "भाषांतर किंवा भावार्थ चूक",
  },
  {
    key: "missing-context",
    en: "Missing important context",
    mr: "महत्त्वाचा संदर्भ गहाळ आहे",
  },
  {
    key: "mislabeled-sources",
    en: "Sources are mislabeled or in wrong section",
    mr: "स्रोत चुकीच्या ठिकाणी किंवा चुकीचे लेबल",
  },
  {
    key: "other",
    en: "Other",
    mr: "इतर",
  },
];

// ── Localised strings ────────────────────────────────────────────────────────
const LABELS: Record<
  Lang,
  {
    report: string;
    reportAria: string;
    reportModalTitle: string;
    reportWhatLabel: string;
    reportDetailPlaceholder: string;
    reportSubmit: string;
    reportCancel: string;
    reportThanks: string;
    share: string;
    shareAria: string;
    shareWhatsApp: string;
    shareCopyLink: string;
    shareMore: string;
    linkCopied: string;
  }
> = {
  en: {
    report: "Report issue",
    reportAria: "Report an issue with this answer",
    reportModalTitle: "Report an issue with this answer",
    reportWhatLabel: "What's wrong?",
    reportDetailPlaceholder: "Add detail (optional, helps Neha review)…",
    reportSubmit: "Submit flag",
    reportCancel: "Cancel",
    reportThanks: "Thank you. Neha will review and correct if needed.",
    share: "Share",
    shareAria: "Share this answer",
    shareWhatsApp: "WhatsApp",
    shareCopyLink: "Copy link",
    shareMore: "More…",
    linkCopied: "Link copied",
  },
  mr: {
    report: "त्रुटी कळवा",
    reportAria: "या उत्तरातील त्रुटी कळवा",
    reportModalTitle: "या उत्तरातील त्रुटी कळवा",
    reportWhatLabel: "काय चूक आहे?",
    reportDetailPlaceholder: "अधिक माहिती द्या (ऐच्छिक)…",
    reportSubmit: "नोंद पाठवा",
    reportCancel: "रद्द करा",
    reportThanks: "धन्यवाद. नेहा तपासून गरज असल्यास दुरुस्त करतील.",
    share: "शेअर करा",
    shareAria: "हे उत्तर शेअर करा",
    shareWhatsApp: "WhatsApp",
    shareCopyLink: "लिंक कॉपी करा",
    shareMore: "आणखी…",
    linkCopied: "लिंक कॉपी केली",
  },
};

export type AnswerToolbarProps = {
  lang?: Lang;
  question?: string;
  mode?: string;
  citations?: ReportCitation[];
};

export default function AnswerToolbar({
  lang = "en",
  question = "",
  mode = "qa",
  citations = [],
}: AnswerToolbarProps) {
  const l = LABELS[lang];
  const isMr = lang === "mr";

  // ── Report state ─────────────────────────────────────────────────────────
  const [reportOpen, setReportOpen] = useState(false);
  const [reportCategory, setReportCategory] = useState<string | null>(null);
  const [reportDetail, setReportDetail] = useState("");
  const [reportSubmitting, setReportSubmitting] = useState(false);
  const [reportDone, setReportDone] = useState(false);

  // ── Share state ───────────────────────────────────────────────────────────
  const [shareOpen, setShareOpen] = useState(false);
  const [linkCopied, setLinkCopied] = useState(false);
  const shareRef = useRef<HTMLDivElement>(null);

  // Close share popover on outside click
  useEffect(() => {
    if (!shareOpen) return;
    function handleClick(e: MouseEvent) {
      if (shareRef.current && !shareRef.current.contains(e.target as Node)) {
        setShareOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [shareOpen]);

  // ── Report submit ─────────────────────────────────────────────────────────
  async function handleReportSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!reportCategory) return; // guard: button should be disabled but be safe
    setReportSubmitting(true);
    try {
      await reportIssue({
        question,
        mode,
        citations,
        note: reportDetail.trim() || undefined,
        category: reportCategory,
      });
      setReportDone(true);
      setReportOpen(false);
      setReportCategory(null);
      setReportDetail("");
    } catch {
      // Network / server error: keep the form open so the user can retry.
    } finally {
      setReportSubmitting(false);
    }
  }

  function handleOpenReport() {
    if (!reportDone) {
      setReportOpen((v) => !v);
    }
  }

  function handleCancelReport() {
    setReportOpen(false);
    setReportCategory(null);
    setReportDetail("");
  }

  // ── Share handlers ────────────────────────────────────────────────────────
  function getShareUrl(): string {
    if (typeof window === "undefined") return "";
    return window.location.href;
  }

  function getShareText(): string {
    const q = question.trim();
    return q ? q : "Gurudev Sangrah answer";
  }

  function handleWhatsApp() {
    const url = getShareUrl();
    const text = getShareText();
    const encoded = encodeURIComponent(text + (url ? " " + url : ""));
    const waUrl = `https://wa.me/?text=${encoded}`;
    if (typeof window !== "undefined") {
      window.open(waUrl, "_blank", "noopener,noreferrer");
    }
    setShareOpen(false);
  }

  function handleCopyLink() {
    const url = getShareUrl();
    if (
      typeof navigator !== "undefined" &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function"
    ) {
      navigator.clipboard
        .writeText(url)
        .then(() => {
          setLinkCopied(true);
          setTimeout(() => setLinkCopied(false), 2500);
        })
        .catch(() => {
          // Clipboard denied — ignore silently.
        });
    }
    setShareOpen(false);
  }

  function handleNativeShare() {
    if (typeof navigator === "undefined" || typeof navigator.share !== "function") return;
    const url = getShareUrl();
    navigator.share({ url }).catch(() => {
      // User dismissed — not an error.
    });
    setShareOpen(false);
  }

  const hasNativeShare =
    typeof navigator !== "undefined" &&
    typeof navigator.share === "function";

  // ── Styles ────────────────────────────────────────────────────────────────
  const btn = {
    color: "var(--text-secondary)",
    border: "1px solid var(--border-soft)",
    background: "transparent",
    cursor: "pointer",
    fontFamily: "var(--font-serif)",
  } as const;

  const submitBtnStyle = {
    background: "#6B1F1F",
    color: "#F4EAC9",
    border: "1px solid #4F1414",
    boxShadow: "inset 0 1px 0 rgba(255,220,170,0.2)",
    fontFamily: isMr ? undefined : "var(--font-serif)",
  } as const;

  return (
    <div className="mb-4">
      {/* ── Button row ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-[13px]">
        {/* Report issue button */}
        <button
          type="button"
          aria-label={l.reportAria}
          aria-expanded={reportOpen}
          onClick={handleOpenReport}
          className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
            isMr ? "font-deva" : ""
          }`}
          style={btn}
        >
          <span aria-hidden>⚐</span>
          <span>{reportDone ? l.reportThanks : l.report}</span>
        </button>

        {/* Share button + popover */}
        <div ref={shareRef} className="relative">
          <button
            type="button"
            aria-label={l.shareAria}
            aria-expanded={shareOpen}
            onClick={() => setShareOpen((v) => !v)}
            className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
              isMr ? "font-deva" : ""
            }`}
            style={btn}
          >
            <span aria-hidden>↗</span>
            <span>{linkCopied ? l.linkCopied : l.share}</span>
          </button>

          {/* Share popover */}
          {shareOpen && (
            <div
              role="menu"
              className="absolute left-0 top-full z-50 mt-1 w-40 rounded-[6px] py-1 shadow-md"
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border-soft)",
              }}
            >
              {/* WhatsApp */}
              <button
                type="button"
                role="menuitem"
                onClick={handleWhatsApp}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-panel)] ${
                  isMr ? "font-deva" : ""
                }`}
                style={{ fontFamily: isMr ? undefined : "var(--font-serif)", color: "var(--text-primary)" }}
              >
                <span aria-hidden>💬</span>
                {l.shareWhatsApp}
              </button>

              {/* Copy link */}
              <button
                type="button"
                role="menuitem"
                onClick={handleCopyLink}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-panel)] ${
                  isMr ? "font-deva" : ""
                }`}
                style={{ fontFamily: isMr ? undefined : "var(--font-serif)", color: "var(--text-primary)" }}
              >
                <span aria-hidden>🔗</span>
                {l.shareCopyLink}
              </button>

              {/* More… (native share, mobile only) */}
              {hasNativeShare && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleNativeShare}
                  className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] hover:bg-[var(--bg-panel)] ${
                    isMr ? "font-deva" : ""
                  }`}
                  style={{ fontFamily: isMr ? undefined : "var(--font-serif)", color: "var(--text-primary)" }}
                >
                  <span aria-hidden>⋯</span>
                  {l.shareMore}
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── Report modal ─────────────────────────────────────────────────── */}
      {reportOpen && (
        <form
          onSubmit={handleReportSubmit}
          className="mt-3 rounded-[6px] p-4"
          style={{
            border: "1px solid var(--border-soft)",
            background: "var(--bg-surface)",
          }}
        >
          {/* Title */}
          <p
            className={`mb-3 text-[14px] font-semibold ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-primary)", fontFamily: isMr ? undefined : "var(--font-serif)" }}
          >
            {l.reportModalTitle}
          </p>

          {/* What's wrong? label */}
          <p
            className={`mb-2 text-[13px] font-medium ${isMr ? "font-deva" : ""}`}
            style={{ color: "var(--text-secondary)" }}
          >
            {l.reportWhatLabel}
          </p>

          {/* Radio group */}
          <fieldset className="mb-3 space-y-1.5" style={{ border: "none", padding: 0, margin: 0 }}>
            <legend className="sr-only">{l.reportWhatLabel}</legend>
            {FLAG_CATEGORIES.map((cat) => (
              <label
                key={cat.key}
                className={`flex cursor-pointer items-center gap-2 text-[13px] ${
                  isMr ? "font-deva" : ""
                }`}
                style={{
                  color: "var(--text-primary)",
                  fontFamily: isMr ? undefined : "var(--font-serif)",
                }}
              >
                <input
                  type="radio"
                  name="flag-category"
                  value={cat.key}
                  checked={reportCategory === cat.key}
                  onChange={() => setReportCategory(cat.key)}
                  disabled={reportSubmitting}
                  className="accent-[#6B1F1F]"
                />
                {isMr ? cat.mr : cat.en}
              </label>
            ))}
          </fieldset>

          {/* Detail textarea */}
          <textarea
            value={reportDetail}
            onChange={(e) => setReportDetail(e.target.value)}
            placeholder={l.reportDetailPlaceholder}
            rows={3}
            disabled={reportSubmitting}
            className={`mb-3 block w-full resize-none rounded-[4px] bg-transparent px-2 py-1.5 text-[14px] outline-none ${
              isMr ? "font-deva" : ""
            }`}
            style={{
              fontFamily: isMr ? undefined : "var(--font-serif)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-soft)",
              lineHeight: 1.5,
            }}
          />

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={reportSubmitting || reportCategory === null}
              className={`rounded-[5px] px-3 py-1.5 text-[13px] font-semibold disabled:opacity-50 ${
                isMr ? "font-deva" : ""
              }`}
              style={submitBtnStyle}
            >
              {l.reportSubmit}
            </button>
            <button
              type="button"
              onClick={handleCancelReport}
              disabled={reportSubmitting}
              className={`rounded-[5px] px-3 py-1.5 text-[13px] disabled:opacity-50 ${
                isMr ? "font-deva" : ""
              }`}
              style={btn}
            >
              {l.reportCancel}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
