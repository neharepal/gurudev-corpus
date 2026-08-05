import type { Quote } from "../data/mock-conversations";
import { authorDisplayName } from "./authors";

/**
 * Pure helpers for rendering a Quote. Extracted from QuoteBlock so both
 * card and inline variants share the same attribution / URL logic and both
 * are testable without a DOM.
 */

/**
 * Build the "Read in full" URL for a canonical quote, or return null when
 * the quote can't be linked (missing workId, non-canonical kind).
 */
export function buildReadHref(
  quote: Pick<Quote, "kind" | "workId" | "readPage"> | undefined,
  opts: { lang?: string; fromUrl?: string } = {}
): string | null {
  if (!quote || !quote.workId || quote.kind !== "canonical") return null;
  const qs = new URLSearchParams();
  if (quote.readPage) qs.set("page", String(quote.readPage));
  if (opts.lang) qs.set("lang", opts.lang);
  if (opts.fromUrl) qs.set("from", opts.fromUrl);
  const qStr = qs.toString();
  return `/read/${quote.workId}${qStr ? `?${qStr}` : ""}`;
}

/**
 * Attribution line pieces for a quote. LLM sometimes emits `location` that
 * repeats the work title or author verbatim ("Mysticism in Maharashtra"
 * as location for a MiM quote) — de-dupe against title/author so the
 * output reads "Title · Author" instead of "Title, Title · Author".
 *
 * Returns the individual pieces so callers can render them differently
 * (card variant wants a long "— Title, Location · Author" line; inline
 * variant wants a compact "Title · Location" as a link).
 */
export function buildAttribution(
  quote: Pick<Quote, "workTitle" | "location" | "author"> | undefined
): {
  title: string;
  location: string; // empty when redundant
  author: string;
} {
  if (!quote) return { title: "", location: "", author: "" };
  const author = authorDisplayName(quote.author);
  const title = (quote.workTitle ?? "").trim();
  const loc = (quote.location ?? "").trim();
  const norm = (s: string) => (s ?? "").toLowerCase().replace(/\s+/g, " ").trim();
  const nLoc = norm(loc);
  const locRedundant =
    !nLoc ||
    nLoc === norm(title) ||
    nLoc === norm(author) ||
    nLoc.startsWith(norm(title)) ||
    nLoc.includes(norm(author));
  return {
    title,
    location: locRedundant ? "" : loc,
    author,
  };
}

/**
 * Formatted card-variant attribution line ("— Title, Location · Author"
 * or "— Title · Author" if location is redundant). Preserves the shape
 * QuoteBlock's card variant used before the refactor.
 */
export function formatCardAttribution(
  quote: Pick<Quote, "workTitle" | "location" | "author"> | undefined
): string {
  const { title, location, author } = buildAttribution(quote);
  if (location) return `— ${title}, ${location} · ${author}`;
  return `— ${title} · ${author}`;
}

/**
 * Compact inline-variant attribution ("Title · Location" or just "Title").
 * Used as the visible text of the "Read in full" link in the woven-prose
 * layout — the author already appears in the surrounding narrative.
 */
export function formatInlineAttribution(
  quote: Pick<Quote, "workTitle" | "location" | "author"> | undefined
): string {
  const { title, location } = buildAttribution(quote);
  if (location) return `${title} · ${location}`;
  return title;
}

/**
 * Strip a redundant leading `"Paraphrase:"` / `"Translation:"` / `"Gloss:"`
 * label from the paraphrase field. Some LLM outputs prefix the paraphrase
 * with that label — it renders as visual noise since the paraphrase's
 * position + style already say it's a gloss.
 */
export function cleanParaphrase(raw: string | undefined | null): string {
  if (!raw) return "";
  return raw.replace(/^\s*(paraphrase|translation|gloss)\s*[:\-—]\s*/i, "").trim();
}
