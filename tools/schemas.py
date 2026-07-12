"""
Structured-output contract for the Gurudev Sangrah backend.

This module is the single source of truth for the response shape returned
by `POST /ask`. The chat-app's `lib/api.ts` `AskResponse` mirrors these
pydantic models — keep the two in sync.

Each mode (qa / pravachan / reading) has:
  - a pydantic model (for validation + serialization)
  - a JSON-schema dict (passed to the Anthropic SDK as a tool `input_schema`)
  - a tool definition that wraps the JSON schema

The LLM is forced to emit its response via the tool. The tool's `input`
block is parsed back into the pydantic model. See ADR-011 for the
rationale (and for why we use tool-use rather than `messages.parse()` —
the Python 3.8 / anthropic 0.72 environment cannot run the newer SDK).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Chunk-leakage scrubber (defensive post-process safety net)
#
# Despite system-prompt rules and hiding chunk numbers from the LLM input,
# we still scrub every user-facing string field as a belt-and-braces step.
# The regex matches "chunk" / "chunks" followed by a digit (so phrases like
# "chunks of bread" pass through untouched), optionally with a second number
# joined by "and", "&", a comma, an en/em-dash, "-", or "to".
# ---------------------------------------------------------------------------

_CHUNK_LEAK_RE = re.compile(
    r"\bchunks?\s+\d+(?:\s*(?:and|to|&|,|–|—|-)\s*\d+)?\b",
    flags=re.IGNORECASE,
)


def _scrub_chunk_leak(s: Optional[str]) -> Optional[str]:
    """Strip 'chunk N' / 'chunks N and M' patterns; normalize leftover whitespace.

    Returns None if input is None (so Optional fields stay Optional). Returns
    "" if the entire input was a chunk reference. Trailing/leading commas,
    semicolons, and parenthesis-fragments left dangling after removal are
    cleaned up. Leaves text with no chunk-pattern unchanged.
    """
    if s is None:
        return None
    if not isinstance(s, str):
        return s
    if not _CHUNK_LEAK_RE.search(s):
        return s
    out = _CHUNK_LEAK_RE.sub("", s)
    # Collapse double spaces and clean up orphan punctuation that the removal
    # left behind: ", , " → ", "; " , " → " "; trailing " ," → ""; etc.
    out = re.sub(r"\s+", " ", out)
    out = re.sub(r"\s*,\s*,+", ",", out)
    out = re.sub(r"\(\s*,", "(", out)
    out = re.sub(r",\s*\)", ")", out)
    out = re.sub(r"\(\s*\)", "", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = out.strip().strip(",;").strip()
    return out


def _scrub_list_of_strings(xs: Optional[List[str]]) -> Optional[List[str]]:
    if xs is None:
        return None
    return [s for s in (_scrub_chunk_leak(x) for x in xs) if s]


# ---------------------------------------------------------------------------
# Shared pieces — Quote, Citation, Reference
# ---------------------------------------------------------------------------


class Quote(BaseModel):
    """A verbatim passage with its attribution.

    Mirrors `Quote` in chat-app/lib/api.ts. `paraphrase` is optional and
    is used when the quote's language differs from the user's (the LLM
    supplies a brief gloss labelled as a paraphrase so the user can read
    the gist without losing the verbatim source).

    `workId` is server-filled (NOT model-writable): the backend splices it
    in from the chunk's `meta.work_id` so the frontend can build a
    "Read in full" link for canonical works. It is always "" for non-canonical
    kinds (athvani / biography) and for quotes that had no matching chunk.
    """

    body: str
    workTitle: str
    location: str
    kind: Literal["canonical", "athvani", "biography"]
    author: str
    paraphrase: Optional[str] = None
    workId: Optional[str] = ""
    # The model-emitted reference letter (A, B, …) identifying which retrieved
    # passage this quote came from. Kept on the model (not stripped at validation)
    # so the server can map a citation back to its chunk AFTER validation to fill
    # readPage on the final `done` response — otherwise the "Read in full" deep
    # link loses its page. Not used by the frontend.
    passage: Optional[str] = None
    # Server-filled: 1-based page in the reading surface where the cited passage
    # appears. Only set for canonical quotes with a resolved chunk offset. None
    # (excluded from serialisation via exclude_none) when unresolvable.
    readPage: Optional[int] = None

    @model_validator(mode="after")
    def _scrub(self) -> "Quote":
        # `body` is verbatim source text and is NOT scrubbed (to avoid
        # mangling legitimate quoted material). All other fields are LLM
        # prose where "chunks 7 and 8" can only be a leak.
        self.workTitle = _scrub_chunk_leak(self.workTitle) or ""
        self.location = _scrub_chunk_leak(self.location) or ""
        self.author = _scrub_chunk_leak(self.author) or ""
        self.paraphrase = _scrub_chunk_leak(self.paraphrase)
        # workId is server-filled and never contains user-facing prose —
        # no scrubbing needed (and the chunk-leak regex would mangle IDs).
        return self


class Citation(BaseModel):
    """A quote plus a one-line rationale explaining why it was chosen."""

    quote: Quote
    whyChosen: str

    @model_validator(mode="after")
    def _scrub(self) -> "Citation":
        self.whyChosen = _scrub_chunk_leak(self.whyChosen) or ""
        return self


class Reference(BaseModel):
    """A work the answer drew on without quoting verbatim (meta-mode Q&A)."""

    workTitle: str
    location: Optional[str] = None
    author: Optional[str] = None

    @model_validator(mode="after")
    def _scrub(self) -> "Reference":
        self.workTitle = _scrub_chunk_leak(self.workTitle) or ""
        self.location = _scrub_chunk_leak(self.location)
        self.author = _scrub_chunk_leak(self.author)
        return self


# ---------------------------------------------------------------------------
# Q&A response — unified quote-and-synthesize (ADR-010 superseded 2026-07-08)
# ---------------------------------------------------------------------------


class QAResponse(BaseModel):
    kind: Literal["qa"] = "qa"
    # `classification` is now optional — kept as an audit hint only.
    # The doctrinal/meta branch logic was removed (ADR-010 reversal, 2026-07-08).
    # The frontend branches on citations.length, not on this field.
    classification: Optional[Literal["doctrinal", "meta"]] = "doctrinal"
    question: str
    # Defaults to "" so a (meta) answer that uses `framingParagraphs` instead of
    # `framing` doesn't fail pydantic's "field required" before the validator
    # below (which enforces that at least one of the two is present) can run.
    framing: str = ""
    # Optional paragraph array for longer meta answers. LLMs reliably emit
    # JSON arrays but unreliably emit literal "\n\n" inside JSON strings, so
    # we let the model choose: short answer → `framing`; longer answer →
    # `framingParagraphs`. The UI prefers the array when present.
    framingParagraphs: Optional[List[str]] = None
    citations: List[Citation] = Field(default_factory=list)
    references: Optional[List[Reference]] = None
    synthesis: Optional[str] = None

    @model_validator(mode="after")
    def _scrub_and_check(self) -> "QAResponse":
        self.framing = _scrub_chunk_leak(self.framing) or ""
        self.framingParagraphs = _scrub_list_of_strings(self.framingParagraphs)
        self.synthesis = _scrub_chunk_leak(self.synthesis)
        # Enforce: either `framing` is non-empty OR `framingParagraphs` has
        # at least one element. After scrubbing, an entirely-leaked framing
        # could land empty; require the model to give us something.
        if not self.framing and not (self.framingParagraphs and len(self.framingParagraphs) > 0):
            raise ValueError(
                "QAResponse requires either `framing` (non-empty) or `framingParagraphs` (non-empty list)."
            )
        return self


# ---------------------------------------------------------------------------
# Pravachan response
# ---------------------------------------------------------------------------


class PravachanExample(BaseModel):
    title: str
    gloss: Optional[str] = None
    quote: Quote
    whyThisExample: str
    readSlug: Optional[str] = None

    @model_validator(mode="after")
    def _scrub(self) -> "PravachanExample":
        self.title = _scrub_chunk_leak(self.title) or ""
        self.gloss = _scrub_chunk_leak(self.gloss)
        self.whyThisExample = _scrub_chunk_leak(self.whyThisExample) or ""
        return self


class PravachanResponse(BaseModel):
    kind: Literal["pravachan"] = "pravachan"
    question: str
    thesis: Optional[str] = None
    gurudevsWords: Optional[Quote] = None
    examples: List[PravachanExample] = Field(default_factory=list)

    @model_validator(mode="after")
    def _scrub(self) -> "PravachanResponse":
        self.thesis = _scrub_chunk_leak(self.thesis)
        return self


# ---------------------------------------------------------------------------
# Reading response
# ---------------------------------------------------------------------------


class ReadingAttribution(BaseModel):
    workTitle: str
    chapter: str
    author: str

    @model_validator(mode="after")
    def _scrub(self) -> "ReadingAttribution":
        self.workTitle = _scrub_chunk_leak(self.workTitle) or ""
        self.chapter = _scrub_chunk_leak(self.chapter) or ""
        self.author = _scrub_chunk_leak(self.author) or ""
        return self


class ReadingResponse(BaseModel):
    kind: Literal["reading"] = "reading"
    question: str
    framing: str
    passage: str
    attribution: ReadingAttribution

    @model_validator(mode="after")
    def _scrub(self) -> "ReadingResponse":
        # `passage` is verbatim source text → not scrubbed.
        self.framing = _scrub_chunk_leak(self.framing) or ""
        return self


# ---------------------------------------------------------------------------
# JSON schemas (input_schema for Anthropic tool definitions)
#
# These are intentionally hand-written rather than derived from
# pydantic's `model_json_schema()` — the SDK expects a tight, explicit
# JSON-Schema dict, and editing it directly keeps the contract visible
# in this file.
# ---------------------------------------------------------------------------


# Inner shapes reused across modes.
_QUOTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "body": {"type": "string", "description": "Verbatim text from the source."},
        "workTitle": {"type": "string"},
        "location": {
            "type": "string",
            "description": (
                "Human-readable location in the work — chapter, page, section, "
                "paragraph, letter number, or athvani section heading. Leave as "
                "empty string if no natural locator is available. Never use an "
                "internal retrieval identifier here."
            ),
        },
        "kind": {"type": "string", "enum": ["canonical", "athvani", "biography"]},
        "author": {"type": "string"},
        "paraphrase": {
            "type": "string",
            "description": (
                "Optional short gloss in the user's language when the quote is "
                "in a different language. Clearly a paraphrase, not the source."
            ),
        },
    },
    "required": ["body", "workTitle", "location", "kind", "author"],
}

# Q&A citations quote BY REFERENCE (latency fix — see
# docs/PLAN-reference-and-splice-citations.md). Instead of retyping the full
# verbatim passage (which made the model stall for ~10-25s mid-stream), the
# model names the passage LETTER and short start/end anchors; the backend
# splices in the real `body` and authoritative attribution from the chunk.
_QA_CITATION_QUOTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "passage": {
            "type": "string",
            "description": (
                "The single passage LETTER (e.g. \"A\", \"B\", \"C\") from "
                "<retrieved_passages> that this quote is taken from. Exactly one label."
            ),
        },
        "quoteStart": {
            "type": "string",
            "description": (
                "The FIRST few words (about 4-8) of the verbatim quote, copied "
                "EXACTLY — character for character — from that passage's TEXT. "
                "Do NOT paraphrase or translate. Marks where the quote begins."
            ),
        },
        "quoteEnd": {
            "type": "string",
            "description": (
                "The LAST few words (about 4-8) of the verbatim quote, copied "
                "EXACTLY from that passage's TEXT, occurring after quoteStart. "
                "Marks where the quote ends. For a very short quote it may equal "
                "quoteStart. Do NOT retype the whole passage."
            ),
        },
        "location": {
            "type": "string",
            "description": (
                "Human-readable location in the work — chapter, page, section, "
                "paragraph, letter number, or athvani section heading. Leave as "
                "empty string if no natural locator is available. Never use an "
                "internal retrieval identifier here."
            ),
        },
        "paraphrase": {
            "type": "string",
            "description": (
                "Optional short gloss in the user's language when the quote is "
                "in a different language. Clearly a paraphrase, not the source."
            ),
        },
    },
    "required": ["passage", "quoteStart", "quoteEnd", "location"],
}

_CITATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "quote": _QA_CITATION_QUOTE_SCHEMA,
        "whyChosen": {
            "type": "string",
            "description": "One sentence in the user's language explaining why this passage answers the question.",
        },
    },
    "required": ["quote", "whyChosen"],
}

_REFERENCE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "workTitle": {"type": "string"},
        "location": {"type": "string"},
        "author": {"type": "string"},
    },
    "required": ["workTitle"],
}

QA_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["doctrinal", "meta"],
            "description": (
                "Optional audit hint — omit or set to 'doctrinal' for most answers. "
                "The doctrinal/meta branch was removed (ADR-010 reversal 2026-07-08); "
                "the frontend branches on citations.length, not on this field."
            ),
        },
        "question": {
            "type": "string",
            "description": "The user's question, echoed verbatim.",
        },
        "framing": {
            "type": "string",
            "description": (
                "An INTRODUCTORY PARAGRAPH (2-4 sentences) that frames the question and "
                "previews what the literature holds. Not a bare label like 'Here is what "
                "the literature says'; actually introduce the topic. Keep it to one paragraph. "
                "For SHORT answers (one paragraph, <=4 sentences): the full prose answer as a "
                "single paragraph. For LONGER answers (multiple paragraphs): leave this as an "
                "empty string and use `framingParagraphs` instead. "
                "Do NOT include literal newline sequences (\\n\\n) inside this string."
            ),
        },
        "framingParagraphs": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "For answers that need multiple paragraphs. One element per paragraph "
                "(~3-5 sentences each). When you use this field, leave `framing` empty. The UI "
                "renders each element as a separate <p>. Do NOT include literal newline sequences "
                "inside a paragraph string."
            ),
        },
        "citations": {
            "type": "array",
            "items": _CITATION_SCHEMA,
            "description": (
                "Between 3 and 5 citations — choose the STRONGEST; quality over quantity. "
                "NEVER exceed 5: a longer list crowds out the concluding `synthesis` and slows "
                "the answer. Never pad with weak passages. "
                "Quote each passage BY REFERENCE — give the passage letter plus the exact "
                "start/end words of the span you want; do NOT retype the full passage text. "
                "For navigational or biographical questions with no quotable passage, an "
                "empty array is fine — answer in framing/framingParagraphs with references."
            ),
        },
        "references": {
            "type": "array",
            "items": _REFERENCE_SCHEMA,
            "description": (
                "Works the answer drew on without quoting verbatim — biographies, bibliographies, "
                "indexes, navigational works, and any other source synthesized in prose. List ALL "
                "relevant works; omitting works that were drawn on is an error."
            ),
        },
        "synthesis": {
            "type": "string",
            "description": (
                "A CONCLUDING PARAGRAPH (1-3 sentences) that ties the cited passages together "
                "into a coherent takeaway. REQUIRED whenever you have 1 or more citations — "
                "always write it; it must never be omitted. Budget for it: keep to at most 5 "
                "citations so this closing paragraph always fits. "
                "Omit it ONLY when the answer is entirely prose with no citations."
            ),
        },
    },
    "required": ["question", "framing", "citations"],
}


# ---------------------------------------------------------------------------
# Reference-and-splice for Q&A citations
# (latency fix — see docs/PLAN-reference-and-splice-citations.md)
#
# The model emits each doctrinal quote by reference (passage letter + short
# verbatim start/end anchors) rather than retyping the passage. These helpers
# splice the real `body` (and authoritative attribution from the chunk's
# metadata) back into the quote dict, producing the same wire `Quote` shape the
# frontend already consumes. Operates on raw dicts, in place, before pydantic
# validation — so the parsed `Quote` always has a populated `body`.
# ---------------------------------------------------------------------------

_ALLOWED_KINDS = {"canonical", "athvani", "biography"}


# ---------------------------------------------------------------------------
# Length-preserving diacritic fold
#
# Maps each character to its base letter by NFKD-decomposing and stripping
# combining marks, BUT preserves the original character if the result would
# change the string's length (one char → one char is required so that match
# offsets in the folded form correspond exactly to offsets in the original).
# Examples: â → a, ā → a, ñ → n, é → e.  Characters whose NFKD expansion
# would be multi-char or whose base is still non-ASCII but not a letter are
# kept as-is so the fold is length-neutral.  Whitespace and punctuation are
# NOT collapsed here — anchor regex handles whitespace tolerance separately.
# ---------------------------------------------------------------------------

def _fold_char(ch: str) -> str:
    """Return the ASCII base letter for a single diacritic character, or the
    character itself if no length-preserving fold is possible."""
    nfkd = unicodedata.normalize("NFKD", ch)
    # Strip combining marks (category "Mn" = Mark, Nonspacing).
    base = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    # Keep fold only when it's exactly one ASCII letter (preserves length).
    if len(base) == 1 and base.isascii() and base.isalpha():
        return base
    return ch


def _fold_text(text: str) -> str:
    """Fold `text` character-by-character; result has exactly len(text) chars
    so that span offsets align between the folded and original strings."""
    return "".join(_fold_char(c) for c in text)


def _anchor_tokens(anchor: str) -> List[str]:
    """Word-run tokens of an anchor (punctuation dropped, Unicode-aware)."""
    return re.findall(r"\w+", anchor or "", re.UNICODE)


def _anchor_regex(anchor: str):
    """Regex matching the anchor's WORDS in the source, tolerant of any
    punctuation/whitespace differences (attached or between words). Built from
    word-runs only, so e.g. an end anchor "amirasa." still matches a source
    "amirasa," — the common cause of mismatches in OCR'd text."""
    toks = _anchor_tokens(anchor)
    if not toks:
        return None
    # `\W+` between tokens = one or more non-word chars (space, newline, punct).
    return re.compile(r"\W+".join(re.escape(t) for t in toks))


