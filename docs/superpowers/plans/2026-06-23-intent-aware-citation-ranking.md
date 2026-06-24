# Intent-Aware Citation Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rank retrieved citations by query intent — canonical works win for philosophical questions, recollections (athvani/biography) win for narrative ones — and drop secondary reprints of canonical originals.

**Architecture:** Extend the existing `retrieve.py` pipeline (cosine → boost → MMR). A new `intent.py` classifies the query (heuristic, cheap LLM fallback). A new `apply_intent_tier_weights` replaces the flat `apply_primary_tier_boost`, adding a per-tier delta keyed on intent. `mmr_rerank` gains an authority-aware near-duplicate skip. Implements RFC-011.

**Tech Stack:** Python 3 (anaconda interpreter), NumPy, the `anthropic` SDK (Haiku for the intent fallback), pytest.

## Global Constraints

- **Interpreter:** all Python (tests + scripts) runs under `/Users/neharepal/opt/anaconda3/bin/python` — the env that has `fastapi`, `anthropic`, `numpy`, `pytest 5.4.3`. The pyenv default lacks these.
- **Flat imports:** `tools/` modules import each other flat (`import retrieve`, `import intent`), so tests must run with `tools/` on `sys.path` (handled by `tools/tests/conftest.py`, Task 1).
- **No API in unit tests.** The intent LLM fallback is injectable; unit tests pass a stub or use `use_llm_fallback=False`. Real Haiku/Anthropic calls happen only at runtime.
- **Non-mutating scoring helpers:** `apply_intent_tier_weights` returns a new array (`scores.copy()`), never mutates its input — same contract as the `apply_primary_tier_boost` it replaces.
- **Intent labels are exactly:** `"doctrinal"`, `"narrative"`, `"navigational"`, `"unknown"`.
- **Source tiers are exactly:** `"canonical"`, `"recollections"`, `"reference"`.
- **Commit footer:** end every commit message with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- **Run pytest from the repo root:** `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest <path> -v`.

---

### Task 1: Source-tier classification + test scaffold

**Files:**
- Create: `tools/tests/__init__.py` (empty)
- Create: `tools/tests/conftest.py`
- Create: `tools/tests/test_tiers.py`
- Modify: `tools/retrieve.py` (add `chunk_tier` after the `PRIMARY_AUTHORS` block, ~line 60)

**Interfaces:**
- Produces: `retrieve.chunk_tier(meta: dict) -> str` returning one of `"canonical" | "recollections" | "reference"`.

- [ ] **Step 1: Create the test scaffold**

Create `tools/tests/__init__.py` (empty file).

Create `tools/tests/conftest.py`:

```python
import os
import sys

# Put tools/ on sys.path so flat imports (`import retrieve`, `import intent`) work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

- [ ] **Step 2: Write the failing test**

Create `tools/tests/test_tiers.py`:

```python
import retrieve


def test_canonical_kind_is_canonical_tier():
    assert retrieve.chunk_tier({"kind": "canonical"}) == "canonical"


def test_athvani_and_biography_are_recollections():
    assert retrieve.chunk_tier({"kind": "athvani"}) == "recollections"
    assert retrieve.chunk_tier({"kind": "biography"}) == "recollections"


def test_reference_kind_is_reference_tier():
    assert retrieve.chunk_tier({"kind": "reference"}) == "reference"


def test_unknown_or_missing_kind_defaults_to_recollections():
    assert retrieve.chunk_tier({"kind": "something-else"}) == "recollections"
    assert retrieve.chunk_tier({}) == "recollections"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_tiers.py -v`
Expected: FAIL with `AttributeError: module 'retrieve' has no attribute 'chunk_tier'`

- [ ] **Step 4: Implement `chunk_tier`**

In `tools/retrieve.py`, immediately after the `PRIMARY_AUTHORS = frozenset({...})` block (around line 60), add:

```python
def chunk_tier(meta: dict) -> str:
    """Authority tier of a chunk for intent-aware ranking (RFC-011).

    canonical     -> the masters' / canonical authors' own works (01_canonical)
    recollections -> athvani + biography (souvenirs, memoirs; 00_raw, 02_aggregated)
    reference     -> bibliographies / indexes (03_catalog)
    Anything unrecognised defaults to recollections (never over-promoted).
    """
    kind = meta.get("kind")
    if kind == "canonical":
        return "canonical"
    if kind == "reference":
        return "reference"
    return "recollections"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_tiers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/tests/__init__.py tools/tests/conftest.py tools/tests/test_tiers.py tools/retrieve.py
