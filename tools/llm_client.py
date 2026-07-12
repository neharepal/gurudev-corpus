"""
Anthropic SDK wrapper for the Gurudev Corpus chat backend.

Per ADR-003, Phase 2 uses the Anthropic API (separate from Neha's consumer
Claude.ai subscription). Set ANTHROPIC_API_KEY before running.

Per RFC-003 / RFC-001:
- Default model: Claude Sonnet 4.6 (claude-sonnet-4-6)
  Strong multilingual EN+MR, best $/quality at sampradaya scale (~$33/mo for
  500 devotees with prompt caching).
- Pravachan mode routes to Claude Opus 4.7 (claude-opus-4-7) — structured
  multi-source synthesis benefits from higher capacity.

Prompt caching (per shared/prompt-caching.md):
- System prompt is the stable prefix → wrap in a text block with cache_control.
- Render order is `tools → system → messages` so caching the last system block
  caches everything before it. Each mode's system prompt is several kB, well
  over Sonnet 4.6's 2048-token minimum cacheable prefix.
- The user message (retrieved chunks + question) is variable per request and
  not worth caching for single-turn flows. For multi-turn follow-ups we add
  cache_control to the most recent assistant turn — see ChatClient.ask_followup.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any

import anthropic
from anthropic import Anthropic

from schemas import get_response_model, get_tool, splice_qa_citations, splice_quote_dict


def _coerce_json_containers(tool_input):
    """Repair a tool_use input where the model stringified a list/object field.

    Models occasionally emit a structured field (e.g. QAResponse.citations) as a
    JSON *string* — `citations: "[\\n {\\n \\"quote\\": …}]"` — instead of an actual
    array, which fails pydantic validation. For each top-level field whose value is
    a string that looks like a JSON array/object, parse it and substitute the
    parsed list/dict. Non-JSON strings (prose like `framing`) are left untouched.
    """
    if not isinstance(tool_input, dict):
        return tool_input
    out = dict(tool_input)
    for k, v in out.items():
        if isinstance(v, str) and v.strip()[:1] in ("[", "{"):
            try:
                parsed = json.loads(v)
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, (list, dict)):
                out[k] = parsed
    return out


# Model routing per RFC-001 and RFC-003.
MODEL_DEFAULT = "claude-sonnet-4-6"
MODEL_PRAVACHAN = "claude-opus-4-7"

# Per-mode output token budgets. Q&A is concise (a framing line + 2–5 quotes
# + an optional 2-sentence synthesis). Pravachan is structured and longer.
# Reading is brief (3–6 sentences + 1–2 short quotes).
# Pravachan bumped to 7000 (from 3500) after ADR-011 tool-use rewrite: JSON
# field-name + escape overhead consumes ~2x the budget that markdown did,
# and Marathi UTF-8 chars cost ~3 tokens each — at 3500 the examples array
# was truncated to empty. 7000 fits all 5 examples + thesis + Gurudev's words.
MAX_TOKENS_BY_MODE = {
    # 3000: safety ceiling. The real bound is the ≤5-citation cap (schemas.py) + the
    # "synthesis is required" rule — together a Marathi answer (framing + 5 rationales
    # + synthesis, ~3 tokens/char) lands near ~2600, so 3000 leaves the concluding
    # paragraph room to complete. (Was 2400; an 8-citation answer hit it and truncated
    # the synthesis — the fix is fewer citations, not just a bigger budget.)
    "qa": 3000,
    "pravachan": 7000,
    "reading": 1200,
}


def pick_model(mode: str) -> str:
    """Sonnet for every mode. Pravachan used Opus (RFC-001), but was moved to
    Sonnet on 2026-06-25 for latency parity with Q&A (user request) — Opus
    generating pravachan's 7000-token structured discourse was the slow path.
    Reversible: return MODEL_PRAVACHAN for pravachan to restore Opus."""
    return MODEL_DEFAULT


class MissingApiKeyError(RuntimeError):
    pass


class ChatClient:
    """Thin wrapper around the Anthropic SDK with caching baked in."""

    def __init__(self, *, api_key: str | None = None):
        # Anthropic() falls back to ANTHROPIC_API_KEY if api_key is None.
        # Give a clear error if neither is set — per ADR-003 this is the v1 setup gate.
        if api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingApiKeyError(
                "ANTHROPIC_API_KEY is not set. Per ADR-003, the chat backend uses "
                "the Anthropic API (separate from Claude.ai subscriptions). "
                "Create an account at https://console.anthropic.com, generate a key, "
                "and export it: `export ANTHROPIC_API_KEY=...`"
            )
        self.client = Anthropic(api_key=api_key)

    def ask(
        self,
        *,
        system_prompt: str,
        user_message: str,
        mode: str = "qa",
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> anthropic.types.Message:
        """Single-turn ask: send system + one user message, return the Message.

        The system prompt is wrapped with `cache_control` so the second and
        later calls reuse the cached prefix (~90% input-cost reduction on
        the system-prompt portion). Verify hits via `response.usage`.
        """
        model = model or pick_model(mode)
        max_tokens = max_tokens or MAX_TOKENS_BY_MODE.get(mode, 2000)

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[
                    {"role": "user", "content": user_message},
                ],
            )
            return response
        except anthropic.RateLimitError as e:
            raise RuntimeError(
                f"Anthropic API rate limit hit. Wait a few seconds and retry. ({e})"
            ) from e
        except anthropic.AuthenticationError as e:
            raise RuntimeError(
                "Anthropic API rejected the API key. Check ANTHROPIC_API_KEY. "
                f"({e})"
            ) from e
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e

    def ask_structured(
        self,
        *,
        mode: str,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int | None = None,
        label_to_chunk: dict | None = None,
    ):
        """Single-turn structured ask via tool-use (ADR-011).

        Forces the model to emit its answer via the mode-specific
        `emit_<mode>_response` tool. Returns a tuple of
        (parsed_pydantic_instance, raw_message). Raises if the model
        does not produce a tool_use block, or if the tool input fails
        pydantic validation.
        """
        model = model or pick_model(mode)
        max_tokens = max_tokens or MAX_TOKENS_BY_MODE.get(mode, 2000)
        tool = get_tool(mode)
        response_model = get_response_model(mode)

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[
                    {"role": "user", "content": user_message},
                ],
            )
        except anthropic.RateLimitError as e:
            raise RuntimeError(
                f"Anthropic API rate limit hit. Wait a few seconds and retry. ({e})"
            ) from e
        except anthropic.AuthenticationError as e:
            raise RuntimeError(
                "Anthropic API rejected the API key. Check ANTHROPIC_API_KEY. "
                f"({e})"
            ) from e
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e

        tool_use = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_use = block
                break
        if tool_use is None:
            raise RuntimeError(
                f"Model returned no tool_use block for {tool['name']!r}. "
                f"stop_reason={response.stop_reason!r}"
            )

        # Reference-and-splice: fill verbatim `body` + attribution into QA
        # citations from the referenced chunks before validation.
        tool_input = _coerce_json_containers(tool_use.input)
        if mode == "qa" and label_to_chunk:
            tool_input = copy.deepcopy(tool_input)
            splice_qa_citations(tool_input, label_to_chunk)

        try:
            parsed = response_model.model_validate(tool_input)
        except Exception as e:  # pydantic.ValidationError
            raise RuntimeError(
                f"Tool input failed pydantic validation for mode={mode!r}: {e}"
            ) from e

        return parsed, response

    def ask_structured_stream(
        self,
        *,
        mode: str,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int | None = None,
        label_to_chunk: dict | None = None,
    ):
        """Streaming variant of ask_structured (RFC-010).

        Yields (event_type, payload) tuples:
          - ("field",      {"name", "value"})        top-level field closed
          - ("field_close",{"name"})                 array field closed (sentinel)
          - ("array_item", {"array", "index", "value"})  one element of an array
          - ("delta",      {"path", "text"})         char-by-char passthrough for active leaf string
          - ("done",       {"response", "usage"})    full validated pydantic dump
          - ("error",      {"message"})              upstream or validation failure

        The Anthropic tool-use stream emits `input_json_delta` blocks whose
        `partial_json` strings are fed into PartialJsonDecoder; the decoder
        determines when each top-level field or array element is fully closed
        and emits the corresponding event.
        """
        # Import inside method to keep module load cheap.
        sys.path.insert(0, os.path.dirname(__file__))
        from streaming import PartialJsonDecoder, FieldEvent, ArrayItemEvent, DeltaEvent

        model = model or pick_model(mode)
        max_tokens = max_tokens or MAX_TOKENS_BY_MODE.get(mode, 2000)
        tool = get_tool(mode)
        response_model = get_response_model(mode)

        decoder = PartialJsonDecoder(emit_string_deltas=True)
        full_message = None

        try:
            with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[
                    {"role": "user", "content": user_message},
                ],
            ) as stream:
                for event in stream:
                    etype = getattr(event, "type", None)
                    if etype == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        if delta is None:
                            continue
                        dtype = getattr(delta, "type", None)
                        if dtype == "input_json_delta":
                            partial = getattr(delta, "partial_json", "")
                            for ev in decoder.feed(partial):
                                if isinstance(ev, FieldEvent):
                                    if ev.value is None:
                                        # Array close sentinel.
                                        yield ("field_close", {"name": ev.name})
                                    else:
                                        yield ("field", {"name": ev.name, "value": ev.value})
                                elif isinstance(ev, ArrayItemEvent):
                                    value = ev.value
                                    # Splice the verbatim body into a QA citation
                                    # the moment its (short) reference fields close,
                                    # so the full quote reaches the client without
                                    # the model ever retyping it. See RFC-010 /
                                    # docs/PLAN-reference-and-splice-citations.md.
                                    if (
                                        mode == "qa"
                                        and ev.array == "citations"
                                        and label_to_chunk
                                        and isinstance(value, dict)
                                        and isinstance(value.get("quote"), dict)
                                    ):
                                        splice_quote_dict(value["quote"], label_to_chunk)
                                    yield ("array_item", {"array": ev.array, "index": ev.index, "value": value})
                                elif isinstance(ev, DeltaEvent):
                                    yield ("delta", {"path": ev.path, "text": ev.text})
                full_message = stream.get_final_message()
        except anthropic.RateLimitError as e:
            yield ("error", {"message": f"Anthropic rate limit: {e}"})
            return
        except anthropic.AuthenticationError as e:
            yield ("error", {"message": f"Anthropic auth: {e}"})
            return
        except anthropic.APIError as e:
            yield ("error", {"message": f"Anthropic API: {e}"})
            return

        # Reconcile: validate the full tool input against pydantic.
        tool_use = None
        for block in full_message.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool["name"]:
                tool_use = block
                break
        if tool_use is None:
            yield ("error", {"message": f"Model returned no tool_use block for {tool['name']!r}"})
            return

        tool_input = _coerce_json_containers(tool_use.input)
        if mode == "qa" and label_to_chunk:
            tool_input = copy.deepcopy(tool_input)
            splice_qa_citations(tool_input, label_to_chunk)

        try:
            parsed = response_model.model_validate(tool_input)
        except Exception as e:
            yield ("error", {"message": f"Validation failed for mode={mode!r}: {e}"})
            return

        yield ("done", {"response": parsed.model_dump(), "usage": cache_stats(full_message)})

    def ask_with_history(
        self,
        *,
        system_prompt: str,
        history: list[dict[str, Any]],
        next_user_message: str,
        mode: str = "qa",
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> anthropic.types.Message:
        """Multi-turn variant: send prior history + a new user message.

        For multi-turn flows we additionally cache the most recent message in
        the existing history — this grows the cache as the conversation goes
        on, so every follow-up reads more from cache than the previous one.

        `history` is a list of {role, content} dicts in the SDK's normal shape.
        """
        model = model or pick_model(mode)
        max_tokens = max_tokens or MAX_TOKENS_BY_MODE.get(mode, 2000)

        messages: list[dict[str, Any]] = []
        # Copy history; mark the last entry's last content block as a cache breakpoint.
        if history:
            for m in history[:-1]:
                messages.append(m)
            last = dict(history[-1])
            content = last.get("content")
            if isinstance(content, str):
                # Convert to block form so we can attach cache_control.
                last_content = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            elif isinstance(content, list) and content:
                last_content = list(content)
                last_block = dict(last_content[-1])
                last_block["cache_control"] = {"type": "ephemeral"}
                last_content[-1] = last_block
            else:
                last_content = content
            last["content"] = last_content
            messages.append(last)

        messages.append({"role": "user", "content": next_user_message})

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=messages,
            )
            return response
        except anthropic.APIError as e:
            raise RuntimeError(f"Anthropic API error: {e}") from e


def render_response_text(response: anthropic.types.Message) -> str:
    """Concatenate all text blocks in the response (skip tool_use, thinking)."""
    return "".join(b.text for b in response.content if b.type == "text")


def cache_stats(response: anthropic.types.Message) -> dict[str, int]:
    """Pull the cache-relevant fields off the usage object for logging."""
    u = response.usage
    return {
        "input": getattr(u, "input_tokens", 0) or 0,
        "output": getattr(u, "output_tokens", 0) or 0,
        "cache_creation": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