def _folded_anchor_regex(anchor: str):
    """Like _anchor_regex but operates in the diacritic-folded domain.

    The anchor itself is folded (so ā→a) and the regex is built from its
    folded tokens. Because _fold_text is length-preserving, match offsets
    in the folded text translate directly to offsets in the original text.
    Falls back gracefully to None when the anchor has no word tokens."""
    folded_anchor = _fold_text(anchor or "")
    return _anchor_regex(folded_anchor)


# A sentence/paragraph boundary: terminal punctuation (incl. the Devanagari
# danda) with optional closing quote, followed by whitespace/end — or a blank line.
_BOUNDARY = re.compile(r"[।.!?][\"'’”\)\]]?(?=\s|$)|\n\s*\n")


def _to_boundary(text: str, start: int, after: int) -> str:
    """Verbatim text from `start` to the next sentence/paragraph boundary at or
    after `after` (else to the end of the chunk). Used when the start anchor
    matched but the end anchor did not — far better than a stub."""
    m = _BOUNDARY.search(text, after)
    end = m.end() if m else len(text)
    return text[start:end].strip()


def _splice_span(text: str, start: str, end: str) -> Optional[str]:
    """Verbatim substring of `text` from the start anchor through the end anchor,
    tolerant of punctuation/whitespace AND diacritics/spelling variations.

    Strategy:
    1. Try an exact (word-tolerant) anchor match in the original text.
    2. If that fails, fold both the text and the anchor to their ASCII base
       letters (length-preserving) and repeat the search.  Offsets from the
       folded match are used to slice from the ORIGINAL text so the returned
       body is byte-for-byte the real source (original diacritics intact).
    Returns None only if the START anchor can't be located by either method;
    a missing END anchor falls back to a sentence boundary."""
    sr = _anchor_regex(start)
    sm = sr.search(text) if sr else None

    if sm is None:
        # Diacritic-tolerant retry: search in the folded text.
        folded_text = _fold_text(text)
        fsr = _folded_anchor_regex(start)
        sm = fsr.search(folded_text) if fsr else None
        if sm is None:
            return None
        # sm offsets are in folded_text space == original text space (length-preserved).
        start_toks = _anchor_tokens(_fold_text(start))
        end_toks = _anchor_tokens(_fold_text(end))
        if not end_toks or end_toks == start_toks:
            return text[sm.start(): sm.end()].strip()
        fer = _folded_anchor_regex(end)
        em = fer.search(folded_text, sm.end()) if fer else None
        if em:
            return text[sm.start(): em.end()].strip()
        return _to_boundary(text, sm.start(), sm.end())

    start_toks = _anchor_tokens(start)
    end_toks = _anchor_tokens(end)
    # Short quote: end omitted or same words as start -> span is the start match.
    if not end_toks or end_toks == start_toks:
        return text[sm.start(): sm.end()].strip()
    er = _anchor_regex(end)
    em = er.search(text, sm.end()) if er else None
    if em:
        return text[sm.start(): em.end()].strip()
    # End anchor not found: extend from the start match to a sentence boundary.
    return _to_boundary(text, sm.start(), sm.end())