git commit -m "$(printf 'Add chunk_tier source-authority classifier (RFC-011)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: Intent heuristic classifier

**Files:**
- Create: `tools/intent.py`
- Create: `tools/tests/test_intent.py`

**Interfaces:**
- Produces: `intent._heuristic_intent(query: str) -> str | None` — a confident label or `None` when ambiguous (no cues / tie).
- Produces: `intent.classify_intent(query: str, *, use_llm_fallback: bool = True, llm_fallback=None) -> str` — one of the four intent labels. (LLM fallback wired in Task 3; this task lands the heuristic + `"unknown"` default and the `use_llm_fallback=False` path.)
- Produces: `intent.INTENTS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

Create `tools/tests/test_intent.py`:

```python
import intent


def test_doctrinal_cues():
    assert intent.classify_intent(
        "What is Gurudev's philosophy of self-surrender?", use_llm_fallback=False
    ) == "doctrinal"


def test_narrative_cues_english_and_marathi():
    assert intent.classify_intent(
        "Tell me an athvani about Bhausaheb Maharaj", use_llm_fallback=False
    ) == "narrative"
    assert intent.classify_intent(
        "महाराजांची एखादी आठवण सांगा", use_llm_fallback=False
    ) == "narrative"


def test_navigational_cues():
    assert intent.classify_intent(
        "Which works of Gurudev Ranade are in the corpus?", use_llm_fallback=False
    ) == "navigational"


def test_no_cues_without_fallback_is_unknown():
    assert intent.classify_intent("Hmm.", use_llm_fallback=False) == "unknown"


def test_heuristic_returns_none_when_ambiguous():
    assert intent._heuristic_intent("Hmm.") is None


def test_injected_fallback_used_for_ambiguous_query():
    called = {}

    def stub(q):
        called["q"] = q
        return "doctrinal"

    out = intent.classify_intent("Hmm tell me.", llm_fallback=stub)
    assert out == "doctrinal"
    assert called["q"] == "Hmm tell me."


def test_fallback_exception_resolves_to_unknown():
    def boom(q):
        raise RuntimeError("api down")

    assert intent.classify_intent("Hmm tell me.", llm_fallback=boom) == "unknown"


def test_fallback_bad_label_resolves_to_unknown():
    assert intent.classify_intent(
        "Hmm tell me.", llm_fallback=lambda q: "garbage"
    ) == "unknown"


def test_confident_query_never_calls_fallback():
    def boom(q):
        raise AssertionError("fallback must not run for a confident query")

    assert intent.classify_intent(
        "What is the philosophy of bhakti?", llm_fallback=boom
    ) == "doctrinal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_intent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'intent'`

- [ ] **Step 3: Implement `tools/intent.py` (heuristic only)**

Create `tools/intent.py`:

