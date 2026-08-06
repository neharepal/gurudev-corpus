// RFC-023 — helpers for the Sources footer of a Reading-mode Q&A answer.
//
// These are the shared pieces between the ReadingQaAnswer component and any
// future surface that wants to render a passage-link with the U2 fix (same-
// slug nav closes the drawer, cross-slug nav is a plain jump). Kept as pure
// functions (no React) so they're trivially unit-tested.

import type { PassageLink } from "../data/mock-conversations";

export type Lang = "en" | "mr";

/**
 * Build the `/read/<workSlug>?page=N&lang=<lang>` href for a passage link.
 *
 * The `?page=` value is the BACKEND page number — the reader route treats it
 * that way and translates to displayed page numbering when a TOC page is
 * injected. That is intentional and consistent with citation deep links from
 * the QA surface (see chat-app/components/QuoteBlock.tsx).
 */
export function buildReadingLinkHref(
  link: Pick<PassageLink, "workSlug" | "page">,
  opts: { lang: Lang },
): string {
  const params = new URLSearchParams();
  params.set("page", String(link.page));
  params.set("lang", opts.lang);
  return `/read/${link.workSlug}?${params.toString()}`;
}

/**
 * True when the link points into the currently-open book — the same slug the
 * reader is already viewing. Callers use this to gate the U2 fix: on same-
 * slug nav the drawer must close (soft-nav under the still-open drawer would
 * leave nothing visibly changing).
 */
export function isSameSlug(
  link: Pick<PassageLink, "workSlug">,
  currentSlug: string,
): boolean {
  if (!link?.workSlug || !currentSlug) return false;
  return link.workSlug === currentSlug;
}