def _degrade(start: str, end: str) -> str:
    start = (start or "").strip()
    end = (end or "").strip()
    if end and end != start:
        return f"{start} … {end}"
    return start


def clean_quote_body(text: str) -> str:
    """Strip invisible scan/encoding junk from a verbatim quote body.

    Character-level ONLY (garble verifier, Phase 1): drops C0/C1 control chars
    (keeping tab/newline/CR), the zero-width space (U+200B) and BOM (U+FEFF), and
    turns the Unicode replacement char (U+FFFD, which stood for an undecodable
    byte) into a space so adjacent words don't merge. It does NOT attempt
    word-level OCR correction (e.g. "Tne"->"The"), which would fabricate the
    source — those go to the human flag (Phase 2). U+200C/U+200D (ZWNJ/ZWJ) are
    KEPT because they are meaningful in Devanagari. Clean text returns unchanged.
    """
    if not text:
        return text
    out = []
    for ch in text:
        cp = ord(ch)
        if cp == 0xFFFD:                        # replacement char -> space
            out.append(" ")
        elif cp in (0x200B, 0xFEFF):            # ZWSP, BOM -> drop
            continue
        elif cp in (0x09, 0x0A, 0x0D):          # tab, newline, CR -> keep
            out.append(ch)
        elif cp < 0x20 or 0x7F <= cp <= 0x9F:   # other C0/C1 controls -> drop
            continue
        else:
            out.append(ch)
    return "".join(out)