```python
"""Query-intent classification for intent-aware citation ranking (RFC-011).

A multilingual heuristic classifies the common cases for free; an injectable
LLM fallback (wired in Task 3) handles ambiguous queries. Intent never blocks
retrieval — any failure resolves to "unknown".
"""

from __future__ import annotations

from typing import Callable, Optional

INTENTS = ("doctrinal", "narrative", "navigational", "unknown")

# Lowercased substring cues per intent (Devanagari has no case). Seed lists —
# expand against real queries (RFC-011 open question).
_CUES: dict[str, tuple[str, ...]] = {
    "doctrinal": (
        "teaching", "philosophy", "philosophical", "doctrine", "meaning",
        "concept", "principle", "what does", "explain",
        "शिकवण", "तत्त्वज्ञान", "अर्थ", "सिद्धांत", "तत्त्व",
    ),
    "narrative": (
        "athvani", "story", "stories", "incident", "anecdote", "memory",
        "memories", "recollection",
        "आठवण", "प्रसंग", "गोष्ट", "कथा",
    ),
    "navigational": (
        "which works", "which books", "what books", "list", "index",
        "catalogue", "catalog", "structure", "how many",
        "कोणते ग्रंथ", "यादी", "सूची",
    ),
}


def _heuristic_intent(query: str) -> Optional[str]:
    """Confident intent label, or None if no cues fire or two intents tie."""
    q = query.lower()
    hits = {name: sum(1 for cue in cues if cue in q) for name, cues in _CUES.items()}
    best = max(hits, key=hits.get)
    top = hits[best]
    if top == 0:
        return None  # no cues -> ambiguous
    if sum(1 for v in hits.values() if v == top) > 1:
        return None  # tie -> ambiguous
    return best


def classify_intent(
    query: str,
    *,
    use_llm_fallback: bool = True,
    llm_fallback: Optional[Callable[[str], Optional[str]]] = None,
) -> str:
    """Return one of INTENTS. Heuristic first; LLM fallback only when ambiguous."""
    label = _heuristic_intent(query)
    if label is not None:
        return label
    if use_llm_fallback:
        fb = llm_fallback or _default_llm_fallback
        try:
            guess = fb(query)
        except Exception:
            guess = None
        if guess in INTENTS and guess != "unknown":
            return guess
    return "unknown"


def _default_llm_fallback(query: str) -> Optional[str]:  # replaced in Task 3
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_intent.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/intent.py tools/tests/test_intent.py
git commit -m "$(printf 'Add multilingual intent heuristic + fallback contract (RFC-011)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: Intent LLM fallback (Haiku, injectable, cached)

**Files:**
- Modify: `tools/intent.py` (replace the stub `_default_llm_fallback`)
- Modify: `tools/tests/test_intent.py` (add fallback-path tests)

**Interfaces:**
- Consumes: `intent.classify_intent(..., llm_fallback=...)` and the stub `intent._default_llm_fallback` from Task 2.
- Produces: real `intent._default_llm_fallback(query: str) -> str | None` — calls Haiku, cached per query, returns a label or `None`; plus `intent._get_client()`. Used automatically by `classify_intent` when no `llm_fallback` is injected.

- [ ] **Step 1: Write the failing tests**

Append to `tools/tests/test_intent.py` (these monkeypatch the Anthropic client, so they make **no** real API call):

```python
class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResp:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


def _fake_client(reply_text):
    class _FakeClient:
        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            return _FakeResp(reply_text)

    return _FakeClient()


def test_default_fallback_parses_haiku_label(monkeypatch):
    monkeypatch.setattr(intent, "_get_client", lambda: _fake_client("narrative"))
    intent._default_llm_fallback.cache_clear()
    assert intent._default_llm_fallback("some genuinely ambiguous query") == "narrative"


def test_default_fallback_unrecognised_label_returns_none(monkeypatch):
    monkeypatch.setattr(intent, "_get_client", lambda: _fake_client("no idea at all"))
    intent._default_llm_fallback.cache_clear()
    assert intent._default_llm_fallback("another ambiguous query") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_intent.py::test_default_fallback_parses_haiku_label tools/tests/test_intent.py::test_default_fallback_unrecognised_label_returns_none -v`
Expected: FAIL — the Task 2 stub returns `None` (so `== "narrative"` fails), and `_default_llm_fallback` has no `.cache_clear` attribute yet (`AttributeError`) because it is not yet wrapped in `lru_cache`.

- [ ] **Step 3: Replace `_default_llm_fallback` with the real Haiku call**

In `tools/intent.py`, replace the stub `_default_llm_fallback` with:

```python
from functools import lru_cache

