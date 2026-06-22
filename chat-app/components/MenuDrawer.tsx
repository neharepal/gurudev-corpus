"use client";

import { useEffect } from "react";
import { MODES, type ModeId } from "../data/mock-conversations";
import type { Lang } from "./ModeTabs";

const MODE_DESCRIPTIONS: Record<ModeId, { en: string; mr: string }> = {
  qa: {
    en: "Ask anything and get verbatim passages from the literature.",
    mr: "साहित्यातील उतार्‍यांद्वारे उत्तर मिळवा.",
  },
  pravachan: {
    en: "Gather examples and quotes to compose a discourse.",
    mr: "प्रवचनासाठी संदर्भ आणि उद्धरणे गोळा करा.",
  },
  reading: {
    en: "Open and read source texts directly.",
    mr: "थेट ग्रंथ आणि अध्याय वाचा.",
  },
};

const MODE_LABEL_MR: Record<ModeId, string> = {
  qa: "प्रश्नोत्तर",
  pravachan: "प्रवचन",
  reading: "वाचन",
};

const SECTION_LABELS = {
  lang: { en: "Language", mr: "भाषा" },
  mode: { en: "Mode", mr: "रीत" },
  about: { en: "About this archive", mr: "या संग्रहाविषयी" },
  aboutBody: {
    en: "Gurudev Sangrah is a chat-based research aid for the literature of Shri Gurudev Ranade and the Nimbal sampradaya. Every answer cites a verbatim source passage; nothing is paraphrased.",
    mr: "गुरुदेव संग्रह हे श्री गुरुदेव रानडे आणि निंबाळ संप्रदायाच्या साहित्यासाठी प्रश्नोत्तरांचा अभ्यास साधन आहे. प्रत्येक उत्तर मूळ ग्रंथातून थेट उद्धृत केलेले असते.",
  },
};

type Props = {
  open: boolean;
  onClose: () => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  mode: ModeId;
  setMode: (m: ModeId) => void;
};

export default function MenuDrawer({
  open,
  onClose,
  lang,
  setLang,
  mode,
  setMode,
}: Props) {
  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Scrim — only mounted when open so it never blocks clicks
          on page chrome (hamburger, mode chip) when closed. */}
      {open && (
        <div
          onClick={onClose}
          aria-hidden="true"
          className="fixed inset-0 z-40"
          style={{
            background: "rgba(40, 25, 12, 0.32)",
          }}
        />
      )}

      {/* Drawer. Stays mounted to keep slide animation, but pointer-events
          are killed when closed so the off-screen panel can't catch clicks
          intended for the page beneath. */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        className="fixed inset-y-0 left-0 z-50 flex w-[320px] flex-col transition-transform"
        style={{
          transform: open ? "translateX(0)" : "translateX(-100%)",
          background: "var(--bg-surface)",
          borderRight: "1px solid #6B1F1F",
          boxShadow: "0 0 28px rgba(60, 30, 10, 0.25)",
          pointerEvents: open ? "auto" : "none",
          visibility: open ? "visible" : "hidden",
        }}
      >
        {/* Header. */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border-soft)" }}
        >
          <h2
            className="text-[17px] font-semibold"
            style={{ color: "#6B1F1F", fontFamily: "var(--font-serif)" }}
          >
            {lang === "mr" ? "सेटिंग्ज" : "Settings"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
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

        {/* Body. */}
        <div className="flex-1 overflow-y-auto px-5 py-5">
          {/* Language. */}
          <section className="mb-8">
            <h3 className="gd-label mb-3" style={{ color: "#7A2E2A" }}>
              {SECTION_LABELS.lang[lang]}
            </h3>
            <div
              className="inline-flex items-stretch overflow-hidden rounded-full text-[13px]"
              role="group"
              aria-label="Language"
              style={{ border: "1px solid #6B1F1F" }}
            >
              {(["en", "mr"] as Lang[]).map((l) => {
                const active = lang === l;
                return (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLang(l)}
                    className={l === "mr" ? "font-deva" : ""}
                    style={{
                      background: active ? "#6B1F1F" : "transparent",
                      color: active ? "#F4EAC9" : "#6B1F1F",
                      border: "none",
                      cursor: "pointer",
                      padding: "6px 16px",
                      fontWeight: active ? 700 : 500,
                    }}
                  >
                    {l === "en" ? "English" : "मराठी"}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Mode. */}
          <section className="mb-8">
            <h3 className="gd-label mb-3" style={{ color: "#7A2E2A" }}>
              {SECTION_LABELS.mode[lang]}
            </h3>
            <ul className="space-y-2">
              {MODES.map((m) => {
                const active = mode === m.id;
                const display =
                  lang === "mr" ? MODE_LABEL_MR[m.id] : m.label;
                return (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => setMode(m.id)}
                      className="block w-full rounded-[6px] px-3 py-2.5 text-left"
                      style={{
                        background: active
                          ? "rgba(122, 46, 42, 0.10)"
                          : "transparent",
                        border: active
                          ? "1px solid #7A2E2A"
                          : "1px solid var(--border-soft)",
                        cursor: "pointer",
                      }}
                    >
                      <div
                        className={`text-[15px] font-semibold ${
                          lang === "mr" ? "font-deva" : ""
                        }`}
                        style={{
                          color: active ? "#7A1F2B" : "var(--text-primary)",
                        }}
                      >
                        {display}
                      </div>
                      <div
                        className={`mt-0.5 text-[13px] leading-snug ${
                          lang === "mr" ? "font-deva" : ""
                        }`}
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {MODE_DESCRIPTIONS[m.id][lang]}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          {/* About. */}
          <section>
            <h3 className="gd-label mb-3" style={{ color: "#7A2E2A" }}>
              {SECTION_LABELS.about[lang]}
            </h3>
            <p
              className={`text-[13.5px] leading-relaxed ${
                lang === "mr" ? "font-deva" : ""
              }`}
              style={{ color: "var(--text-secondary)" }}
            >
              {SECTION_LABELS.aboutBody[lang]}
            </p>
          </section>
        </div>
      </aside>
    </>
  );
}