def splice_quote_dict(quote: Dict[str, Any], label_to_chunk: Dict[str, Any]) -> bool:
    """Fill body/workTitle/kind/author on a reference quote, in place.

    Returns True if the verbatim body was spliced cleanly, False if it degraded
    (unknown passage or anchor mismatch) or there was nothing to splice.

    When the quote carries a reference (`passage`/`quoteStart`/`quoteEnd`), the
    spliced text from the chunk ALWAYS overrides any `body` the model emitted —
    non-strict tool use sometimes still fills `body`, and trusting that would
    defeat the whole point (faithful, byte-identical quotes). Only a quote with
    NO reference at all (other modes / legacy shape) keeps its model `body`.
    """
    if not isinstance(quote, dict):
        return False

    passage = (quote.get("passage") or "").strip()
    start = quote.get("quoteStart") or ""
    end = quote.get("quoteEnd") or ""
    model_body = quote.get("body") or ""
    has_ref = bool(passage or start or end)

    if not has_ref:
        # Genuine verbatim body (pravachan/reading/legacy) — leave it untouched.
        result = bool(model_body)
    else:
        chunk = (label_to_chunk or {}).get(passage)
        if chunk is None:
            # Unknown passage letter: can't splice. Use the model's own body if
            # it gave one; otherwise leave body absent (no stub — the caller will
            # handle a missing body rather than showing a broken ellipsis citation).
            if not model_body:
                pass  # body stays absent; do NOT emit a stub
            quote.setdefault("workTitle", "")
            quote.setdefault("author", "")
            quote.setdefault("location", "")
            if quote.get("kind") not in _ALLOWED_KINDS:
                quote["kind"] = "canonical"
            result = False
        else:
            meta = chunk.get("meta") or {}
            text = chunk.get("text") or ""
            body = _splice_span(text, start, end)
            ok = body is not None
            # Spliced text wins over any model-emitted body. On a start-anchor
            # miss (ok is False) use the full source chunk as the body rather
            # than a degraded "start … end" stub — the user always sees real
            # verbatim text, never a broken ellipsis citation.
            if ok:
                quote["body"] = body
            else:
                # Full-passage fallback: show the whole chunk, cleaned.
                quote["body"] = clean_quote_body(text) if text else (model_body or "")
            # Authoritative attribution from the chunk's metadata.
            quote["workTitle"] = meta.get("title") or meta.get("work_id") or quote.get("workTitle") or ""
            quote["author"] = meta.get("author") or quote.get("author") or ""
            mkind = meta.get("kind")
            if mkind in _ALLOWED_KINDS:
                quote["kind"] = mkind
            elif quote.get("kind") not in _ALLOWED_KINDS:
                quote["kind"] = "canonical"
            quote.setdefault("location", "")
            # Server-fills workId so the frontend can build a "Read in full"
            # link for canonical works. Only set for canonical kind; leave ""
            # for athvani/biography (those don't have a dedicated reader URL).
            if quote.get("kind") == "canonical":
                quote["workId"] = meta.get("work_id") or ""
            else:
                quote["workId"] = ""
            result = ok

    # Garble verifier (Phase 1): strip invisible scan/encoding junk from the
    # final verbatim body. Character-level only — no word-level OCR guessing.
    if quote.get("body"):
        quote["body"] = clean_quote_body(quote["body"])
    return result