_INTENT_MODEL = "claude-haiku-4-5"  # cheapest model; intent is a 1-word task
_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic  # lazy import keeps unit tests SDK-free
        _client = Anthropic()
    return _client


@lru_cache(maxsize=512)
def _default_llm_fallback(query: str) -> Optional[str]:
    """Classify an ambiguous query with Haiku. Cached per query. None on failure."""
    prompt = (
        "Classify this question about a spiritual corpus into exactly one intent "
        "label. Reply with only the label word.\n"
        "- doctrinal: teaching, philosophy, meaning, or doctrine\n"
        "- narrative: a story, anecdote, incident, or recollection (athvani)\n"
        "- navigational: which works/books exist, lists, structure, counts\n\n"
        f"Question: {query}\nLabel:"
    )
    resp = _get_client().messages.create(
        model=_INTENT_MODEL,
        max_tokens=8,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    ).strip().lower()
    for name in ("doctrinal", "narrative", "navigational"):
        if name in text:
            return name
    return None
```

Add `from functools import lru_cache` to the imports at the top of the file (or keep it local as shown).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_intent.py -v`
Expected: PASS (11 passed) — the new tests monkeypatch the client, so no real Haiku call is made.

- [ ] **Step 5: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/intent.py tools/tests/test_intent.py
git commit -m "$(printf 'Add Haiku intent fallback for ambiguous queries (RFC-011)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: Intent × tier weighting

**Files:**
- Modify: `tools/retrieve.py` (add constants + `apply_intent_tier_weights` near `apply_primary_tier_boost`, ~line 84)
- Create: `tools/tests/test_weights.py`

**Interfaces:**
- Consumes: `retrieve.chunk_tier` (Task 1), `retrieve.PRIMARY_AUTHORS` (existing).
- Produces: `retrieve.TIER_WEIGHTS: dict[str, dict[str, float]]`, `retrieve.PRIMARY_AUTHOR_BONUS: float`, `retrieve.DUP_THRESHOLD: float`.
- Produces: `retrieve.apply_intent_tier_weights(scores: np.ndarray, metas: list[dict], intent: str, *, weights=TIER_WEIGHTS, primary_bonus=PRIMARY_AUTHOR_BONUS) -> np.ndarray` (non-mutating).

- [ ] **Step 1: Write the failing test**

Create `tools/tests/test_weights.py`:

```python
import numpy as np
import retrieve


def _metas():
    return [
        {"kind": "canonical", "author": "gurudev_ranade"},   # 0: canonical primary
        {"kind": "canonical", "author": "other_authors"},    # 1: canonical other
        {"kind": "biography"},                                # 2: recollections
        {"kind": "reference"},                                # 3: reference
    ]


def test_doctrinal_weights_prefer_canonical_demote_reference():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "doctrinal")
    # canonical primary = +0.10 + 0.04 ; canonical other = +0.10 ;
    # recollections = +0.04 ; reference = -0.12
    assert out[0] == np.float32(0.14)
    assert out[1] == np.float32(0.10)
    assert out[2] == np.float32(0.04)
    assert out[3] == np.float32(-0.12)
    # ordering: primary > other > recollections > reference
    assert out[0] > out[1] > out[2] > out[3]


def test_narrative_weights_prefer_recollections():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "narrative")
    assert out[2] == np.float32(0.10)          # recollections boosted
    assert out[0] == np.float32(0.04)          # canonical primary: 0 + primary bonus
    assert out[2] > out[0]                     # recollection beats canonical


def test_unknown_intent_used_for_unrecognised_label():
    scores = np.zeros(4, dtype=np.float32)
    out = retrieve.apply_intent_tier_weights(scores, _metas(), "banana")
    # falls back to the "unknown" row: canonical +0.05, recollections 0, reference -0.08
    assert out[1] == np.float32(0.05)
    assert out[3] == np.float32(-0.08)


def test_non_mutating():
    scores = np.zeros(4, dtype=np.float32)
    snapshot = scores.copy()
    retrieve.apply_intent_tier_weights(scores, _metas(), "doctrinal")
    assert np.array_equal(scores, snapshot)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_weights.py -v`
