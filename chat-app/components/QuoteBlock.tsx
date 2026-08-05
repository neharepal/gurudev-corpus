import Link from "next/link";
import type { Quote } from "../data/mock-conversations";
import { renderInlineMd } from "../lib/render-inline-md";
import {
  buildReadHref,
  cleanParaphrase,
  formatCardAttribution,
  formatInlineAttribution,
} from "../lib/quote-formatting";

// Renders a verbatim quote with its attribution. Two variants:
//
//  * `variant="card"` (default) — the historical bordered-card look with a
//    long "— Title, Location · Author" line and a separate "→ Read in full"
//    link below. Used for Gurudev's Words and pravachan examples where the
//    quote stands on its own.
//
//  * `variant="inline"` — the woven-prose look introduced for Q&A citations
//    (per Ninad's readability feedback, 2026-08-04). Thin left rail in
//    accent-maroon, no top/bottom border, no "Read in full" button — the
//    attribution line itself is the click target. Reads as an embedded
//    blockquote inside continuous narrative prose rather than a fenced-off
//    card.
//
// Pure formatting logic (attribution assembly, URL construction) lives in
// `lib/quote-formatting.ts` and is unit-tested.

export type QuoteBlockVariant = "card" | "inline";

export default function QuoteBlock({
  quote,
  lang,
  fromUrl,
  variant = "card",
}: {
  // Accept undefined so callers can pass partially-streamed fields (e.g.
  // `ex.quote` before its delta arrives) without a type assertion.
  quote: Quote | undefined;
  lang?: string;
  fromUrl?: string;
  variant?: QuoteBlockVariant;
}) {
  // Streaming guard: bail out until there's a body to render.
  if (!quote || !quote.body) return null;

  const containsDevanagari = /[ऀ-ॿ]/.test(quote.body);
  const isMr = lang === "mr";
  const readHref = buildReadHref(quote, { lang, fromUrl });

  // Paraphrase / translation gloss — the LLM populates `quote.paraphrase`
  // when the quote's source language differs from the reader's language.
  // `cleanParaphrase` strips redundant "Paraphrase:" / "Translation:" /
  // "Gloss:" label prefixes some models emit.
  const paraphrase = cleanParaphrase(quote.paraphrase);
  const paraphraseContainsDeva = paraphrase && /[ऀ-ॿ]/.test(paraphrase);

  if (variant === "inline") {
    // Woven-prose variant: thin left rail, compact attribution as link,
    // no top/bottom fence. Sits inside narrative flow.
    const inlineAttr = formatInlineAttribution(quote);
    return (
      <blockquote
        className={`gd-quote-inline my-5 pl-4 ${containsDevanagari ? "font-deva" : ""}`}
        style={{
          borderLeft: "2px solid var(--accent-maroon)",
        }}
      >
        <span className="gd-quote-inline-body">{quote.body}</span>
        {paraphrase ? (
          <span
            className={`gd-quote-inline-paraphrase mt-1 block ${
              paraphraseContainsDeva ? "font-deva" : ""
            }`}
          >
            {renderInlineMd(paraphrase)}
          </span>
        ) : null}
        <span
          className="gd-quote-inline-cite mt-1.5 block"
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "12.5px",
            color: "var(--text-secondary, #6E5B3E)",
            letterSpacing: "0.02em",
          }}
        >
          {readHref ? (
            <Link
              href={readHref}
              className={`gd-quote-inline-link ${isMr ? "font-deva" : ""}`}
              style={{
                color: "var(--accent-maroon)",
                borderBottom: "1px solid var(--accent-maroon)",
                textDecoration: "none",
                fontWeight: 500,
                paddingBottom: "1px",
              }}
            >
              {inlineAttr}
            </Link>
          ) : (
            inlineAttr
          )}
        </span>
      </blockquote>
    );
  }

  // Card variant (unchanged shape — used by Gurudev's Words + examples).
  const attribution = formatCardAttribution(quote);
  return (
    <div>
      <blockquote
        className={`gd-quote ${containsDevanagari ? "font-deva" : ""}`}
      >
        {quote.body}
      </blockquote>
      {paraphrase ? (
        <p
          className={`gd-quote-paraphrase mt-1 italic ${
            paraphraseContainsDeva ? "font-deva" : ""
          }`}
          style={{ color: "var(--text-secondary, #5A4632)", opacity: 0.85 }}
        >
          {renderInlineMd(paraphrase)}
        </p>
      ) : null}
      <p className="gd-quote-attr">{attribution}</p>
      {readHref ? (
        <Link
          href={readHref}
          className={`mt-1 inline-block text-[14px] ${isMr ? "font-deva" : ""}`}
          style={{ color: "var(--accent-maroon)" }}
        >
          {isMr ? "→ संपूर्ण वाचा" : "→ Read in full"}
        </Link>
      ) : null}
    </div>
  );
}
