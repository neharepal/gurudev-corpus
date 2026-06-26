"use client";

// Per-answer toolbar — explicit text labels alongside the glyphs so
// older devotees on Zoom screen-share recognize the controls without
// having to decode icon-only buttons (user feedback 2026-06-15).
//
// Share: uses Web Share API when available (mobile); copies the current URL to
// clipboard otherwise, showing a brief "Link copied" confirmation.
//
// Report issue: opens a small inline form to capture a note about the answer,
// POSTs it to /api/report (flag-and-queue), then shows a "Thank you" message.
// Applying corrections is a separate maintenance step (garble Phase 2).

import { useState } from "react";
import { reportIssue, type ReportCitation } from "../lib/api";

type Lang = "en" | "mr";

const LABELS: Record<
  Lang,
  {
    report: string;
    reportAria: string;
    share: string;
    shareAria: string;
    reportFormPlaceholder: string;
    reportSubmit: string;
    reportCancel: string;
    reportThanks: string;
    linkCopied: string;
  }
> = {
  en: {
    report: "Report issue",
    reportAria: "Report an issue with this answer",
    share: "Share",
    shareAria: "Share this answer",
    reportFormPlaceholder: "Describe the issue (optional)…",
    reportSubmit: "Submit",
    reportCancel: "Cancel",
    reportThanks: "Thank you — reported",
    linkCopied: "Link copied",
  },
  mr: {
    report: "त्रुटी कळवा",
    reportAria: "या उत्तरातील त्रुटी कळवा",
    share: "शेअर करा",
    shareAria: "हे उत्तर शेअर करा",
    reportFormPlaceholder: "त्रुटी सांगा (ऐच्छिक)…",
    reportSubmit: "पाठवा",
    reportCancel: "रद्द करा",
    reportThanks: "धन्यवाद — नोंद केली",
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

  // Share state
  const [shareFeedback, setShareFeedback] = useState<string | null>(null);

  // Report state
  const [reportOpen, setReportOpen] = useState(false);
  const [reportNote, setReportNote] = useState("");
  const [reportSubmitting, setReportSubmitting] = useState(false);
  const [reportDone, setReportDone] = useState(false);

  // ── Share handler ──────────────────────────────────────────────────────────
  // Builds the shareable URL from the current window.location (the
  // /chat?mode=...&lang=...&q=... URL reproduces the answer when opened).
  // Uses Web Share API when available (mobile); falls back to clipboard copy.
  // Guarded for SSR / missing APIs.
  function handleShare() {
    if (typeof window === "undefined") return;

    const url = window.location.href;

    // Web Share API (mobile, progressive)
    if (
      typeof navigator !== "undefined" &&
      typeof navigator.share === "function"
    ) {
      navigator
        .share({ url })
        .catch(() => {
          // User dismissed the share sheet — not an error.
        });
      return;
    }

    // Clipboard fallback
    if (
      typeof navigator !== "undefined" &&
      navigator.clipboard &&
      typeof navigator.clipboard.writeText === "function"
    ) {
      navigator.clipboard
        .writeText(url)
        .then(() => {
          setShareFeedback(l.linkCopied);
          setTimeout(() => setShareFeedback(null), 2500);
        })
        .catch(() => {
          // Clipboard access denied — silently ignore.
        });
    }
  }

  // ── Report submit handler ──────────────────────────────────────────────────
  async function handleReportSubmit(e: React.FormEvent) {
    e.preventDefault();
    setReportSubmitting(true);
    try {
      await reportIssue({
        question,
        mode,
        citations,
        note: reportNote.trim() || undefined,
      });
      setReportDone(true);
      setReportOpen(false);
      setReportNote("");
    } catch {
      // Network / server error: keep the form open so the user can retry.
    } finally {
      setReportSubmitting(false);
    }
  }

  const btn = {
    color: "var(--text-secondary)",
    border: "1px solid var(--border-soft)",
    background: "transparent",
    cursor: "pointer",
    fontFamily: "var(--font-serif)",
  } as const;

  return (
    <div className="mb-4">
      {/* Button row */}
      <div className="flex items-center gap-2 text-[13px]">
        {/* Report issue button */}
        <button
          type="button"
          aria-label={l.reportAria}
          aria-expanded={reportOpen}
          onClick={() => {
            if (!reportDone) setReportOpen((v) => !v);
          }}
          className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
            isMr ? "font-deva" : ""
          }`}
          style={btn}
        >
          <span aria-hidden>⚐</span>
          <span>{reportDone ? l.reportThanks : l.report}</span>
        </button>

        {/* Share button */}
        <button
          type="button"
          aria-label={l.shareAria}
          onClick={handleShare}
          className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
            isMr ? "font-deva" : ""
          }`}
          style={btn}
        >
          <span aria-hidden>↗</span>
          <span>{shareFeedback ?? l.share}</span>
        </button>
      </div>

      {/* Report inline form — shown below the buttons */}
      {reportOpen && (
        <form
          onSubmit={handleReportSubmit}
          className="mt-3 rounded-[6px] p-3"
          style={{
            border: "1px solid var(--border-soft)",
            background: "var(--bg-surface)",
          }}
        >
          <textarea
            value={reportNote}
            onChange={(e) => setReportNote(e.target.value)}
            placeholder={l.reportFormPlaceholder}
            rows={3}
            disabled={reportSubmitting}
            className={`mb-2 block w-full resize-none rounded-[4px] bg-transparent px-2 py-1.5 text-[14px] outline-none ${
              isMr ? "font-deva" : ""
            }`}
            style={{
              fontFamily: isMr ? undefined : "var(--font-serif)",
              color: "var(--text-primary)",
              border: "1px solid var(--border-soft)",
              lineHeight: 1.5,
            }}
          />
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={reportSubmitting}
              className={`rounded-[5px] px-3 py-1.5 text-[13px] font-semibold disabled:opacity-50 ${
                isMr ? "font-deva" : ""
              }`}
              style={{
                background: "#6B1F1F",
                color: "#F4EAC9",
                border: "1px solid #4F1414",
                boxShadow: "inset 0 1px 0 rgba(255,220,170,0.2)",
                fontFamily: isMr ? undefined : "var(--font-serif)",
              }}
            >
              {l.reportSubmit}
            </button>
            <button
              type="button"
              onClick={() => {
                setReportOpen(false);
                setReportNote("");
              }}
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