def splice_qa_citations(tool_input: Dict[str, Any], label_to_chunk: Dict[str, Any]) -> int:
    """Splice every citation quote in a QA tool-input dict, in place.

    Returns the number of citations that degraded (anchor mismatch / unknown
    passage) — for diagnostics. Safe to call on meta answers (no citations).
    """
    degraded = 0
    cits = tool_input.get("citations")
    if isinstance(cits, list):
        kept = []
        for c in cits:
            if isinstance(c, dict) and isinstance(c.get("quote"), dict):
                if not splice_quote_dict(c["quote"], label_to_chunk):
                    degraded += 1
                # Drop a citation left with no usable verbatim body (e.g. the
                # model referenced an unknown passage letter and the full-passage
                # fallback had nothing to supply). Omitting it is better than
                # failing Quote validation on a missing body or rendering blank.
                if not (c["quote"].get("body") or "").strip():
                    continue
            kept.append(c)
        tool_input["citations"] = kept
    return degraded


_PRAVACHAN_EXAMPLE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Short title or theme for this story, in the user's language.",
        },
        "gloss": {
            "type": "string",
            "description": "Optional one-line gloss when the athvani is too long to quote in full.",
        },
        "quote": _QUOTE_SCHEMA,
        "whyThisExample": {
            "type": "string",
            "description": "One sentence in the user's language linking the story to the thesis.",
        },
        "readSlug": {
            "type": "string",
            "description": "Optional read-in-full slug; omit if unknown.",
        },
    },
    "required": ["title", "quote", "whyThisExample"],
}