Expected: FAIL with `AttributeError: module 'retrieve' has no attribute 'apply_intent_tier_weights'`

- [ ] **Step 3: Add constants + `apply_intent_tier_weights`**

In `tools/retrieve.py`, after `apply_primary_tier_boost` (~line 84), add:

```python
# Intent-aware tier weighting (RFC-011). Deltas are added to cosine BEFORE MMR.
# Magnitudes are starting values; cosine top scores ~0.5-0.7, so these reorder
# near-ties without swamping a genuinely strong match. Tune via tune_sweep.py.
TIER_WEIGHTS: dict[str, dict[str, float]] = {
    "doctrinal":    {"canonical": 0.10, "recollections": 0.04, "reference": -0.12},
    "narrative":    {"canonical": 0.00, "recollections": 0.10, "reference": -0.08},
    "navigational": {"canonical": 0.00, "recollections": 0.00, "reference":  0.08},
    "unknown":      {"canonical": 0.05, "recollections": 0.00, "reference": -0.08},
}
PRIMARY_AUTHOR_BONUS = 0.04   # canonical works by lineage masters (PRIMARY_AUTHORS)
DUP_THRESHOLD = 0.92          # cosine >= this between two chunks => near-duplicate


def apply_intent_tier_weights(
    scores: np.ndarray,
    metas: list[dict],
    intent: str,
    *,
    weights: dict[str, dict[str, float]] = TIER_WEIGHTS,
    primary_bonus: float = PRIMARY_AUTHOR_BONUS,
) -> np.ndarray:
    """Add an intent-conditioned per-tier delta to each score; return a new array.

    Replaces apply_primary_tier_boost. `intent` is one of the keys in `weights`;
    an unrecognised intent falls back to the "unknown" row. Canonical chunks by
    a lineage-master author get `primary_bonus` on top. Non-mutating.
    """
    table = weights.get(intent) or weights["unknown"]
    boosted = scores.copy()
    for i, m in enumerate(metas):
        tier = chunk_tier(m)
        delta = table.get(tier, 0.0)
        if tier == "canonical" and m.get("author") in PRIMARY_AUTHORS:
            delta += primary_bonus
        boosted[i] += delta
    return boosted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_weights.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/retrieve.py tools/tests/test_weights.py
git commit -m "$(printf 'Add intent x tier weighting matrix (RFC-011)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: Authority-aware near-duplicate demotion in MMR

**Files:**
- Modify: `tools/retrieve.py` (`mmr_rerank` — add `dup_threshold` param + skip, ~lines 120-168)
- Create: `tools/tests/test_dedup.py`

**Interfaces:**
- Consumes: `retrieve.DUP_THRESHOLD` (Task 4).
- Produces: `retrieve.mmr_rerank(..., dup_threshold: float = DUP_THRESHOLD)` — candidates whose cosine similarity to an already-selected chunk ≥ `dup_threshold` are skipped.

- [ ] **Step 1: Write the failing test**

Create `tools/tests/test_dedup.py`:

```python
import numpy as np
import retrieve


def test_near_duplicate_of_selected_chunk_is_skipped():
    # 3 unit vectors: 0 and 1 are near-identical (the souvenir reprint case),
    # 2 is distinct. With max_per_source high, MMR would otherwise take 0 and 1.
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.999, 0.0447, 0.0],   # ~0.999 cosine with vec 0
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float32,
    )
    # normalise rows
    embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    metas = [
        {"work_id": "canonical-gita"},
        {"work_id": "acpr-souvenir"},
        {"work_id": "other"},
    ]
    qvec = embeddings[0]
    cand_idx = np.array([0, 1, 2])
    cand_scores = embeddings @ qvec  # 0 highest, 1 ~equal, 2 low

    out = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, embeddings, metas,
        top_k=3, mmr_lambda=0.7, max_per_source=5, dup_threshold=0.92,
    )
    selected = [i for i, _ in out]
    assert 0 in selected           # the canonical original is kept
    assert 1 not in selected       # its near-duplicate reprint is dropped
    assert 2 in selected           # the distinct chunk survives


