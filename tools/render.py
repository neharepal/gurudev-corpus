"""
Markdown rendering for structured responses (ADR-011).

The wire-protocol contract is JSON (validated against pydantic models in
`schemas.py`). For terminal display in `chat.py` and for the per-question
reports in `tune_sweep.py`, we render the structured response back into
markdown matching the prior hand-formatted layout.

This is FOR HUMAN DISPLAY ONLY. Production traffic (FastAPI → chat-app)
flows pydantic → JSON; this module is never on that path.
"""

from __future__ import annotations

from typing import Any, List

from schemas import (
    PravachanResponse,
    QAResponse,
    ReadingResponse,
)


def _quote_block(quote, attribution_suffix: str = "") -> List[str]:
    """Render a Quote as a Markdown blockquote + attribution line."""
    lines: List[str] = []
    body = quote.body.strip()
    # Preserve internal newlines inside the blockquote.
    for ln in body.splitlines():
        lines.append(f"> {ln}")
    attr_bits = [quote.workTitle]
    if quote.location:
        attr_bits.append(quote.location)
    attr = ", ".join(attr_bits)
    extra = f" ({quote.kind})"
    if quote.author:
        extra += f" · {quote.author}"
    lines.append(f"> *— {attr}{extra}{attribution_suffix}*")
    if quote.paraphrase:
        lines.append(f">")
        lines.append(f"> *{quote.paraphrase}*")
    return lines


def render_qa_markdown(resp: QAResponse) -> str:
    out: List[str] = []
    if resp.classification == "meta":
        # Meta mode: framing IS the answer. References optional.
        out.append(resp.framing.strip())
        if resp.references:
            out.append("")
            out.append("Works referenced:")
            for r in resp.references:
                bits = [r.workTitle]
                if r.location:
                    bits.append(r.location)
                tail = f" · {r.author}" if r.author else ""
                out.append(f"— {', '.join(bits)}{tail}")
        out.append("")
        out.append(f"_classification: {resp.classification}_")
        return "\n".join(out)

    # Doctrinal
    out.append(resp.framing.strip())
    for i, cit in enumerate(resp.citations):
        out.append("")
        out.extend(_quote_block(cit.quote))
        out.append("")
        out.append(f"**Why this passage:** {cit.whyChosen.strip()}")
        if i != len(resp.citations) - 1:
            out.append("")
            out.append("---")
    if resp.synthesis:
        out.append("")
        out.append(f"**Synthesis:** {resp.synthesis.strip()}")
    out.append("")
    out.append(f"_classification: {resp.classification}_")
    return "\n".join(out)


def render_pravachan_markdown(resp: PravachanResponse) -> str:
    out: List[str] = []
    out.append("## Your question")
    out.append("")
    out.append(f"> \"{resp.question.strip()}\"")
    if resp.thesis:
        out.append("")
        out.append("## Thesis")
        out.append("")
        out.append(resp.thesis.strip())
    if resp.gurudevsWords:
        out.append("")
        out.append("## Gurudev's words")
        out.append("")
        out.extend(_quote_block(resp.gurudevsWords))
    out.append("")
    out.append("## Stories")
    out.append("")
    for i, ex in enumerate(resp.examples, 1):
        out.append(f"{i}. **{ex.title.strip()}**")
        if ex.gloss:
            out.append(f"   {ex.gloss.strip()}")
        out.append("")
        # Indent the quote block under the list item.
        qlines = _quote_block(ex.quote)
        for ln in qlines:
            out.append(f"   {ln}")
        out.append("")
        out.append(f"   **Why this story:** {ex.whyThisExample.strip()}")
        if ex.readSlug:
            out.append("")
            out.append(f"   [→ Read in full: `{ex.readSlug}`]")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_reading_markdown(resp: ReadingResponse) -> str:
    out: List[str] = []
    out.append(resp.framing.strip())
    out.append("")
    for ln in resp.passage.strip().splitlines():
        out.append(f"> {ln}")
    att = resp.attribution
    out.append(
        f"> *— {att.workTitle}, {att.chapter} · {att.author}*"
    )
    return "\n".join(out)


def render_markdown(resp: Any) -> str:
    """Dispatch by response `kind`."""
    if isinstance(resp, QAResponse):
        return render_qa_markdown(resp)
    if isinstance(resp, PravachanResponse):
        return render_pravachan_markdown(resp)
    if isinstance(resp, ReadingResponse):
        return render_reading_markdown(resp)
    raise TypeError(f"Unknown response type: {type(resp).__name__}")
