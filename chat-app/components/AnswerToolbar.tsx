"use client";

// Per-answer toolbar — explicit text labels alongside the glyphs so
// older devotees on Zoom screen-share recognize the controls without
// having to decode icon-only buttons (user feedback 2026-06-15).
// Functionality is deferred to a follow-up implementation pass per
// RFC-004 §Content flagging + §WhatsApp share.
type Lang = "en" | "mr";

const LABELS: Record<
  Lang,
  { report: string; reportAria: string; share: string; shareAria: string }
> = {
  en: {
    report: "Report issue",
    reportAria: "Report an issue with this answer",
    share: "Share",
    shareAria: "Share this answer",
  },
  mr: {
    report: "त्रुटी कळवा",
    reportAria: "या उत्तरातील त्रुटी कळवा",
    share: "शेअर करा",
    shareAria: "हे उत्तर शेअर करा",
  },
};

export default function AnswerToolbar({ lang = "en" }: { lang?: Lang }) {
  const l = LABELS[lang];
  const isMr = lang === "mr";
  const btn = {
    color: "var(--text-secondary)",
    border: "1px solid var(--border-soft)",
    background: "transparent",
    cursor: "pointer",
    fontFamily: "var(--font-serif)",
  } as const;
  return (
    <div className="mb-4 flex items-center gap-2 text-[13px]">
      <button
        type="button"
        aria-label={l.reportAria}
        // TODO: RFC-004 §Content flagging — wire to flag modal + flag_queue.yaml.
        onClick={() => {
          /* noop until follow-up */
        }}
        className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
          isMr ? "font-deva" : ""
        }`}
        style={btn}
      >
        <span aria-hidden>⚐</span>
        <span>{l.report}</span>
      </button>
      <button
        type="button"
        aria-label={l.shareAria}
        // TODO: RFC-004 §WhatsApp share — wire to share menu.
        onClick={() => {
          /* noop until follow-up */
        }}
        className={`inline-flex items-center gap-1.5 rounded-[5px] px-2.5 py-1.5 ${
          isMr ? "font-deva" : ""
        }`}
        style={btn}
      >
        <span aria-hidden>↗</span>
        <span>{l.share}</span>
      </button>
    </div>
  );
}
