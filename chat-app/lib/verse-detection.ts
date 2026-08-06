/**
 * Heuristic detection of foreign-script verse/quotation paragraphs
 * embedded inside English commentary. Applied to Sanskrit shlokas
 * (Devanagari, e.g. Iśopaniṣad 2 in BGPGR Ch I), Ancient Greek
 * quotations (Plotinus Enneads in MiM/BGPGR), and Bengali/Gujarati/
 * Tamil passages Ranade cites verbatim.
 *
 * Rule: the paragraph's non-whitespace characters must be ≥ threshold
 * (default 0.5) non-Latin-alphabet characters (Devanagari, Bengali,
 * Gujarati, Tamil, or Greek — including polytonic Greek Extended),
 * AND stripped length must be ≥ 6, AND we must be in an English-book
 * context (`isMarathi` = false, because Marathi books are ~100%
 * Devanagari body prose and would trip the threshold everywhere).
 *
 * Latin passages (Church Father quotations in Latin script) can't be
 * distinguished from English commentary by script alone; those need a
 * different signal (font-style, quote marks, or upstream tagging).
 */
const INDIC_RE = /[ऀ-ॿঀ-৿઀-૿஀-௿Ͱ-Ͽἀ-῿]/gu;
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


// --- Embedded verse-run extraction ---
// Ranade often puts a Greek (Plotinus, Enneads) or Sanskrit shloka INSIDE
// a longer English commentary paragraph, so per-paragraph detection misses
// them (majority-English). `splitVerseBlocks` finds the RUNs of foreign
// text and returns an ordered list of blocks so the reader can render the
// prose parts as <p> and the verse runs as boxed callouts.

export type VerseBlock = { type: "prose" | "verse"; text: string };

// A "foreign run" is a stretch of characters that starts and ends with an
// Indic/Greek char, and may include internal whitespace, ellipsis dots,
// and standard punctuation. This lets us grab a whole quotation including
// Ranade's `.....` prefix/suffix and internal grammar marks. The minimum
// run length filters out inline loanwords like `λόγος` mid-sentence.
const FOREIGN_START_END = "ऀ-ॿঀ-৿઀-૿஀-௿Ͱ-Ͽἀ-῿";
const CONNECTOR = "\\s.,;:!?'‘’\"“”()[\\]–—…·-";
const RUN_RE = new RegExp(
  `[${FOREIGN_START_END}][${CONNECTOR}${FOREIGN_START_END}]*[${FOREIGN_START_END}]`,
  "gu"
);

const MIN_RUN_LENGTH = 40;


// --- Verse citation extraction ---
// A shloka is typically closed with `॥` (pūrṇa-virāma / double daṇḍa) and
// followed by a short Latin-script reference like `XIII. 12-13.`,
// `Iśa. Up. 2.`, or `Enneads, VI. 9. 9-11.`. Split the tail off so the
// reader can render it on its own line beneath the verse.

const INDIC_ANY = /[ऀ-ॿঀ-৿઀-૿஀-௿Ͱ-Ͽἀ-῿]/gu;