def test_dup_threshold_one_keeps_everything():
    embeddings = np.eye(3, dtype=np.float32)
    metas = [{"work_id": f"w{i}"} for i in range(3)]
    qvec = embeddings[0]
    cand_idx = np.array([0, 1, 2])
    cand_scores = embeddings @ qvec
    out = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, embeddings, metas,
        top_k=3, mmr_lambda=0.7, max_per_source=5, dup_threshold=1.0,
    )
    assert len(out) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_dedup.py -v`
Expected: FAIL — `mmr_rerank() got an unexpected keyword argument 'dup_threshold'`

- [ ] **Step 3: Add the `dup_threshold` skip to `mmr_rerank`**

In `tools/retrieve.py`, change the `mmr_rerank` signature to add the keyword-only param (alongside `max_per_source`):

```python
    max_per_source: int,
    dup_threshold: float = DUP_THRESHOLD,
) -> list[tuple[int, float]]:
```

Then, inside the candidate loop, immediately AFTER the `max_div` is computed and BEFORE the `mmr = ...` line, add the skip:

```python
            # diversity penalty: max similarity to any already-selected chunk
            if selected:
                max_div = float(
                    np.max(embeddings[selected] @ embeddings[idx])
                )
            else:
                max_div = 0.0
            # Authority-aware dedup: a near-duplicate of an already-selected
            # (higher-ranked) chunk is dropped — the intent weighting made the
            # higher-authority copy win the earlier slot. (RFC-011)
            if selected and max_div >= dup_threshold:
                continue
            mmr = mmr_lambda * sim - (1.0 - mmr_lambda) * max_div
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/test_dedup.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the whole suite to confirm no regressions**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -v`
Expected: PASS (all tests from Tasks 1-5)

- [ ] **Step 6: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/retrieve.py tools/tests/test_dedup.py
git commit -m "$(printf 'Add authority-aware near-duplicate demotion to MMR (RFC-011)\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: Wire intent classification into the three retrieval call sites

**Files:**
- Modify: `tools/server.py` (`_retrieve`, line ~130)
- Modify: `tools/chat.py` (`run_retrieval`, line ~87)
- Modify: `tools/tune_sweep.py` (`retrieve_for`, line ~134)
- Modify: `tools/retrieve.py` (delete the now-unused `apply_primary_tier_boost`)

**Interfaces:**
- Consumes: `intent.classify_intent` (Tasks 2-3), `retrieve.apply_intent_tier_weights` (Task 4).
- Produces: no new public API — replaces the three `retrieve.apply_primary_tier_boost(...)` calls with intent-aware weighting. `mmr_rerank` uses its `dup_threshold` default, so those calls need no change.

> This task is wiring; it is verified by an import smoke-check plus a grep that the old call is gone, then a manual cost-aware integration run. Each sub-edit is shown in full.

- [ ] **Step 1: Update `server.py`**

In `tools/server.py`, near the other imports (the block with `import retrieve`), add:

```python
import intent
```

In `_retrieve`, replace:

```python
    scores = retrieve.apply_primary_tier_boost(scores, sub_metas)
```

with:

```python
    query_intent = intent.classify_intent(question)
    scores = retrieve.apply_intent_tier_weights(scores, sub_metas, query_intent)
```

(`question` is `_retrieve`'s first parameter — already in scope.)

- [ ] **Step 2: Update `chat.py`**

In `tools/chat.py`, add `import intent` next to `import retrieve` (line ~52). In `run_retrieval`, replace:

```python
    scores = retrieve.apply_primary_tier_boost(scores, metas)
