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
    """

    body: str
    workTitle: str
    location: str
    kind: Literal["canonical", "athvani", "biography"]
    author: str
    paraphrase: Optional[str] = None

    @model_validator(mode="after")
    def _scrub(self) -> "Quote":
        # `body` is verbatim source text and is NOT scrubbed (to avoid
        # mangling legitimate quoted material). All other fields are LLM
        # prose where "chunks 7 and 8" can only be a leak.
        self.workTitle = _scrub_chunk_leak(self.workTitle) or ""
        self.location = _scrub_chunk_leak(self.location) or ""
        self.author = _scrub_chunk_leak(self.author) or ""
        self.paraphrase = _scrub_chunk_leak(self.paraphrase)
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
# Q&A response — doctrinal or meta (ADR-010)
# ---------------------------------------------------------------------------


class QAResponse(BaseModel):
    kind: Literal["qa"] = "qa"
    classification: Literal["doctrinal", "meta"]
    question: str
    framing: str
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

_CITATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "quote": _QUOTE_SCHEMA,
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
            "description": "Classification of the question per ADR-010 — based on the SOURCES you cite, not on the question phrasing.",
        },
        "question": {
            "type": "string",
            "description": "The user's question, echoed verbatim.",
        },
        "framing": {
            "type": "string",
            "description": (
                "Doctrinal: a short framing sentence (e.g. 'Here is what the literature says on this:'). "
                "Meta SHORT (one paragraph, <=4 sentences): the full answer as a single paragraph. "
                "Meta LONGER (multiple paragraphs): leave this as an empty string and use `framingParagraphs` instead. "
                "Do NOT include literal newline sequences (\\n\\n) inside this string."
            ),
        },
        "framingParagraphs": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Meta only, for answers that need multiple paragraphs. One element per paragraph "
                "(~3-5 sentences each). When you use this field, leave `framing` empty. The UI "
                "renders each element as a separate <p>. Do NOT include literal newline sequences "
                "inside a paragraph string."
            ),
        },
        "citations": {
            "type": "array",
            "items": _CITATION_SCHEMA,
            "description": (
                "Doctrinal: 2-5 verbatim citations with rationales. "
                "Meta: empty array — meta mode does not quote."
            ),
        },
        "references": {
            "type": "array",
            "items": _REFERENCE_SCHEMA,
            "description": "Meta only — works the answer drew on without quoting. Omit or empty for doctrinal.",
        },
        "synthesis": {
            "type": "string",
            "description": "Doctrinal only — optional 1-2 sentence synthesis at the end.",
        },
    },
    "required": ["classification", "question", "framing", "citations"],
}

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
            "Emit the structured Q&A answer. Classification is per ADR-010 — "
            "based on the SOURCES you cite, not the question phrasing."
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
