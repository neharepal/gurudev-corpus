"""
Partial-JSON decoder + SSE helpers for streaming `/ask` responses (RFC-010).

The Anthropic SDK's tool-use streaming emits `InputJSONDelta` events whose
`partial_json` fields are arbitrary slices of the JSON the model is producing
for the tool call's `input` object. The slices can land anywhere — mid-key,
mid-string, mid-UTF-8 codepoint — and we need to:

  1. Track when a top-level field's value has fully closed → emit `FieldEvent`
     (back-compat with phase 1).
  2. Track when an array element has fully closed → emit `ArrayItemEvent`
     (back-compat with phase 1).
  3. Pass through deltas for ANY active leaf string at ANY nesting depth, with
     the full dotted path so the UI can typewriter nested fields like
     `citations.0.quote.body` (phase 2).

The decoder is a stack-based state machine. Each frame on the stack represents
"I am at this nesting level"; the frame's `path` is the dotted path from the
root to the value currently being assembled. When a value's closing token is
read, the frame pops, the value lands in the parent (object's `values` dict
or array's `items` list), and — if the parent is the root — an event fires.

This is NOT a general JSON parser. It does the minimum needed for the shape
the LLM emits via tool-use: a top-level object whose fields may themselves
be strings, scalars, objects, or arrays of objects.

Per RFC-010 Open Question §1: we own this code; no external dependency on a
streaming-JSON library whose UTF-8 handling we cannot audit. Tradeoff
documented in the RFC.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterator, List, Optional, Union


# ---------------------------------------------------------------------------
# Event shapes the decoder emits
# ---------------------------------------------------------------------------

@dataclass
class FieldEvent:
    """A top-level field's value has fully decoded.

    Phase-1 back-compat: `name` is the top-level field name (not a dotted path).
    For nested values, callers rely on `DeltaEvent` path plus the final `done`
    event to reconcile.
    """
    name: str
    value: Any


@dataclass
class ArrayItemEvent:
    """An element of a TOP-LEVEL array field has fully decoded."""
    array: str
    index: int
    value: Any


@dataclass
class DeltaEvent:
    """A chunk of text appended to the currently-active leaf string.

    Phase 2: `path` is the full dotted path from root, including object keys
    and array indices, e.g. "framing", "synthesis", "citations.0.quote.body",
    "examples.2.title". The React side accumulates into the matching slot of
    its progressive draft.
    """
    path: str
    text: str


Event = Union[FieldEvent, ArrayItemEvent, DeltaEvent]


# ---------------------------------------------------------------------------
# Stack frames
# ---------------------------------------------------------------------------

@dataclass
class _ObjectFrame:
    path: List[Union[str, int]]
    state: str = "EXPECT_KEY"  # EXPECT_KEY | IN_KEY | AFTER_KEY | EXPECT_VALUE | AFTER_VALUE
    current_key: Optional[str] = None
    key_escape: bool = False
    values: dict = dc_field(default_factory=dict)


@dataclass
class _ArrayFrame:
    path: List[Union[str, int]]
    state: str = "EXPECT_ELEMENT_OR_CLOSE"  # EXPECT_ELEMENT_OR_CLOSE | AFTER_ELEMENT
    current_index: int = 0
    items: list = dc_field(default_factory=list)


@dataclass
class _StringFrame:
    path: List[Union[str, int]]
    buf: str = ""
    escape: bool = False


@dataclass
class _ScalarFrame:
    path: List[Union[str, int]]
    buf: str = ""


_Frame = Union[_ObjectFrame, _ArrayFrame, _StringFrame, _ScalarFrame]


_ESCAPE_MAP = {
    "n": "\n", "t": "\t", "r": "\r", '"': '"',
    "\\": "\\", "/": "/", "b": "\b", "f": "\f",
}


def _path_str(path: List[Union[str, int]]) -> str:
    return ".".join(str(p) for p in path)


# ---------------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------------

class PartialJsonDecoder:
    """Feed it raw JSON deltas; iterate the events produced.

    Usage:
        decoder = PartialJsonDecoder(emit_string_deltas=True)
        for chunk in anthropic_input_json_deltas:
            for event in decoder.feed(chunk):
                yield event
    """

    def __init__(self, emit_string_deltas: bool = True) -> None:
        self.emit_string_deltas = emit_string_deltas
        self._stack: List[_Frame] = []

    # --- Public ------------------------------------------------------------

    def feed(self, text: str) -> Iterator[Event]:
        for ch in text:
            yield from self._consume(ch)

    def finalize(self) -> Iterator[Event]:
        return iter(())

    # --- Internal ----------------------------------------------------------

    def _consume(self, ch: str) -> Iterator[Event]:
        if not self._stack:
            # Pre-root: ignore leading whitespace / garbage until {.
            if ch == "{":
                self._stack.append(_ObjectFrame(path=[]))
            return

        top = self._stack[-1]
        if isinstance(top, _ObjectFrame):
            yield from self._consume_object(top, ch)
        elif isinstance(top, _ArrayFrame):
            yield from self._consume_array(top, ch)
        elif isinstance(top, _StringFrame):
            yield from self._consume_string(top, ch)
        elif isinstance(top, _ScalarFrame):
            yield from self._consume_scalar(top, ch)

    # --- Object frame ------------------------------------------------------

    def _consume_object(self, top: _ObjectFrame, ch: str) -> Iterator[Event]:
        if top.state == "EXPECT_KEY":
            if ch.isspace() or ch == ",":
                return
            if ch == '"':
                top.state = "IN_KEY"
                top.current_key = ""
                top.key_escape = False
                return
            if ch == "}":
                yield from self._close_structure()
                return
            return

        if top.state == "IN_KEY":
            if top.key_escape:
                top.current_key = (top.current_key or "") + _ESCAPE_MAP.get(ch, ch)
                top.key_escape = False
                return
            if ch == "\\":
                top.key_escape = True
                return
            if ch == '"':
                top.state = "AFTER_KEY"
                return
            top.current_key = (top.current_key or "") + ch
            return

        if top.state == "AFTER_KEY":
            if ch == ":":
                top.state = "EXPECT_VALUE"
            return

        if top.state == "EXPECT_VALUE":
            if ch.isspace():
                return
            child_path = list(top.path) + [top.current_key or ""]
            if ch == '"':
                self._stack.append(_StringFrame(path=child_path))
                return
            if ch == "{":
                self._stack.append(_ObjectFrame(path=child_path))
                return
            if ch == "[":
                self._stack.append(_ArrayFrame(path=child_path))
                return
            # Scalar (number, boolean, null).
            self._stack.append(_ScalarFrame(path=child_path, buf=ch))
            return

        if top.state == "AFTER_VALUE":
            if ch.isspace():
                return
            if ch == ",":
                top.state = "EXPECT_KEY"
                return
            if ch == "}":
                yield from self._close_structure()
                return
            return

    # --- Array frame -------------------------------------------------------

    def _consume_array(self, top: _ArrayFrame, ch: str) -> Iterator[Event]:
        if top.state == "EXPECT_ELEMENT_OR_CLOSE":
            if ch.isspace() or ch == ",":
                return
            if ch == "]":
                yield from self._close_structure()
                return
            child_path = list(top.path) + [top.current_index]
            if ch == '"':
                self._stack.append(_StringFrame(path=child_path))
                return
            if ch == "{":
                self._stack.append(_ObjectFrame(path=child_path))
                return
            if ch == "[":
                self._stack.append(_ArrayFrame(path=child_path))
                return
            self._stack.append(_ScalarFrame(path=child_path, buf=ch))
            return

        if top.state == "AFTER_ELEMENT":
            if ch.isspace():
                return
            if ch == ",":
                top.current_index += 1
                top.state = "EXPECT_ELEMENT_OR_CLOSE"
                return
            if ch == "]":
                yield from self._close_structure()
                return
            return

    # --- String frame ------------------------------------------------------

    def _consume_string(self, top: _StringFrame, ch: str) -> Iterator[Event]:
        if top.escape:
            mapped = _ESCAPE_MAP.get(ch, ch)
            top.buf += mapped
            top.escape = False
            if self.emit_string_deltas:
                yield DeltaEvent(path=_path_str(top.path), text=mapped)
            return
        if ch == "\\":
            top.escape = True
            return
        if ch == '"':
            value = top.buf
            self._stack.pop()
            yield from self._record_value(value)
            return
        top.buf += ch
        if self.emit_string_deltas:
            yield DeltaEvent(path=_path_str(top.path), text=ch)

    # --- Scalar frame ------------------------------------------------------

    def _consume_scalar(self, top: _ScalarFrame, ch: str) -> Iterator[Event]:
        # Scalars terminate at structural punctuation. The terminator itself
        # must be re-processed in the parent context once we've popped.
        if ch in ",}]" or ch.isspace():
            raw = top.buf.strip()
            try:
                value = json.loads(raw)
            except json.JSONDecodeError:
                # Truncated scalar — return the raw text.
                value = raw
            self._stack.pop()
            yield from self._record_value(value)
            # Re-feed the terminator to the now-current parent.
            yield from self._consume(ch)
            return
        top.buf += ch

    # --- Helpers -----------------------------------------------------------

    def _close_structure(self) -> Iterator[Event]:
        """Called when } or ] closes the current top-of-stack frame."""
        if not self._stack:
            return
        top = self._stack.pop()
        if isinstance(top, _ObjectFrame):
            value: Any = top.values
        elif isinstance(top, _ArrayFrame):
            value = top.items
        else:
            return
        # If the closing structure had no parent (top-level root object), nothing
        # more to do — the `done` event from the caller carries the full picture.
        if not self._stack:
            return
        yield from self._record_value(value, structure_kind=type(top).__name__, original_top=top)

    def _record_value(
        self,
        value: Any,
        *,
        structure_kind: Optional[str] = None,
        original_top: Optional[_Frame] = None,
    ) -> Iterator[Event]:
        """Tell the parent frame that one value just closed.

        Updates the parent's accumulated state, advances its sub-state to
        EXPECT_COMMA/CLOSE-equivalent, and — when the parent is the root or
        the parent is a top-level array — emits the corresponding back-compat
        event (FieldEvent / ArrayItemEvent).
        """
        if not self._stack:
            return
        parent = self._stack[-1]

        if isinstance(parent, _ObjectFrame):
            key = parent.current_key or ""
            parent.values[key] = value
            parent.state = "AFTER_VALUE"
            # Top-level field close → FieldEvent (back-compat with phase 1).
            if not parent.path:
                # If the value that closed was a TOP-LEVEL ARRAY, phase 1
                # emitted FieldEvent(name=key, value=None) as a sentinel
                # (mapped to "field_close" on the SSE wire). Preserve that.
                if structure_kind == "_ArrayFrame":
                    yield FieldEvent(name=key, value=None)
                else:
                    yield FieldEvent(name=key, value=value)
            return

        if isinstance(parent, _ArrayFrame):
            parent.items.append(value)
            parent.state = "AFTER_ELEMENT"
            # Top-level array element close → ArrayItemEvent (back-compat).
            if len(parent.path) == 1 and isinstance(parent.path[0], str):
                yield ArrayItemEvent(
                    array=parent.path[0],
                    index=parent.current_index,
                    value=value,
                )
            return


# ---------------------------------------------------------------------------
# SSE wire helpers
# ---------------------------------------------------------------------------

def sse(event_type: str, **payload: Any) -> str:
    body = {"type": event_type, **payload}
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def sse_heartbeat() -> str:
    return ": heartbeat\n\n"
