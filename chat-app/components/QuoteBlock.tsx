import Link from "next/link";
import type { Quote } from "../data/mock-conversations";
import { authorDisplayName } from "../lib/authors";

// Renders a verbatim quote with its attribution directly below — per ADR-007
// the quote IS the citation. The internal `kind` classifier (canonical /
// athvani / biography) is no longer shown in the UI — it's metadata that
// confused devotees ("what is canonical?"). Quotes from athvani sources are
// still visually distinct via the narrator's name in the author field.
//
// When `quote.workId` is non-empty AND `quote.kind === "canonical"`, a small
// "Read in full →" link is rendered below the attribution. This is only shown
// for canonical works because those are the ones served by /read/{slug}.
// Athvani and biography quotes don't have a dedicated reader URL.
// `lang` is optional — passed through to the reader URL when available, so the
// reader opens in the right language; omitted if the caller doesn't have it.
// `fromUrl` is optional — when provided, it is appended as `&from=` so the
// reader's back link can return the user to the exact Q&A or reader session
// they came from (back-navigation origin-awareness, ADR-???).
export default function QuoteBlock({
  quote,
  lang,
  fromUrl,
}: {
  // Accept undefined so callers can pass partially-streamed fields (e.g.
  // `ex.quote` before its delta arrives) without a type assertion.
  // The runtime guard below handles it safely.
  quote: Quote | undefined;
  lang?: string;
  fromUrl?: string;
}) {
  // During streaming a citation/example can render before its quote/body is
  // populated; bail out until there's something to show (avoids a crash).
  if (!quote || !quote.body) return null;
  const containsDevanagari = /[ऀ-ॿ]/.test(quote.body);
  const isMr = lang === "mr";
  const showReadLink = quote.kind === "canonical" && !!quote.workId;
  // Build the "Read in full" href. Use URLSearchParams so we never misplace
  // the first `?` vs subsequent `&` separators.
  const readHref = showReadLink
    ? (() => {
        const qs = new URLSearchParams();
        if (quote.readPage) qs.set("page", String(quote.readPage));
        if (lang) qs.set("lang", lang);
        if (fromUrl) qs.set("from", fromUrl);
        const qStr = qs.toString();
        return `/read/${quote.workId}${qStr ? `?${qStr}` : ""}`;
      })()
    : null;
  return (
    <div>
      <blockquote
        className={`gd-quote ${containsDevanagari ? "font-deva" : ""}`}
      >
        {quote.body}
      </blockquote>
      <p className="gd-quote-attr">
        — {quote.workTitle}, {quote.location} · {authorDisplayName(quote.author)}
      </p>
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
