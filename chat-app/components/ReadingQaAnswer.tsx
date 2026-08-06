// RFC-023 — Reading-mode Q&A answer render.
//
// Distinct from the QAAnswer render (which sits above the citation loop in
// read/[slug]/page.tsx): here the answer body is one plain synthesis + an
// optional "Sources" footer. No verbatim quote cards — the reader is already
// looking at the book.
//
// Every link in the Sources footer runs through a shared onClick that closes
// the drawer on same-slug navigation. This is where the U2 fix lives:
// without it a click on a same-book link would soft-nav the page under the
// still-open drawer and the reader would see nothing change.

import Link from "next/link";
import type { MouseEvent } from "react";
import type { PassageLink } from "../data/mock-conversations";
import { renderBlockMd } from "../lib/render-block-md";
import {
  buildReadingLinkHref,
  isSameSlug,
  type Lang,
} from "../lib/reading-qa-links";

export default function ReadingQaAnswer({
  text,
  passageLinks,
  currentSlug,
  lang,
  onNav,
}: {
  /** Full answer body — Markdown allowed; rendered by `renderBlockMd`. */
  text: string;
  /** Sources footer content; server caps at 3. */
  passageLinks?: PassageLink[];
  /** The book the reader currently has open — U2 fix pivots on this. */
  currentSlug: string;
  /** UI language (labels / font); passed through to link hrefs. */
  lang: Lang;
  /** Called ONCE, synchronously, on same-slug link click BEFORE navigation
   *  so the drawer can close and the soft-nav becomes visible. */
  onNav?: () => void;
}) {
  const isMr = lang === "mr";
  const bodyContainsDeva = /[ऀ-ॿ]/.test(text || "");
  const links = (passageLinks ?? []).filter(
    (l) => l && l.workSlug && typeof l.page === "number" && l.label,
  );

  function onLinkClick(link: PassageLink) {
    return (_ev: MouseEvent<HTMLAnchorElement>) => {
      // U2 fix (RFC-023): on same-slug navigation the drawer would otherwise
      // stay open OVER the newly-loaded page and the reader would see no
      // visible change. Close the drawer synchronously so the soft-nav is
      // visible. Do NOT preventDefault — let Next.js Link do the actual nav.
      if (isSameSlug(link, currentSlug)) {
        onNav?.();
      }
    };
  }

  const sourcesLabel = isMr ? "स्रोत" : "Sources";

  return (
    <div>
      <div
        className={`text-[14px] synthesis-body ${bodyContainsDeva || isMr ? "font-deva" : ""}`}
        style={{ color: "var(--text-primary)", lineHeight: 1.6 }}
      >
        {renderBlockMd(text)}
      </div>

      {links.length > 0 ? (
        <div className="mt-3">
          <div
            className={`gd-label mb-1 ${isMr ? "font-deva" : ""}`}
            style={{
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              fontSize: "11px",
              letterSpacing: "0.06em",
            }}
          >
            {sourcesLabel}
          </div>
          <ul className="list-none p-0 m-0">
            {links.map((link, i) => {
              const href = buildReadingLinkHref(link, { lang });
              const crossWork = !isSameSlug(link, currentSlug);
              const labelHasDeva = /[ऀ-ॿ]/.test(link.label);
              return (
                <li key={i} className="mt-1">
                  <Link
                    href={href}
                    onClick={onLinkClick(link)}
                    className={`text-[14px] ${labelHasDeva ? "font-deva" : ""}`}
                    style={{
                      color: "var(--accent-maroon)",
                      textDecoration: "underline",
                      textUnderlineOffset: "2px",
                    }}
                  >
                    {link.label}
                  </Link>
                  {crossWork && link.workTitle ? (
                    <span
                      className={`ml-2 text-[12px] ${
                        /[ऀ-ॿ]/.test(link.workTitle) ? "font-deva" : ""
                      }`}
                      style={{ color: "var(--text-tertiary)" }}
                    >
                      {link.workTitle}
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