```

with:

```python
    query_intent = intent.classify_intent(question)
    scores = retrieve.apply_intent_tier_weights(scores, metas, query_intent)
```

- [ ] **Step 3: Update `tune_sweep.py` (heuristic-only, to keep sweeps cheap/deterministic)**

In `tools/tune_sweep.py`, add `import intent` next to `import retrieve` (line ~33). In `retrieve_for`, replace:

```python
    scores = retrieve.apply_primary_tier_boost(scores, sub_metas)
```

with:

```python
    # Heuristic-only here so sweeps stay deterministic and make no API calls.
    query_intent = intent.classify_intent(question, use_llm_fallback=False)
    scores = retrieve.apply_intent_tier_weights(scores, sub_metas, query_intent)
```

(`retrieve_for`'s query parameter is `question` — confirmed.)

- [ ] **Step 4: Delete the dead `apply_primary_tier_boost`**

In `tools/retrieve.py`, delete the entire `apply_primary_tier_boost` function (and its preceding doc-comment block describing `PRIMARY_TIER_BOOST`). Also delete the now-unused `PRIMARY_TIER_BOOST = 0.07` constant. `PRIMARY_AUTHORS` stays (used by `apply_intent_tier_weights`).

- [ ] **Step 5: Verify nothing still references the removed symbols**

Run: `cd /Users/neharepal/gurudev-corpus && grep -rn "apply_primary_tier_boost\|PRIMARY_TIER_BOOST" tools/`
Expected: no output (all references removed).

- [ ] **Step 6: Import smoke-check (no API)**

Run:
```bash
cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -c "
import sys; sys.path.insert(0, 'tools')
import intent, retrieve
import ast
for f in ('tools/server.py','tools/chat.py','tools/tune_sweep.py','tools/retrieve.py','tools/intent.py'):
    ast.parse(open(f).read())
print('intent label for a doctrinal query:', intent.classify_intent('What is the philosophy of bhakti?', use_llm_fallback=False))
print('all modules parse + import OK')
"
```
Expected: prints `doctrinal` and `all modules parse + import OK`.

- [ ] **Step 7: Run the full unit suite**

Run: `cd /Users/neharepal/gurudev-corpus && /Users/neharepal/opt/anaconda3/bin/python -m pytest tools/tests/ -v`
Expected: PASS (all tests).

- [ ] **Step 8: Commit**

```bash
cd /Users/neharepal/gurudev-corpus
git add tools/server.py tools/chat.py tools/tune_sweep.py tools/retrieve.py
git commit -m "$(printf 'Wire intent-aware ranking into retrieval call sites (RFC-011)\n\nReplaces the flat apply_primary_tier_boost with intent x tier weighting in\nserver, chat, and tune_sweep; deletes the dead helper.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

- [ ] **Step 9: Manual integration check (cost-aware — run when ready, makes real API calls)**

With the backend restarted (`/Users/neharepal/opt/anaconda3/bin/python tools/server.py`), confirm:
1. The self-surrender doctrinal question now cites the canonical "Bhagavadgita as Pathway to God Realization" rather than the "ACPR Silver Jubilee Souvenir".
2. An "athvani about …" question surfaces athvani/recollection sources near the top.

Record findings; if the souvenir still wins, raise `TIER_WEIGHTS["doctrinal"]["reference"]`/`["recollections"]` separation or lower `DUP_THRESHOLD`, then re-check.

---

## Notes for the implementer

- **Line numbers drift** as you edit; they are approximate anchors. Locate by the quoted code, not the number.
- **Don't touch the corpus** (`00_raw`…`04_processed`, `CORPUS_CONTENTS.md`) — an ingestion may be running. Stage only the `tools/` and `docs/` files named in each commit.
- **RFC-011** (`docs/rfc/RFC-011-intent-aware-citation-ranking.md`) is the source of truth for intent, tiers, and the weight matrix.
- After Task 6, update RFC-011's Status from `PROPOSED` to `ACCEPTED <date>` in a follow-up commit if the integration check passes.
