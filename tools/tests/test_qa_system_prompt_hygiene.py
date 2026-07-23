"""Guards on the QA system prompt so we don't regress the reader-language
+ work-labeling rules added 2026-07-22 in response to sadhak feedback.

The rules the LLM must be told to follow:
  1. No engineering jargon in user-facing prose fields ("the corpus",
     "retrieved passages", etc.) — see nilambari's Jul 22 answer that
     said "The biography *Parmartha Mandir* records..." — reader is
     a devotee, not an engineer.
  2. No invented descriptive labels for works ("the biography",
     "the philosophical work") when the label isn't explicitly stated
     in the citation body. `kind` in the chunk meta is ground truth.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from prompts import SYSTEM_PROMPT_QA  # noqa: E402


def test_no_engineering_jargon_rule_present():
    """The prompt must forbid `the corpus` / `retrieved passages` / etc.
    in prose fields the reader sees."""
    p = SYSTEM_PROMPT_QA.lower()
    # The rule itself must call out the banned phrases so the model sees
    # the exact tokens it should avoid.
    assert "reader-facing language" in p or "reader is a devotee" in p
    for banned in ["the corpus", "retrieved passages", "the retrieved set"]:
        assert banned in p, (
            f"the prompt should list {banned!r} as a banned phrase so the "
            f"model recognizes and avoids it"
        )
    # Near-cousins added 2026-07-23 after the "list of places" answer
    # surfaced "these passages record" / "the available passages" — same
    # jargon-in-disguise the original rule didn't catch.
    for banned in [
        "the available passages",
        "these passages record",
        "the passages here",
    ]:
        assert banned in p, (
            f"the prompt should list {banned!r} as a banned phrase so the "
            f"model recognizes and avoids it — it's a near-cousin of the "
            f"original retrieval-jargon ban"
        )


def test_do_not_invent_work_labels_rule_present():
    """The prompt must forbid prefixing works with type labels
    ("the biography X", "the philosophical work Y") that aren't
    supported by the citation body."""
    p = SYSTEM_PROMPT_QA.lower()
    # The specific rule + example must be present.
    assert "do not invent descriptive labels" in p
    # Reference the specific 2026-07-22 misfire — Parmartha Mandir as
    # a "biography" — so future maintainers know why the rule exists.
    assert "parmartha mandir" in p
    # The `kind` meta-line is the ground truth.
    assert "kind=" in p or "ground truth" in p


def test_positive_example_of_correct_style():
    """The prompt should include a positive example (correct usage) so
    the model has something to imitate, not just a list of don'ts."""
    p = SYSTEM_PROMPT_QA
    # A correct phrasing example ("Parmartha Mandir records how...")
    # or an analogous positive template.
    assert (
        "Parmartha Mandir records how" in p
        or ("correct:" in p.lower() and "records" in p.lower())
    )


def test_no_invented_author_attribution_in_anthologies():
    """The prompt must forbid attributing a passage to a specific author
    in a multi-author anthology when the citation body doesn't self-
    identify the author. Root of Mukund's 2026-07-22 misfire —
    Contemporary Indian Philosophy passage attributed to 'Shri
    Gurudev's own essay' when it was actually from another essayist."""
    p = SYSTEM_PROMPT_QA
    p_l = p.lower()
    # The rule must exist by name.
    assert "invent per-passage author attribution" in p_l or (
        "multi-author" in p_l and "attribution" in p_l
    )
    # It must name Contemporary Indian Philosophy explicitly (that's
    # our known misfire case).
    assert "Contemporary Indian Philosophy" in p
    # It must include the concrete anti-example ("Shri Gurudev's own essay").
    assert "Shri Gurudev's own essay" in p
