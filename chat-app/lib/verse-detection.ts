/**
 * Heuristic detection of Indic-script verse paragraphs embedded inside
 * English commentary. Used by the reader to apply a lightweight
 * box treatment (dotted top/bottom rules, centered, font-deva) to
 * Sanskrit/Prakrit/Marathi/Bengali/Gujarati/Tamil quotations that
 * Ranade cites verbatim inside English prose (e.g. Iśopaniṣad 2 inside
 * BGPGR's Chapter I).
 *
 * Rule: the paragraph's non-whitespace characters must be ≥ threshold
 * (default 0.5) Indic characters, AND the stripped length must be
 * ≥ 6, AND we must be in an English-book context (`isMarathi` = false,
 * because Marathi books are ~100% Devanagari body prose and would
 * trip the threshold everywhere).
 */
const INDIC_RE = /[ऀ-ॿঀ-৿઀-૿஀-௿]/gu;
const DEFAULT_THRESHOLD = 0.5;
const MIN_STRIPPED_LENGTH = 6;

export interface IsVerseOptions {
  /**
   * If true, the reader is showing a Marathi/Devanagari book. Skip
   * detection entirely — body prose is expected to be Devanagari.
   */
  isMarathi?: boolean;
  /**
   * Fraction of non-whitespace chars that must be Indic to count as a
   * verse. Default 0.5 (50%).
   */
  threshold?: number;
}

export function isVerseParagraph(body: string, opts: IsVerseOptions = {}): boolean {
  if (opts.isMarathi) return false;
  if (!body) return false;
  const stripped = body.replace(/\s+/g, "");
  if (stripped.length < MIN_STRIPPED_LENGTH) return false;
  const indicChars = stripped.match(INDIC_RE) || [];
  const ratio = indicChars.length / stripped.length;
  return ratio >= (opts.threshold ?? DEFAULT_THRESHOLD);
}
