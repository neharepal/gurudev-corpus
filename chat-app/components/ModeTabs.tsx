"use client";

import { MODES, type ModeId } from "../data/mock-conversations";

export type Lang = "en" | "mr";

const LABELS_EN: Record<ModeId, string> = {
  qa: "Q&A",
  pravachan: "Pravachan",
  reading: "Reading",
};

const LABELS_MR: Record<ModeId, string> = {
  qa: "प्रश्नोत्तर",
  pravachan: "प्रवचन",
  reading: "वाचन",
};

type Props = {
  mode: ModeId;
  onSelect: (mode: ModeId) => void;
  lang: Lang;
};

export default function ModeTabs({ mode, onSelect, lang }: Props) {
  const labels = lang === "mr" ? LABELS_MR : LABELS_EN;
  return (
    <div
      role="tablist"
      aria-label="Mode"
      className="mx-auto flex w-full max-w-[420px] items-stretch"
      style={{ borderBottom: "1px solid var(--border-soft)" }}
    >
      {MODES.map((m) => {
        const active = m.id === mode;
        return (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(m.id)}
            className={`flex-1 px-3 py-2.5 text-center transition-colors ${
              lang === "mr" ? "font-deva" : ""
            } ${active ? "text-[17px]" : "text-[15px]"}`}
            style={{
              borderBottom: active
                ? "2.5px solid #7A1F2B"
                : "2.5px solid transparent",
              color: active ? "#7A1F2B" : "#8A7560",
              marginBottom: "-1px",
              fontWeight: active ? 700 : 400,
              background: "transparent",
              fontFamily:
                lang === "mr" ? undefined : "var(--font-serif)",
            }}
          >
            {labels[m.id]}
          </button>
        );
      })}
    </div>
  );
}