export function splitVerseCitation(text: string): { verse: string; citation: string | null } {
  if (!text) return { verse: "", citation: null };
  const CITATION_MAX_LEN = 60;

  // Primary: split at the last `॥`, keep it with the verse.
  const lastDanda = text.lastIndexOf("॥");
  if (lastDanda > 0) {
    const tail = text.slice(lastDanda + 1).trim();
    // Tail must be non-Indic, non-empty, and short enough to plausibly be
    // a citation (chapter.verse ref or "Book, X. Y").
    if (
      tail.length > 0 &&
      tail.length <= CITATION_MAX_LEN &&
      !INDIC_ANY.test(tail)
    ) {
      // Reset regex state (INDIC_ANY has /g flag).
      INDIC_ANY.lastIndex = 0;
      return { verse: text.slice(0, lastDanda + 1).trim(), citation: tail };
    }
    INDIC_ANY.lastIndex = 0;
  }

  // Fallback: find the last Indic/Greek char and check if what follows
  // looks like a Latin citation (contains at least one digit OR a
  // period-separated reference like "Iśa. Up. 2.").
  INDIC_ANY.lastIndex = 0;
  let lastForeign = -1;
  let m: RegExpExecArray | null;
  while ((m = INDIC_ANY.exec(text)) !== null) {
    lastForeign = m.index;
  }
  INDIC_ANY.lastIndex = 0;
  if (lastForeign > 0 && lastForeign < text.length - 3) {
    const tail = text.slice(lastForeign + 1).trim();
    if (
      tail.length > 0 &&
      tail.length <= CITATION_MAX_LEN &&
      /^[\s.,;:()"'“”—–\-A-Za-zĀ-ž0-9]+$/.test(tail) &&
      /\d/.test(tail)
    ) {
      // Must look citation-ish: contains a digit AND the whole thing is
      // just Latin+punct. Rejects a trailing English sentence.
      return { verse: text.slice(0, lastForeign + 1).trim(), citation: tail };
    }
  }

  return { verse: text.trim(), citation: null };
}


// --- Sentence-continuation merge ---
// Surya OCR (and to a lesser extent typeset PDFs with mid-sentence page
// breaks) sometimes emit a single sentence as two adjacent paragraphs.
// Signals: previous paragraph ends with a non-terminator (letter, comma,
// semicolon, or hyphen); next paragraph starts with a lowercase letter.
// This is a purely presentational join — canonical text on disk is
// untouched.

export interface Paragraph {
  n: number;
  body: string;
  is_subheading?: boolean;
  // Verse-format book flags (server.VERSE_FORMAT_SLUGS — nityanemavali). Set
  // per-paragraph by the server; the reader renders `is_heading` as a
  // maroon serif chapter title and `is_verse` centered/bold via `.gd-verse`.
  is_heading?: boolean;
  heading_level?: 2 | 3 | number;
  is_verse?: boolean;
}

const TERMINATORS = ".!?\"'”’)}]";

export function mergeSentenceContinuations<P extends Paragraph>(paragraphs: P[]): P[] {
  if (!paragraphs || paragraphs.length === 0) return paragraphs;
  const out: P[] = [];
  for (const para of paragraphs) {
    const prev = out.length > 0 ? out[out.length - 1] : null;
    // Never merge across subheading / heading / verse boundaries. Verse
    // padas and section headings from verse-format books are structural —
    // Surya-style sentence-continuation joining doesn't apply to them
    // and would concatenate a pada into the next paragraph's prose.
    if (
      !prev ||
      prev.is_subheading ||
      para.is_subheading ||
      prev.is_heading ||
      para.is_heading ||
      prev.is_verse ||
      para.is_verse
    ) {
      out.push({ ...para });
      continue;
    }
    const prevTail = prev.body.replace(/\s+$/, "");
    const currHead = para.body.replace(/^\s+/, "");
    if (!prevTail || !currHead) {
      out.push({ ...para });
      continue;
    }
    const lastChar = prevTail[prevTail.length - 1];
    const firstChar = currHead[0];
    // Firm terminator on prev tail → new paragraph (no merge).
    if (TERMINATORS.includes(lastChar)) {
      out.push({ ...para });
      continue;
    }
    // Current starts with an uppercase Latin letter or number-marker → new
    // paragraph (Ranade's numbered sub-items `1. ...` etc.).
    if (/^[A-Z0-9(]/.test(firstChar)) {
      out.push({ ...para });
      continue;
    }
    // Merge: hyphenated word-break (`develop-` + `ment`) joins with no
    // space + drops the hyphen; otherwise join with a single space.
    let merged: string;
    if (prevTail.endsWith("-")) {
      merged = prevTail.slice(0, -1) + currHead;
    } else if (prevTail.endsWith("—") || prevTail.endsWith("–")) {
      merged = prevTail + currHead;
    } else {
      merged = prevTail + " " + currHead;
    }
    out[out.length - 1] = { ...prev, body: merged };
  }
  return out;
}

export function splitVerseBlocks(body: string, opts: IsVerseOptions = {}): VerseBlock[] {
  if (!body) return [];
  if (opts.isMarathi) return [{ type: "prose", text: body }];

  // Whole-paragraph verse takes precedence (majority foreign OR pure).
  if (isVerseParagraph(body, opts)) {
    return [{ type: "verse", text: body }];
  }

  const runs: { start: number; end: number }[] = [];
  RUN_RE.lastIndex = 0;
  for (let m; (m = RUN_RE.exec(body)); ) {
    const text = m[0];
    // Require the run to be substantial AND majority foreign — reject
    // short quotations like inline `(λόγος)`.
    const foreignChars = (text.match(INDIC_RE) || []).length;
    if (text.length >= MIN_RUN_LENGTH && foreignChars / text.length >= 0.5) {
      // Expand the run outward to swallow adjacent ellipsis dots + whitespace
      // that Ranade uses as quotation delimiters (`.....text.....`). Otherwise
      // those dot-only fragments render as leftover prose blocks around the
      // verse — visually noisy.
      let start = m.index;
      while (start > 0 && /[.·…\s]/.test(body[start - 1])) start--;
      let end = m.index + text.length;
      while (end < body.length && /[.·…\s]/.test(body[end])) end++;
      runs.push({ start, end });
    }
  }
  if (runs.length === 0) return [{ type: "prose", text: body }];

  const blocks: VerseBlock[] = [];
  let cursor = 0;
  for (const run of runs) {
    if (run.start > cursor) {
      const prefix = body.slice(cursor, run.start).trim();
      if (prefix) blocks.push({ type: "prose", text: prefix });
    }
    // Also swallow leading/trailing ellipsis-dot runs and whitespace on
    // the verse itself — cosmetically the frame doesn't need them.
    const verse = body.slice(run.start, run.end).trim();
    blocks.push({ type: "verse", text: verse });
    cursor = run.end;
  }
  if (cursor < body.length) {
    const suffix = body.slice(cursor).trim();
    if (suffix) blocks.push({ type: "prose", text: suffix });
  }
  return blocks;
}
