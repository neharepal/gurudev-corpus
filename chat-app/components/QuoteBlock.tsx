import type { Quote } from "../data/mock-conversations";
import { authorDisplayName } from "../lib/authors";

// Renders a verbatim quote with its attribution directly below — per ADR-007
// the quote IS the citation. The internal `kind` classifier (canonical /
// athvani / biography) is no longer shown in the UI — it's metadata that
// confused devotees ("what is canonical?"). Quotes from athvani sources are
// still visually distinct via the narrator's name in the author field.
export default function QuoteBlock({ quote }: { quote: Quote }) {
  const containsDevanagari = /[ऀ-ॿ]/.test(quote.body);
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
    </div>
  );
}