PRAVACHAN_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "The user's topic/question, echoed verbatim.",
        },
        "thesis": {
            "type": "string",
            "description": (
                "1-2 sentences in the user's language naming the central teaching. "
                "Omit for athvani-collection questions."
            ),
        },
        "gurudevsWords": dict(
            _QUOTE_SCHEMA,
            description="ONE canonical passage that grounds the thesis. Omit for athvani-collection questions.",
        ),
        "examples": {
            "type": "array",
            "items": _PRAVACHAN_EXAMPLE_SCHEMA,
            "description": "3-5 athvani that illustrate the thesis.",
        },
    },
    "required": ["question", "examples"],
}

READING_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "framing": {
            "type": "string",
            "description": "Short framing sentence in the user's language acknowledging what they're reading.",
        },
        "passage": {
            "type": "string",
            "description": "The most relevant verbatim passage answering the inline question.",
        },
        "attribution": {
            "type": "object",
            "properties": {
                "workTitle": {"type": "string"},
                "chapter": {"type": "string"},
                "author": {"type": "string"},
            },
            "required": ["workTitle", "chapter", "author"],
        },
    },
    "required": ["question", "framing", "passage", "attribution"],
}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


TOOLS_BY_MODE: Dict[str, Dict[str, Any]] = {
    "qa": {
        "name": "emit_qa_response",
        "description": (
            "Emit the structured Q&A answer. Every answer may include citations, "
            "framingParagraphs, synthesis, and references in any combination — "
            "the doctrinal/meta split was removed (ADR-010 reversal 2026-07-08)."
        ),
        "input_schema": QA_INPUT_SCHEMA,
    },
    "pravachan": {
        "name": "emit_pravachan_response",
        "description": (
            "Emit the structured pravachan research brief. Thematic questions "
            "include thesis + gurudevsWords + examples; athvani-collection "
            "questions omit thesis and gurudevsWords."
        ),
        "input_schema": PRAVACHAN_INPUT_SCHEMA,
    },
    "reading": {
        "name": "emit_reading_response",
        "description": (
            "Emit the structured inline-reading answer. Keep it short and "
            "scoped to the current passage."
        ),
        "input_schema": READING_INPUT_SCHEMA,
    },
}


RESPONSE_MODEL_BY_MODE: Dict[str, Any] = {
    "qa": QAResponse,
    "pravachan": PravachanResponse,
    "reading": ReadingResponse,
}


def get_tool(mode: str) -> Dict[str, Any]:
    if mode not in TOOLS_BY_MODE:
        raise ValueError(f"Unknown mode {mode!r}. Choose from: {sorted(TOOLS_BY_MODE)}")
    return TOOLS_BY_MODE[mode]


def get_response_model(mode: str):
    if mode not in RESPONSE_MODEL_BY_MODE:
        raise ValueError(f"Unknown mode {mode!r}. Choose from: {sorted(RESPONSE_MODEL_BY_MODE)}")
    return RESPONSE_MODEL_BY_MODE[mode]
